"""Storyboard-grounded AI cinematic B-roll adapters and orchestration."""
from __future__ import annotations

import asyncio
import hashlib
import json
import resource
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from ..brand import theme_for
from ..config import settings
from ..schemas.scene import (AIBrollRenderProvenance, AICinematicSpec, Scene,
                             SceneGraph, StoryboardScene)
from . import providers as visual_providers


@dataclass(frozen=True)
class GeneratedAsset:
    path: str
    model: str
    asset_type: str


class ProviderAdapter(Protocol):
    name: str

    def available(self) -> bool: ...
    def model(self) -> str: ...
    async def generate(self, prompt: AICinematicSpec, scene: Scene,
                       quality: str) -> GeneratedAsset: ...


class FluxAdapter:
    name = "flux"

    def available(self) -> bool:
        # Pollinations FLUX is the existing no-key final image endpoint.
        return bool(settings().hf_api_token or settings().pollinations_model)

    def model(self) -> str:
        return (settings().huggingface_image_model if settings().hf_api_token
                else settings().pollinations_model)

    async def generate(self, prompt: AICinematicSpec, scene: Scene,
                       quality: str) -> GeneratedAsset:
        text = f"{prompt.cinematic_prompt}. Avoid: {prompt.negative_prompt}."
        if settings().hf_api_token:
            path = await visual_providers._huggingface_image(
                text, prompt.continuity_seed)
        else:
            path = await visual_providers._pollinations_image(
                text, prompt.continuity_seed)
        return GeneratedAsset(path, self.model(), "image")


class StableDiffusionAdapter:
    name = "stable_diffusion"

    def available(self) -> bool:
        return bool(settings().comfyui_enabled and settings().comfyui_base_url)

    def model(self) -> str:
        return settings().comfyui_checkpoint

    async def generate(self, prompt: AICinematicSpec, scene: Scene,
                       quality: str) -> GeneratedAsset:
        text = f"{prompt.cinematic_prompt}. Avoid: {prompt.negative_prompt}."
        path = await visual_providers._remote_comfyui_image(
            text, prompt.continuity_seed)
        return GeneratedAsset(path, self.model(), "image")


class WanAdapter:
    name = "wan"

    def available(self) -> bool:
        return bool(settings().picsart_api_key)

    def model(self) -> str:
        return settings().picsart_model

    async def generate(self, prompt: AICinematicSpec, scene: Scene,
                       quality: str) -> GeneratedAsset:
        still = await visual_providers.ai_image_generate(
            prompt.cinematic_prompt, "ai_broll", scene.id,
            category="business", seed=prompt.continuity_seed)
        video = await visual_providers.picsart_image_to_video(
            still, prompt.cinematic_prompt,
            visual_providers.clamp_i2v_seconds(prompt.duration),
            "ai_broll", scene.id, seed=prompt.continuity_seed,
            model=self.model())
        return GeneratedAsset(video, self.model(), "video")


_REGISTRY: dict[str, ProviderAdapter] = {
    "flux": FluxAdapter(),
    "stable_diffusion": StableDiffusionAdapter(),
    "wan": WanAdapter(),
}


def register_provider(adapter: ProviderAdapter) -> None:
    """Plug-in point for future providers and local test adapters."""
    _REGISTRY[adapter.name] = adapter


def provider_order() -> tuple[str, ...]:
    configured = tuple(name.strip() for name in
                       settings().ai_broll_provider_priority.split(",")
                       if name.strip())
    return configured or tuple(_REGISTRY)


def select_providers() -> list[ProviderAdapter]:
    return [adapter for name in provider_order()
            if (adapter := _REGISTRY.get(name)) is not None and adapter.available()]


def _continuity_seed(graph: SceneGraph) -> int:
    return int(hashlib.sha256(
        f"ai-broll:{graph.meta.video_id}:{graph.brand_id}".encode()
    ).hexdigest()[:8], 16)


