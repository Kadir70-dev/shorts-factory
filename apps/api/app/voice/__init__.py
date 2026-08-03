"""
Voice identity — the channel's narrator.

Kokoro CANNOT clone a voice. It is a small StyleTTS2-derived model that ships a
fixed pack of pre-trained speaker embeddings; there is no supported zero-shot
cloning or fine-tuning path, and no amount of reference audio changes that. So
"use my own voice" means moving narration to an engine that can actually carry a
cloned identity.

The production paths use the SAME recording session and remain entirely local:

  PIPER FINE-TUNE  (default, permanent)
      MIT-licensed, unrestricted commercial use, runs faster than real time on a
      CPU with no GPU, and fine-tunes cleanly from 20–40 minutes of clean single-
      speaker audio. This is what makes "my voice on every future Short" viable at
      thousands of videos: after the one-off training, each render costs nothing
      and depends on nothing.

  CHATTERBOX / OPENF5
      Zero-shot local cloning from a pinned reference. OpenF5 accepts only the
      Apache-2.0 mrfakename/OpenF5-TTS-Base weights.

The architectural change that matters most is the IDENTITY LOCK. The old cascade
degraded to a different stock narrator when a provider failed. For a channel whose
brand is the host's voice, shipping a stranger reading the script is worse than
shipping nothing — so the cascade now contains only engines carrying this
identity, and running out of them fails the render loudly.
"""
from .manager import VoiceManager
from .profile import (VoiceProfile, load_profile, profile_path,
                      speakable, has_clone)

__all__ = ["VoiceProfile", "load_profile", "profile_path", "speakable",
           "has_clone", "VoiceManager"]
