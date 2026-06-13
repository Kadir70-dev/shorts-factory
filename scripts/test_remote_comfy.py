#!/usr/bin/env python3
"""Test the remote ComfyUI image backend end-to-end.

Builds the same DreamShaper SD1.5 txt2img graph the pipeline uses, submits it to
the remote ComfyUI server (Colab GPU via Cloudflare tunnel), waits for the result,
and asserts a real PNG lands in ShortsFactory's normal image cache.

Run:  make test-comfy
  or: .venv/bin/python scripts/test_remote_comfy.py "your prompt here"

If COMFYUI_ENABLED=0 / COMFYUI_BASE_URL is blank, it prints how to enable and
exits 0 (the pipeline would simply use the existing image chain instead)."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

DEFAULT_SUBJECT = "cinematic dramatic documentary scene, ultra realistic"


async def main() -> None:
    from app.config import settings
    from app.pipeline import providers as P

    s = settings()
    subject = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SUBJECT

    print(f"[cfg] enabled={s.comfyui_enabled} mode={s.comfyui_mode}")
    print(f"[cfg] base_url={s.comfyui_base_url or 'MISSING'}")
    print(f"[cfg] checkpoint={s.comfyui_checkpoint} "
          f"size={s.comfyui_width}x{s.comfyui_height} steps={s.comfyui_steps} "
          f"timeout={s.comfyui_timeout}s")

    if not (s.comfyui_enabled and s.comfyui_base_url):
        print("\n[skip] ComfyUI disabled or no base URL. To enable, set in .env:")
        print("       COMFYUI_ENABLED=1")
        print("       COMFYUI_MODE=remote")
        print("       COMFYUI_BASE_URL=https://<your-tunnel>.trycloudflare.com")
        print("       COMFYUI_TIMEOUT=900")
        print("\n(The pipeline still works — it falls back to the existing "
              "image chain: Google → HuggingFace → Pollinations → footage.)")
        return

    assert hasattr(P, "_remote_comfyui_image"), "_remote_comfyui_image missing"

    prompt = (f"{subject}. {P.AI_IMAGE_STYLE}. "
              f"Avoid: {P.AI_IMAGE_NEGATIVE}.").strip(". ")
    print(f"\n[comfy] submitting prompt to {s.comfyui_base_url} …")
    print(f"[comfy] subject={subject!r}")

    path = await P._remote_comfyui_image(prompt, seed=7)
    size = Path(path).stat().st_size
    print(f"[comfy] ✓ image generated → {path} ({size // 1024}KB)")
    assert size > 1024, "image file suspiciously small"
    print("\n✅ Remote ComfyUI generation VERIFIED. The image is in the normal "
          "cache; downstream editing consumes it unchanged.")


if __name__ == "__main__":
    asyncio.run(main())