def _unsafe_real_person(beat: StoryboardScene) -> bool:
    text = beat.narration.lower()
    roles = (" ceo ", " president ", " founder ", " senator ", " billionaire ")
    known = ("warren buffett", "elon musk", "jerome powell", "donald trump",
             "joe biden", "jamie dimon")
    return any(role in f" {text} " for role in roles) or any(name in text for name in known)


def _evidence_fabrication_risk(beat: StoryboardScene) -> bool:
    text = beat.narration.lower()
    return any(term in text for term in (
        "archival photo", "historical photograph", "leaked document",
        "sec filing", "annual report", "official document", "evidence photo"))


def prompt_spec(graph: SceneGraph, scene: Scene,
                beat: StoryboardScene) -> AICinematicSpec:
    """Turn validated storyboard facts into a complete cinematic brief."""
    beat = StoryboardScene.model_validate(beat.model_dump())
    theme = theme_for(graph, "ai_broll")
    seed = _continuity_seed(graph)
    lenses = ("35mm", "50mm", "40mm anamorphic")
    angles = ("eye-level documentary medium shot", "low-angle wide establishing shot",
              "high-angle observational wide shot")
    lighting = ("soft directional window light with restrained practicals",
                "golden-hour side light with deep navy shadows",
                "cool newsroom key light with warm practical accents")
    movement = ("slow controlled dolly-in", "subtle lateral tracking move",
                "locked tripod frame with gentle atmospheric motion")
    index = seed % len(lenses)
    facts = " ".join(filter(None, [beat.company, beat.primary_entity,
        *beat.secondary_entities, beat.location, str(beat.year or ""),
        *beat.financial_numbers]))
    subject = beat.visual_objective or beat.narration
    prompt = (
        f"Original documentary B-roll illustrating: {subject}. "
        f"Narration facts: {facts or beat.narration}. No on-screen text. "
        "Show an editorially honest symbolic or environmental interpretation, "
        "not fabricated evidence. Vertical mobile composition with one clear subject."
    )
    negative = (
        "text, captions, watermark, logo, fake document, fabricated evidence, "
        "celebrity likeness, identifiable real-person face, distorted hands, "
        "uncanny skin, CGI, cartoon, oversaturated colors, clutter, low resolution"
    )
    return AICinematicSpec(
        cinematic_prompt=prompt, negative_prompt=negative,
        camera_angle=angles[index], focal_length=lenses[index],
        lighting=lighting[index], color_palette=[
            theme.hex("bg"), theme.hex("bg_soft"), theme.hex("primary"),
            theme.hex("secondary"), theme.hex("ink")],
        composition="single readable foreground subject, negative space for captions",
        movement=movement[index], mood=beat.emotion,
        realism_level="photorealistic", continuity_seed=seed,
        brand_style=f"{theme.name}: {theme.tagline}", duration=scene.duration_sec,
        aspect_ratio="9:16")


