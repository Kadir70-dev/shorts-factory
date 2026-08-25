from __future__ import annotations

import struct
import wave

import pytest

from app.voice.engines import VoiceIdentityError
from app.voice.manager import VoiceManager
from app.voice.profile import VoiceProfile
from app.voice.qa import VoiceQAError, inspect


def empty_profile() -> VoiceProfile:
    return VoiceProfile(identity="mine", display_name="Mine", locked=True,
                        speed=1.0, engines={}, lexicon={}, say_as={},
                        sentence_pause_ms=0, paragraph_pause_ms=0)


def write_wav(path, amplitude: int) -> None:
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(44100)
        wav.writeframes(b"".join(struct.pack("<h", amplitude)
                                 for _ in range(44100 // 2)))


def test_manager_refuses_to_render_without_clone():
    with pytest.raises(VoiceIdentityError, match="unavailable"):
        VoiceManager(empty_profile()).require_voice()


def test_qa_accepts_normalized_audible_wav(tmp_path):
    path = tmp_path / "voice.wav"
    write_wav(path, 1000)
    result = inspect(path)
    assert result.duration_sec == .5
    assert result.rms == 1000


def test_qa_rejects_silence(tmp_path):
    path = tmp_path / "silence.wav"
    write_wav(path, 0)
    with pytest.raises(VoiceQAError, match="silent"):
        inspect(path)
