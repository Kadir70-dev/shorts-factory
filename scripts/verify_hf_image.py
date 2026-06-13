#!/usr/bin/env python3
"""Verify the Hugging Face FREE image tier + the full image-provider chain order.

No-token mode: proves the chain SKIPS HF gracefully and never breaks.
Token mode  : actually generates a cinematic FLUX image via Hugging Face and
              asserts a real image file lands on disk (requirement 9's intent)."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))


async def main() -> None:
    from app.config import settings
    from app.pipeline import providers as P

    s = settings()
    tok = s.hf_api_token
    print(f"[cfg] base={s.huggingface_base_url} provider={s.huggingface_image_provider}")
    print(f"[cfg] models: {s.huggingface_image_model} → {s.huggingface_image_model_fast}")
    print(f"[cfg] token: {'set ('+tok[:6]+'…)' if tok else 'MISSING'}")

    # the helper exists and is wired
    assert hasattr(P, "_huggingface_image"), "_huggingface_image missing"

    subject = "a U.S. president resigning in disgrace, secret White House meeting"
    prompt = (f"{subject}. {P.AI_IMAGE_STYLE}. Avoid: {P.AI_IMAGE_NEGATIVE}.").strip(". ")

    if tok:
        # TOKEN MODE — real free FLUX generation through Hugging Face.
        print("\n[hf] generating a cinematic FLUX image via Hugging Face…")
        try:
            path = await P._huggingface_image(prompt, seed=7)
            size = Path(path).stat().st_size
            print(f"[hf] ✓ HF image inserted → {path} ({size//1024}KB)")
            assert size > 1024, "image file suspiciously small"
            print("\n✅ Hugging Face FREE FLUX image generation VERIFIED.")
        except Exception as e:  # noqa: BLE001
            print(f"[hf] ✗ HF generation failed: {type(e).__name__}: {e}")
            print("    (chain still safe — ai_image_generate would fall to "
                  "Pollinations → real footage; pipeline never breaks)")
            raise
    else:
        # NO-TOKEN MODE — prove the chain skips HF and still completes (offline plate).
        print("\n[chain] no HF token → exercising the full chain end (offline plate)…")
        s.ai_image_demo = True   # let the chain resolve to a local plate offline
        path = await P.ai_image_generate(subject, "vid_test", "s1_hook",
                                         category="history", seed=1)
        assert Path(path).exists(), "chain produced no image"
        print(f"[chain] ✓ chain completed without HF → {Path(path).name}")
        print("\n✅ Chain wiring verified (HF gracefully skipped). Provide HF_TOKEN to "
              "verify live FLUX generation.")


if __name__ == "__main__":
    asyncio.run(main())
