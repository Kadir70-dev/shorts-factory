"""Voice identity: the profile, the cascade lock, and speakable-text conversion.

The identity lock is the behaviour worth guarding hardest. Its whole value is that
it FAILS rather than substituting a different narrator — a test that only checked
"synthesis succeeded" would pass while the pipeline quietly shipped a stranger.
"""
from __future__ import annotations

import pytest
import yaml

from app.voice import profile as P


def write_profile(tmp_path, monkeypatch, **overrides):
    """Build a profile file and point the loader at it."""
    doc = {
        "identity": "test_voice_v1",
        "display_name": "Test voice",
        "locked": True,
        "allow_stock_fallback": False,
        "acknowledge_noncommercial": False,
        "prosody": {"speed": 1.04},
        "engines": {
            "elevenlabs": {"enabled": True, "voice_id": ""},
            "piper": {"enabled": True, "model_path": ""},
            "xtts": {"enabled": True, "reference_wav": ""},
        },
        "pronunciation": {
            "lexicon": {"S&P 500": "S and P five hundred", "bps": "basis points"},
            "say_as": {"CPI": "C P I", "BLS": "B L S", "GDP": "G D P"},
        },
    }
    doc.update(overrides)
    cfg = tmp_path / "voice"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "profile.yaml").write_text(yaml.safe_dump(doc))
    monkeypatch.setattr(P, "profile_path", lambda: cfg / "profile.yaml")
    P.load_profile.cache_clear()
    return doc


@pytest.fixture(autouse=True)
def _clear_cache():
    P.load_profile.cache_clear()
    yield
    P.load_profile.cache_clear()


# --------------------------------------------------------------------------- #
# Profile + cascade
# --------------------------------------------------------------------------- #
def test_a_missing_profile_is_inert_not_fatal(tmp_path, monkeypatch):
    monkeypatch.setattr(P, "profile_path", lambda: tmp_path / "nope.yaml")
    P.load_profile.cache_clear()
    prof = P.load_profile()
    assert not prof.exists
    assert prof.cascade() == []


def test_an_unenrolled_profile_has_an_empty_cascade(tmp_path, monkeypatch):
    write_profile(tmp_path, monkeypatch)
    prof = P.load_profile()
    assert prof.exists
    assert prof.cascade() == [], (
        "nothing is enrolled yet, so no engine can carry the voice")


def test_diagnostics_say_what_to_do(tmp_path, monkeypatch):
    write_profile(tmp_path, monkeypatch)
    lines = "\n".join(P.load_profile().diagnostics())
    assert "chatterbox" in lines
    assert "openf5" in lines
    assert "piper" in lines


def test_an_enrolled_engine_enters_the_cascade(tmp_path, monkeypatch):
    model = tmp_path / "voice.onnx"
    model.write_bytes(b"x" * 512)
    write_profile(tmp_path, monkeypatch, engines={
        "piper": {"enabled": True, "model_path": str(model)},
    })
    assert P.load_profile().cascade() == ["piper"]


def test_the_cascade_only_contains_this_identity(tmp_path, monkeypatch):
    """The point of the lock: falling back changes FIDELITY, never who is
    speaking. There is no stock voice anywhere in this list."""
    model = tmp_path / "voice.onnx"
    model.write_bytes(b"x" * 512)
    write_profile(tmp_path, monkeypatch, engines={
        "piper": {"enabled": True, "model_path": str(model)},
    })
    assert P.load_profile().cascade() == ["piper"]
    assert all(e in P.CLONE_ENGINES for e in P.load_profile().cascade())


def test_disabled_engines_are_excluded(tmp_path, monkeypatch):
    model = tmp_path / "voice.onnx"
    model.write_bytes(b"x" * 512)
    write_profile(tmp_path, monkeypatch, engines={
        "piper": {"enabled": False, "model_path": str(model)},
    })
    assert P.load_profile().cascade() == []


