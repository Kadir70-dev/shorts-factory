"""
Per-channel publishing config (config/publishing/<channel>.yaml) and the guards
that keep channels from ever touching each other's credentials or history.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from ..config import CONFIG_DIR, ROOT

PUBLISHING_DIR = CONFIG_DIR / "publishing"
SECRETS_DIR = CONFIG_DIR / "secrets"
REQUIRED = ("channel", "display_name", "output_dir", "youtube", "schedule")


class ChannelConfigError(RuntimeError):
    pass


def _abs(p: str) -> Path:
    path = Path(p)
    return path if path.is_absolute() else (ROOT / path)


def load(channel: str) -> dict:
    path = PUBLISHING_DIR / f"{channel}.yaml"
    if not path.exists():
        raise ChannelConfigError(f"no publishing config: {path}")
    cfg = yaml.safe_load(path.read_text()) or {}
    missing = [k for k in REQUIRED if k not in cfg]
    if missing:
        raise ChannelConfigError(f"{channel}: missing keys {missing}")
    if cfg["channel"] != channel:
        raise ChannelConfigError(f"{path.name} declares channel {cfg['channel']!r}")
    yt = cfg["youtube"]
    cfg["_token"] = _abs(yt["token"])
    cfg["_client_secret"] = _abs(yt["client_secret"])
    cfg["_output_dir"] = _abs(cfg["output_dir"])
    if cfg.get("creative_channel"):
        try:
            from ..config import load_channel
            cfg.setdefault("cta", load_channel(cfg["creative_channel"]).cta)
        except FileNotFoundError:
            pass
    return cfg


def all_channels() -> list[str]:
    return sorted(p.stem for p in PUBLISHING_DIR.glob("*.yaml"))


def isolation_errors() -> list[str]:
    """Cross-channel checks: unique credentials, outputs and YouTube ids, and
    every secret lives under config/secrets/<channel>/."""
    errs: list[str] = []
    seen: dict[str, str] = {}
    for ch in all_channels():
        try:
            cfg = load(ch)
        except ChannelConfigError as e:
            errs.append(str(e))
            continue
        for key in ("_token", "_client_secret", "_output_dir"):
            p = str(cfg[key].resolve())
            if p in seen:
                errs.append(f"{ch} and {seen[p]} share {key.strip('_')}: {p}")
            seen[p] = ch
        for key in ("_token", "_client_secret"):
            own = (SECRETS_DIR / ch).resolve()
            if own not in cfg[key].resolve().parents:
                errs.append(f"{ch}: {key.strip('_')} must live under {own}")
        yid = cfg["youtube"].get("expected_channel_id", "")
        if yid:
            if f"yt:{yid}" in seen:
                errs.append(f"{ch} and {seen[f'yt:{yid}']} target the same YouTube channel")
            seen[f"yt:{yid}"] = ch
    return errs


def upload_readiness(cfg: dict) -> list[str]:
    """Blocking problems for a real upload on this channel."""
    probs = []
    if not cfg["youtube"].get("expected_channel_id", "").startswith("UC"):
        probs.append("youtube.expected_channel_id not set (UC...)")
    if not cfg["_client_secret"].exists():
        probs.append(f"OAuth client secret missing: {cfg['_client_secret']}")
    if not cfg["_token"].exists():
        probs.append(f"no OAuth token yet: run `auth --channel {cfg['channel']}`")
    return probs
