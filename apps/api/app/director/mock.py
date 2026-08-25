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
        if "high-frequency trading" in topic.lower() or "hft" in topic.lower():
            return _hft_graph(spec)
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


def _hft_graph(spec: VideoSpec) -> SceneGraph:
    """Deterministic offline fixture for the approved HFT smoke topic."""
    return SceneGraph(
        meta=SceneMeta(
            video_id=spec.id,
            channel_id=spec.channel_id,
            niche=spec.niche.value,
            title="What is High-Frequency Trading (HFT)?",
            hook="Trades faster than a blink?",
            description="A beginner-friendly explanation of high-frequency trading.",
            tags=["high-frequency trading", "HFT", "finance", "trading"],
            hashtags=["#HFT", "#Trading", "#Shorts"],
        ),
        fps=spec.render.fps, width=spec.render.width, height=spec.render.height,
        scenes=[
            Scene(
                id="s1",
                narration="High-frequency trading can buy and sell in less time than it takes you to blink.",
                duration_sec=5.0,
                visual=Visual(type="broll", query="electronic trading screens",
                              scene_visual_type="dramatic", motion="zoom_in",
                              broll_keywords=["electronic trading screens", "data center"]),
                overlays=[Overlay(type="headline", text="Faster than a blink?",
                                  emphasis="alert", y=0.16)],
                transition_in="fade",
            ),
            Scene(
                id="s2",
                narration="HFT uses powerful computers and algorithms to place huge numbers of orders at extremely high speed.",
                duration_sec=6.0,
                visual=Visual(type="manim", query="orders moving through an exchange",
                              scene_visual_type="data_viz"),
                overlays=[Overlay(type="headline", text="Computers + algorithms",
                                  y=0.18)],
            ),
            Scene(
                id="s3",
                narration="Those algorithms scan prices across markets, spot tiny differences, and react in fractions of a second.",
                duration_sec=6.0,
                visual=Visual(type="broll", query="market data network",
                              scene_visual_type="real_footage",
                              broll_keywords=["server room", "stock exchange data"]),
                overlays=[Overlay(type="headline", text="Scan. Spot. React.",
                                  emphasis="positive", y=0.18)],
            ),
            Scene(
                id="s4",
                narration="The goal is often a very small gain on each trade, repeated many times. Speed and infrastructure create the edge.",
                duration_sec=7.0,
                visual=Visual(type="manim", query="small repeated market movements",
                              scene_visual_type="data_viz"),
                overlays=[Overlay(type="headline", text="Tiny moves, many trades",
                                  y=0.18)],
            ),
            Scene(
                id="s5",
                narration="HFT can add liquidity, but critics say it may increase short-term volatility. This is education, not financial advice.",
                duration_sec=7.0,
                visual=Visual(type="broll", query="calm financial market screens",
                              scene_visual_type="subtle", motion="ken_burns",
                              broll_keywords=["financial market screens", "city skyline"]),
                overlays=[Overlay(type="headline", text="Benefits and trade-offs",
                                  y=0.18)],
            ),
            Scene(
                id="s6",
                narration="Follow for more AI and Trading insights.",
                duration_sec=3.0,
                visual=Visual(type="solid", query="", scene_visual_type="subtle",
                              fallback_color="#15233a"),
                overlays=[Overlay(type="headline",
                                  text="Follow for more AI and Trading insights.",
                                  emphasis="alert", y=0.40)],
                transition_in="slide_l",
            ),
        ],
    )
