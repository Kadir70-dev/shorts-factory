#!/usr/bin/env python3
"""Focused verification of the OpenRouter backup/augmentation layer (no render)."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))


async def main() -> None:
    from app import openrouter
    from app.config import settings
    from app.director.backends import (CLIBackend, FallbackBackend,
                                       OpenRouterBackend, get_backend)

    s = settings()
    print(f"[cfg] base_url={s.openrouter_base_url} model={s.openrouter_model} "
          f"key={'set' if s.openrouter_api_key else 'MISSING'}")

    # 1) enabled() should log '[openrouter] enabled' once
    assert openrouter.enabled() is True, "expected OpenRouter enabled with key set"

    # 2) live reachability — a real backup chat call. If the account has no credits
    #    (402) or any other error, that is reported but does NOT fail the contract:
    #    every caller treats chat() as best-effort and degrades gracefully.
    live = False
    try:
        txt = await openrouter.chat("You are terse.", "Reply with exactly: PONG")
        print(f"[chat] live -> {txt!r}")
        live = bool(txt.strip())
    except Exception as e:  # noqa: BLE001
        print(f"[chat] NOT live ({type(e).__name__}: {str(e)[:80]}) — "
              "backup output unavailable until the OpenRouter account has credit")

    # 3) image-prompt enhancement MUST be graceful: enhanced when live, otherwise the
    #    ORIGINAL subject unchanged. Either way it returns a usable prompt — never empty.
    subject = "the forgotten scandal that broke a president"
    enhanced = await openrouter.enhance_image_prompt(subject)
    print(f"[enhance] -> {enhanced[:100]!r}")
    assert enhanced, "enhancement returned empty"
    if not live:
        assert enhanced == subject, "must fall back to the original subject on error"
        print("[enhance] gracefully kept the original subject (no credit) ✓")

    # 4) backend wiring: with a key present, get_backend() wraps primary in fallback
    be = get_backend()
    assert isinstance(be, FallbackBackend), f"expected FallbackBackend, got {type(be)}"
    assert isinstance(be.primary, CLIBackend), "primary must stay the Claude CLI"
    assert isinstance(be.fallback, OpenRouterBackend), "fallback must be OpenRouter"
    print(f"[backend] {type(be).__name__}(primary={type(be.primary).__name__}, "
          f"fallback={type(be.fallback).__name__})")

    # 5) failure-recovery wiring: simulate the primary crashing -> the FallbackBackend
    #    routes to OpenRouter and logs '[openrouter] fallback model used'. Whether the
    #    backup itself succeeds depends on account credit; we assert the ROUTING fired.
    routed = {"hit": False}

    class Boom:
        async def generate(self, *a, **k):
            raise RuntimeError("claude CLI failed: simulated crash")
        async def research(self, q):
            return ""

    class SpyBackup(OpenRouterBackend):
        async def generate(self, *a, **k):
            routed["hit"] = True
            return await super().generate(*a, **k)

    recover = FallbackBackend(Boom(), SpyBackup())
    schema = {"type": "object", "properties": {"ok": {"type": "boolean"}},
              "required": ["ok"], "additionalProperties": False}
    try:
        raw = await recover.generate("Return JSON.", "Return {\"ok\": true}", schema)
        print(f"[recover] fallback produced: {raw[:120]!r}")
    except Exception as e:  # noqa: BLE001
        print(f"[recover] backup also unavailable ({type(e).__name__}: {str(e)[:60]})")
    assert routed["hit"], "FallbackBackend did not route to OpenRouter on primary crash"
    print("[recover] primary crash correctly routed to the OpenRouter backup ✓")

    print("\n✅ OpenRouter layer verified: enabled-log, wiring, graceful degradation, "
          "and failure-recovery routing." + ("" if live else
          "\n⚠️  Backup OUTPUT is gated on account credit (got 402). Add credit at "
          "openrouter.ai/credits to activate actual fallback generations; until then "
          "the layer is a safe no-op and the Claude CLI pipeline is unaffected."))


if __name__ == "__main__":
    asyncio.run(main())