def cache_key(prompt: AICinematicSpec, provider: str, model: str,
              quality: str) -> str:
    body = json.dumps({"prompt": prompt.model_dump(mode="json"),
                       "provider": provider, "model": model,
                       "seed": prompt.continuity_seed,
                       "duration": prompt.duration, "quality": quality},
                      sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(body.encode()).hexdigest()


async def generate(graph: SceneGraph, scene: Scene, beat: StoryboardScene,
                   quality: str | None = None) -> AIBrollRenderProvenance:
    """Dispatch one eligible beat across adapters; provenance exists on failure."""
    beat = StoryboardScene.model_validate(beat.model_dump())
    if not beat.ai_broll_candidate:
        raise ValueError("storyboard beat is not an AI B-roll candidate")
    quality = quality or settings().ai_broll_quality
    quality = quality if quality in ("preview", "final") else "final"
    prompt_started = time.perf_counter()
    prompt = prompt_spec(graph, scene, beat)
    prompt_ms = (time.perf_counter() - prompt_started) * 1000
    adapters = select_providers()
    adapter = adapters[0] if adapters else None
    provider_name = adapter.name if adapter else "none"
    model = adapter.model() if adapter else "none"
    key = cache_key(prompt, provider_name, model, quality)
    base = dict(scene_id=scene.id, storyboard_scene_id=beat.scene_id,
                provider=provider_name, model=model, asset_type="image",
                cache_key=key, prompt_spec=prompt, quality=quality,
                prompt_generation_ms=prompt_ms, peak_rss_mb=0,
                selection_reason="Official and explanatory visual tiers were unresolved.")
    if _unsafe_real_person(beat):
        return AIBrollRenderProvenance(**base, status="rejected",
            provider_dispatch_ms=0, error="real-person likeness requires supported legal assets")
    if _evidence_fabrication_risk(beat):
        return AIBrollRenderProvenance(**base, status="rejected",
            provider_dispatch_ms=0, error="AI may not fabricate historical evidence or documents")
    if adapter is None:
        return AIBrollRenderProvenance(**base, status="unresolved",
            provider_dispatch_ms=0, error="no configured AI B-roll provider is available")
    root = settings().data_dir / "cache" / "ai_broll" / key
    for ext, asset_type in (("mp4", "video"), ("png", "image"), ("jpg", "image")):
        cached = root / f"render.{ext}"
        if cached.is_file() and cached.stat().st_size:
            return AIBrollRenderProvenance(**{**base, "asset_type": asset_type},
                status="cache_hit", render_path=str(cached), provider_dispatch_ms=0)
    started = time.perf_counter()
    errors: list[str] = []
    for candidate in adapters:
        provider_name, model = candidate.name, candidate.model()
        key = cache_key(prompt, provider_name, model, quality)
        root = settings().data_dir / "cache" / "ai_broll" / key
        for ext, asset_type in (("mp4", "video"), ("png", "image"),
                                ("jpg", "image"), ("jpeg", "image")):
            cached = root / f"render.{ext}"
            if cached.is_file() and cached.stat().st_size:
                return AIBrollRenderProvenance(
                    scene_id=scene.id, storyboard_scene_id=beat.scene_id,
                    status="cache_hit", provider=provider_name, model=model,
                    asset_type=asset_type, render_path=str(cached), cache_key=key,
                    prompt_spec=prompt, quality=quality,
                    prompt_generation_ms=prompt_ms, provider_dispatch_ms=0,
                    peak_rss_mb=0,
                    selection_reason="Official and explanatory visual tiers were unresolved.")
        try:
            generated = await asyncio.wait_for(
                candidate.generate(prompt, scene, quality),
                timeout=settings().ai_broll_timeout_s,
            )
            source = Path(generated.path)
            if not source.is_file() or not source.stat().st_size:
                raise RuntimeError("provider returned a missing or empty asset")
            suffix = ".mp4" if generated.asset_type == "video" else \
                (source.suffix.lower() if source.suffix.lower() in (".png", ".jpg", ".jpeg") else ".png")
            output = root / f"render{suffix}"
            output.parent.mkdir(parents=True, exist_ok=True)
            if source.resolve() != output.resolve():
                shutil.copy2(source, output)
            rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
            return AIBrollRenderProvenance(
                scene_id=scene.id, storyboard_scene_id=beat.scene_id,
                status="rendered", provider=provider_name, model=generated.model,
                asset_type=generated.asset_type, render_path=str(output),
                cache_key=key, prompt_spec=prompt, quality=quality,
                prompt_generation_ms=prompt_ms,
                provider_dispatch_ms=(time.perf_counter() - started) * 1000,
                peak_rss_mb=rss,
                selection_reason="Official and explanatory visual tiers were unresolved.")
        except Exception as exc:  # provider isolation; try the next adapter
            errors.append(f"{candidate.name}: {type(exc).__name__}: {str(exc)[:120]}")
    return AIBrollRenderProvenance(**{**base, "peak_rss_mb":
        resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024}, status="unresolved",
        provider_dispatch_ms=(time.perf_counter() - started) * 1000,
        error="; ".join(errors))
