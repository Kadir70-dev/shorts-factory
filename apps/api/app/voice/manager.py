"""Strict orchestration for local cloned-voice synthesis."""
from __future__ import annotations

from pathlib import Path

from . import engines
from .profile import VoiceProfile, load_profile, speakable
from .qa import QAResult, inspect


class VoiceManager:
    def __init__(self, profile: VoiceProfile | None = None):
        self.profile = profile or load_profile()

    def require_voice(self) -> None:
        if not self.profile.exists:
            raise engines.VoiceIdentityError(
                "config/voice/profile.yaml is required; stock voices are disabled")
        if not self.profile.identity.strip():
            raise engines.VoiceIdentityError("voice profile has no identity")
        if not (self.profile.cascade() or self.profile.fallback_cascade()):
            raise engines.VoiceIdentityError(
                f"cloned voice {self.profile.identity!r} is unavailable:\n" +
                "\n".join(self.profile.diagnostics()))

    def preprocess(self, text: str) -> str:
        return speakable(text, self.profile)

    async def synthesize(self, text: str, out: Path) -> tuple[str, QAResult]:
        self.require_voice()
        engine = await engines.synthesize(self.preprocess(text), out, self.profile)
        try:
            result = inspect(out)
        except Exception:
            out.unlink(missing_ok=True)
            raise
        return engine, result
