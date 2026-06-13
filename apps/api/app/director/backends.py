"""
Director backends. Both return RAW TEXT expected to be a JSON object; the engine
handles JSON extraction + Pydantic validation + repair.

  CLIBackend  — shells out to `claude -p` headless. Runs on the user's Claude
                MAX subscription (no API billing). Default. Testable offline-ish.
  APIBackend  — Anthropic Messages API with forced tool-use (input_schema ==
                SceneGraph schema). Needs ANTHROPIC_API_KEY. Scales / parallel.
"""
from __future__ import annotations

import asyncio
import json
import os

from ..config import settings


# Fact-first research brief. Rejects weak sources, demands dates + named primary
# sources, and separates confirmed facts from forecasts so the Director can label
# `confidence` honestly. Shared by both backends.
_RESEARCH_PROMPT = (
    "Research this topic for a 30-second USA macro/news short: {query}\n\n"
    "Use web search. Be a fact-checker, not a hype writer. Rules:\n"
    "- Use ONLY credible PRIMARY/official or top-tier sources: BLS, BEA, Federal "
    "Reserve, Treasury, EIA, Census, CBO, the named company/agency, or major "
    "wires (AP, Reuters, Bloomberg, WSJ). REJECT blogs, social media, rumor, "
    "anonymous claims, and anything you can't attribute.\n"
    "- Every fact MUST have a NAMED source and a DATE (or period). If you can't "
    "source it, DROP it — do not guess or fill gaps.\n"
    "- Separate clearly:\n"
    "    CONFIRMED  — reported actuals (e.g. 'CPI 3.8% YoY, BLS, May 2026').\n"
    "    FORECAST   — expectations/projections ('Fed dot plot expects ...').\n"
    "    UNCERTAIN  — contested/speculative; note who is speculating.\n"
    "- Do NOT assert causality unless a source states it; otherwise mark it as an "
    "analyst view.\n"
    "- If reliable sources are thin, return FEWER bullets rather than padding.\n\n"
    "Return 4-6 plain-text bullets. Tag each bullet with [CONFIRMED]/[FORECAST]/"
    "[UNCERTAIN], the figure/date, and the named source."
)


class CLIBackend:
    """Uses the local `claude` CLI on the Max plan."""

    def __init__(self):
        self.bin = os.getenv("CLAUDE_BIN", "claude")
        self.model = os.getenv("DIRECTOR_CLI_MODEL", "opus")

    async def generate(self, system: str, user: str, schema: dict) -> str:
        prompt = (
            f"{system}\n\n---\n\n{user}\n\n---\n\n"
            "Output ONLY a single minified JSON object that validates against "
            "this JSON Schema. No markdown fences, no commentary, JSON only:\n"
            f"{json.dumps(schema)}"
        )
        result = await self._run(prompt, allow_search=False)
        return result

    async def research(self, query: str) -> str:
        try:
            return await self._run(_RESEARCH_PROMPT.format(query=query), allow_search=True)
        except Exception:
            return ""   # research is best-effort; never block generation

    async def _run(self, prompt: str, allow_search: bool) -> str:
        args = [self.bin, "-p", "--output-format", "json", "--model", self.model]
        if allow_search:
            args += ["--allowed-tools", "WebSearch"]
        else:
            args += ["--max-turns", "1"]
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, err = await proc.communicate(prompt.encode())
        if proc.returncode != 0:
            raise RuntimeError(f"claude CLI failed: {err.decode()[:400]}")
        env = json.loads(out.decode())
        if env.get("is_error"):
            raise RuntimeError(f"claude error: {env.get('result', '')[:300]}")
        return env["result"]


class APIBackend:
    """Uses the Anthropic Messages API with forced tool-use."""

    def __init__(self):
        from anthropic import AsyncAnthropic
        self.client = AsyncAnthropic(api_key=settings().anthropic_api_key)
        self.model = settings().director_model

    async def generate(self, system: str, user: str, schema: dict) -> str:
        resp = await self.client.messages.create(
            model=self.model,
            max_tokens=settings().director_max_tokens,
            system=system,
            tools=[{"name": "emit_scene_graph",
                    "description": "Return the complete SceneGraph.",
                    "input_schema": schema}],
            tool_choice={"type": "tool", "name": "emit_scene_graph"},
            messages=[{"role": "user", "content": user}],
        )
        block = next(b for b in resp.content if b.type == "tool_use")
        return json.dumps(block.input)

    async def research(self, query: str) -> str:
        try:
            resp = await self.client.messages.create(
                model=self.model, max_tokens=1500,
                tools=[{"type": "web_search_20250305", "name": "web_search",
                        "max_uses": 5}],
                messages=[{"role": "user", "content": _RESEARCH_PROMPT.format(query=query)}],
            )
            return "".join(b.text for b in resp.content if b.type == "text")
        except Exception:
            return ""


class OpenRouterBackend:
    """OpenAI-compatible BACKUP brain via OpenRouter (failure recovery only — it is
    never the primary Director). Same generate()/research() contract as the others."""

    def __init__(self):
        self.model = settings().openrouter_model

    async def generate(self, system: str, user: str, schema: dict) -> str:
        from .. import openrouter
        prompt = (
            f"{user}\n\n---\n\n"
            "Output ONLY a single minified JSON object that validates against this "
            "JSON Schema. No markdown fences, no commentary, JSON only:\n"
            f"{json.dumps(schema)}"
        )
        return await openrouter.chat(
            system, prompt, max_tokens=settings().director_max_tokens)

    async def research(self, query: str) -> str:
        # Best-effort brief; OpenRouter has no first-class web search wired here, so
        # the backup path simply skips research (generation is the critical path).
        return ""


class FallbackBackend:
    """The primary brain (Claude CLI / API) with an OpenRouter safety net. The
    primary stays in charge: OpenRouter is invoked ONLY when the primary raises —
    failure recovery so a transient CLI crash doesn't sink the whole job."""

    def __init__(self, primary, fallback):
        self.primary = primary
        self.fallback = fallback

    async def generate(self, system: str, user: str, schema: dict) -> str:
        try:
            return await self.primary.generate(system, user, schema)
        except Exception as e:  # noqa: BLE001
            from .. import openrouter
            openrouter.log(
                "fallback model used (generate) — primary director failed "
                f"({type(e).__name__}: {str(e)[:120]})")
            return await self.fallback.generate(system, user, schema)

    async def research(self, query: str) -> str:
        # research is already best-effort (the primary swallows its own errors and
        # returns ""), so just delegate — no need to spend a backup call here.
        return await self.primary.research(query)


def get_backend():
    """Pick the primary Director backend (Claude CLI by default, or the Anthropic
    API). If OpenRouter is configured, wrap it in a FallbackBackend so a hard
    primary failure recovers via the cheap backup model — Claude stays primary."""
    from .. import openrouter
    name = os.getenv("DIRECTOR_BACKEND", "cli").lower()
    primary = APIBackend() if name == "api" else CLIBackend()
    if openrouter.enabled():
        return FallbackBackend(primary, OpenRouterBackend())
    return primary