def test_only_apache_openf5_repository_is_accepted(tmp_path, monkeypatch):
    ref = tmp_path / "ref.wav"
    ref.write_bytes(b"x" * 512)
    model = tmp_path / "model.pt"
    config = tmp_path / "config.yaml"
    vocab = tmp_path / "vocab.txt"
    for path in (model, config, vocab):
        path.write_bytes(b"x" * 512)
    write_profile(tmp_path, monkeypatch, engines={
        "openf5": {"enabled": True, "reference_wav": str(ref),
                    "reference_text": "I recorded this reference.",
                    "repository": "SWivid/F5-TTS", "model_path": str(model),
                    "config_path": str(config), "vocab_path": str(vocab)},
    })
    assert P.load_profile().cascade() == []

    write_profile(tmp_path, monkeypatch, engines={
        "openf5": {"enabled": True, "reference_wav": str(ref),
                    "reference_text": "I recorded this reference.",
                    "repository": P.OPENF5_REPOSITORY, "model_path": str(model),
                    "config_path": str(config), "vocab_path": str(vocab)},
    })
    assert P.load_profile().cascade() == ["openf5"]


def test_a_missing_model_file_does_not_count_as_enrolled(tmp_path, monkeypatch):
    write_profile(tmp_path, monkeypatch, engines={
        "piper": {"enabled": True, "model_path": str(tmp_path / "absent.onnx")},
    })
    prof = P.load_profile()
    assert prof.cascade() == []
    assert "model missing" in "\n".join(prof.diagnostics())


def test_synthesis_raises_rather_than_substituting(tmp_path, monkeypatch):
    import asyncio

    from app.voice import engines as E
    write_profile(tmp_path, monkeypatch)
    with pytest.raises(E.VoiceIdentityError):
        asyncio.run(E.synthesize("hello", tmp_path / "out.wav", P.load_profile()))


# --------------------------------------------------------------------------- #
# Speakable text
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("written,spoken_fragment", [
    ("The CPI rose 3.4%.", "C P I"),
    ("The CPI rose 3.4%.", "three point four percent"),
    ("It cost $1.50.", "one dollar fifty"),
    ("Revenue hit $4.2B.", "four point two billion dollars"),
    ("In 2024 it changed.", "twenty twenty-four"),
    ("Back in 1985.", "nineteen eighty-five"),
    ("Through the 1980s.", "nineteen eighties"),
    ("Through the 2010s.", "twenty tens"),
    ("Through the 2000s.", "two thousands"),
    ("The S&P 500 closed higher.", "S and P five hundred"),
    ("Median income was $74,580.", "seventy-four thousand five hundred eighty"),
    ("Rates fell 25 bps.", "basis points"),
    ("GDP grew 2.8%.", "G D P"),
])
def test_speakable_normalisation(tmp_path, monkeypatch, written, spoken_fragment):
    write_profile(tmp_path, monkeypatch)
    out = P.speakable(written, P.load_profile())
    assert spoken_fragment in out, f"{written!r} → {out!r}"


def test_decades_are_pluralised_properly(tmp_path, monkeypatch):
    write_profile(tmp_path, monkeypatch)
    out = P.speakable("Through the 1980s and 1990s.", P.load_profile())
    assert "eightys" not in out and "ninetys" not in out, (
        f"naive pluralisation of the year words: {out!r}")


def test_money_does_not_swallow_the_following_word(tmp_path, monkeypatch):
    write_profile(tmp_path, monkeypatch)
    out = P.speakable("It settled at $78.42 a barrel.", P.load_profile())
    assert "forty-two a barrel" in out, f"words welded together: {out!r}"


def test_unlisted_acronyms_are_left_alone(tmp_path, monkeypatch):
    """Blanket letter-spacing would wreck NASA and OPEC, so `say_as` is an
    explicit list rather than a rule."""
    write_profile(tmp_path, monkeypatch)
    out = P.speakable("NASA and OPEC met.", P.load_profile())
    assert "NASA" in out and "OPEC" in out


def test_speakable_always_ends_on_punctuation(tmp_path, monkeypatch):
    write_profile(tmp_path, monkeypatch)
    assert P.speakable("no full stop here", P.load_profile()).endswith(".")


def test_written_form_is_not_mutated(tmp_path, monkeypatch, graph):
    """Captions and overlays must keep "$4.2B" while the voice says the words."""
    write_profile(tmp_path, monkeypatch)
    original = graph.scenes[0].narration
    P.speakable(original, P.load_profile())
    assert graph.scenes[0].narration == original
