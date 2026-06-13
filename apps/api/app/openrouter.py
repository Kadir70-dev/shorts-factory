"""
OpenRouter — OPTIONAL backup / augmentation provider. NEVER the primary brain.

Claude CLI (Claude Max) stays the default Director. OpenRouter is wired in ONLY as:
  • AI image-prompt enhancement — sharpen a beat's subject into a richer cinematic
    text-to-image prompt.
  • cheap backup LLM routing — an OpenAI-compatible /chat/completions client.
  • failure recovery — a safety net the Director uses when the Claude CLI crashes.

Hard contract: if OPENROUTER_API_KEY is blank, EVERYTHING here is a silent no-op —
`enabled()` is False and the helpers return their input unchanged. The existing
pipeline must never break or change behavior when OpenRouter is not configured.
"""
from __future__ import annotations

import httpx

from .config import settings

_ENABLED_LOGGED = False


def log(msg: str) -> None:
    print(f"[openrouter] {msg}", flush=True)


def enabled() -> bool:
    """True iff an OpenRouter key is configured. Logs '[openrouter] enabled' once."""
    global _ENABLED_LOGGED
    on = bool(settings().openrouter_api_key.strip())
    if on and not _ENABLED_LOGGED:
        log(f"enabled (model={settings().openrouter_model}; "
            "backup/augmentation only — Claude CLI stays primary)")
        _ENABLED_LOGGED = True
    return on


async def chat(system: str, user: str, *, model: str | None = None,
               max_tokens: int = 4000, temperature: float = 0.4) -> str:
    """One OpenAI-compatible chat completion via OpenRouter. Returns the assistant
    text. RAISES on any failure — callers decide whether to swallow it."""
    s = settings()
    headers = {
        "Authorization": f"Bearer {s.openrouter_api_key}",
        "Content-Type": "application/json",
        # Optional OpenRouter attribution headers (recommended, harmless if ignored).
        "HTTP-Referer": "https://github.com/k70/shorts-factory",
        "X-Title": "K70 Shorts Factory",
    }
    body = {
        "model": model or s.openrouter_model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    url = f"{s.openrouter_base_url.rstrip('/')}/chat/completions"
    async with httpx.AsyncClient(timeout=120) as c:
        r = await c.post(url, headers=headers, json=body)
        r.raise_for_status()
        data = r.json()
    return data["choices"][0]["message"]["content"]


# Cinematic prompt-engineer brief for image-prompt enhancement. Mirrors the
# Netflix/Vox/Bloomberg documentary doctrine the image style suffix already bakes
# in (providers.AI_IMAGE_STYLE), so the two reinforce rather than fight.
_IMG_PROMPT_SYS = (
    "You are a cinematic prompt engineer for a Netflix/Vox/Bloomberg-style "
    "documentary-shorts brand. Rewrite the user's scene subject into ONE vivid, "
    "concrete visual prompt for a text-to-image model: name the subject, setting, "
    "composition, lighting and mood. Photoreal documentary look, vertical 9:16. "
    "No text, words, logos or watermarks in the image. Keep it under 55 words. "
    "Output ONLY the prompt — no preamble, no quotes, no markdown."
)


async def enhance_image_prompt(subject: str) -> str:
    """Sharpen an AI-image subject line via the cheap backup model. BEST-EFFORT:
    returns the ORIGINAL subject unchanged if OpenRouter is disabled or errors, so
    image generation behaves exactly as before when not configured."""
    if not enabled():
        return subject
    try:
        out = (await chat(_IMG_PROMPT_SYS, subject.strip(),
                          max_tokens=220, temperature=0.7)).strip()
        if out:
            log(f"image prompt enhanced: {subject[:40]!r} → {out[:60]!r}")
            return out
    except Exception as e:  # noqa: BLE001
        log(f"image prompt enhance failed ({type(e).__name__}) → using original")
    return subject
