"""
VideoSpec — the top-level request contract.

This is what the USER (or the CLI / dashboard) asks for. It is intentionally
small and human-authored. Everything downstream (research, script, scenes) is
DERIVED from this by the Director engine. Keep this thin.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class Niche(str, Enum):
    # K70 Network Solution content buckets. Politics absorbs elections; finance
    # is the "economy explained" bucket. facts/history/business are the new
    # evergreen buckets.
    politics = "usa_politics"
    election = "usa_election"
    finance = "usa_finance"
    facts = "usa_facts"
    history = "usa_history"
    business = "usa_business"
    # Cybersecurity / cybercrime storytelling (dark Netflix-doc bucket).
    cybersecurity = "cybersecurity"


class Platform(str, Enum):
    youtube = "youtube_shorts"
    facebook = "facebook_reels"
    instagram = "instagram_reels"
    tiktok = "tiktok"


class JobStatus(str, Enum):
    queued = "queued"
    researching = "researching"
    scripting = "scripting"
    voicing = "voicing"
    captioning = "captioning"
    assets = "assets"
    rendering = "rendering"
    post = "post"
    awaiting_approval = "awaiting_approval"
    approved = "approved"
    uploading = "uploading"
    done = "done"
    failed = "failed"


class VoiceConfig(BaseModel):
    provider: Literal["elevenlabs", "openai", "piper"] = "elevenlabs"
    voice_id: str = "Rachel"
    speed: float = Field(1.0, ge=0.7, le=1.3)
    stability: float = Field(0.5, ge=0.0, le=1.0)


class RenderConfig(BaseModel):
    width: int = 1080
    height: int = 1920
    fps: int = 30
    # Hard guardrails for Shorts. Director must respect these.
    min_duration_sec: float = 20.0
    max_duration_sec: float = 45.0


class VideoSpec(BaseModel):
    """One unit of work. Maps 1:1 to a job and (eventually) one MP4."""

    id: str = Field(default_factory=lambda: f"vid_{uuid4().hex[:12]}")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # --- authored by user ---
    channel_id: str                       # resolves to config/channels/<id>.yaml
    niche: Niche
    topic: str                            # the input prompt, e.g. "inflation Q2 2026"
    platforms: list[Platform] = [Platform.youtube]

    # --- defaults pulled from channel config, overridable per-request ---
    voice: Optional[VoiceConfig] = None   # None => inherit channel default
    render: RenderConfig = RenderConfig()

    # --- knobs ---
    allow_ai_video: bool = False          # Veo3/Seedance hero shots (cost gate)
    # AI documentary IMAGES (Phase 5.5). ON by default: the slot degrades to a
    # free local cinematic plate when no provider key is set, so it never costs
    # unless a real image API key is configured. Set False to force all-real.
    allow_ai_image: bool = True
    tone: Literal["neutral", "punchy", "explainer"] = "punchy"

    # --- reusable character (Phase 3 layered/anime path; all optional) -------- #
    # When the layered render is on and a character is named here, the Storyboard
    # Agent locks ONE reusable character (stable seed + description) for the hero
    # SUBJECT plane so it stays consistent across scenes/runs. Empty → no subject
    # plane is added (hero stack is background + fx only). Backward compatible.
    character_name: str = ""               # short token, e.g. "kade"
    character_desc: str = ""               # locked visual description
    character_style: str = ""              # optional style suffix (e.g. anime look)

    # --- lifecycle ---
    status: JobStatus = JobStatus.queued
    error: Optional[str] = None


class BatchRequest(BaseModel):
    """Parses 'Generate 5 USA election shorts for today'."""

    channel_id: str
    niche: Niche
    count: int = Field(1, ge=1, le=50)
    topic: Optional[str] = None           # if None, Director picks from trending
    platforms: list[Platform] = [Platform.youtube]
    allow_ai_video: bool = False
    allow_ai_image: bool = True
