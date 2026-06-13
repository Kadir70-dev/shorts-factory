"""
Offline Director. Produces a valid SceneGraph from a template WITHOUT calling
Claude. Used for: pipeline testing with zero API keys, CI, and local smoke runs.

Toggle with env DIRECTOR_MODE=mock (see director/__init__.py factory).
The shape it returns is byte-identical to what the real Director emits, so every
downstream stage (TTS/captions/assets/render) is exercised truthfully.
"""
from __future__ import annotations

from ..config import ChannelConfig
from ..schemas.scene import Overlay, Scene, SceneGraph, SceneMeta, Visual
from ..schemas.video_spec import VideoSpec


class MockDirector:
    def __init__(self, channel: ChannelConfig):
        self.channel = channel

    async def build_scene_graph(self, spec: VideoSpec) -> SceneGraph:
        topic = spec.topic.replace("__trending__:", "").split(":")[0] or "today's story"
        return SceneGraph(
            meta=SceneMeta(
                video_id=spec.id,
                channel_id=spec.channel_id,
                niche=spec.niche.value,
                title=f"{topic.title()} — explained in 30s",
                hook=f"Here's what {topic} actually means.",
            ),
            fps=spec.render.fps,
            width=spec.render.width,
            height=spec.render.height,
            scenes=[
                Scene(
                    id="s1",
                    narration=f"Let's break down {topic}, in thirty seconds.",
                    duration_sec=3.2,
                    visual=Visual(
                        type="broll", query=topic, motion="zoom_in",
                        scene_visual_type="dramatic",
                        visual_intent=f"dramatic opener on {topic}",
                        broll_keywords=["gas station", "grocery shopping",
                                        "stock market", topic],
                    ),
                    overlays=[Overlay(type="headline", text=topic.title(),
                                      emphasis="alert", y=0.16)],
                    transition_in="fade",
                ),
                Scene(
                    id="s2",
                    narration="The number everyone is watching jumped sharply this week.",
                    duration_sec=4.0,
                    visual=Visual(
                        type="manim", query=f"line chart trend of {topic}",
                        scene_visual_type="data_viz",
                        visual_intent="the trend spiking on a chart",
                        broll_keywords=["stock market", "trading floor",
                                        "economy charts"],
                    ),
                    overlays=[Overlay(type="stat", text="vs last month",
                                      sub="+3.4%", emphasis="negative", y=0.30)],
                ),
                Scene(
                    id="s3",
                    narration="Here's the part that actually affects your wallet.",
                    duration_sec=3.6,
                    visual=Visual(
                        type="broll", query=f"{topic} impact people", motion="pan_lr",
                        scene_visual_type="real_footage",
                        visual_intent="ordinary people feeling the pinch",
                        broll_keywords=["worried customers", "grocery checkout",
                                        "paying bills"],
                    ),
                    overlays=[Overlay(type="headline", text="Why it matters", y=0.18)],
                ),
                Scene(
                    id="s4",
                    narration=f"And that's the real story to watch. {self.channel.cta}",
                    duration_sec=4.2,
                    visual=Visual(
                        type="broll", query="city skyline calm",
                        scene_visual_type="subtle", motion="ken_burns",
                        visual_intent="calm closing skyline behind the CTA",
                        broll_keywords=["city skyline", "american flag",
                                        "sunrise time lapse"],
                        fallback_color=self.channel.brand.primary_color,
                    ),
                    overlays=[Overlay(type="headline", text=self.channel.cta,
                                      emphasis="alert", y=0.40)],
                    transition_in="slide_l",
                ),
            ],
        )
