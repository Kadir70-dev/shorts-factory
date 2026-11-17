"""
Original on-screen copy and upload metadata — deterministic, no LLM required.

Every line is a template written for this channel, filled per concept and
rotated through the existing cross-upload rotation ledger (app/state.py) so the
same hook or caption doesn't repeat on consecutive uploads. A human edits any of
it in the concept JSON before approval; nothing here is final until approved.
"""
from __future__ import annotations

import random

from .. import state

TITLES = {
    "funny_fails": ["Top 5 Fails Nobody Saw Coming", "5 Fails That Went Wrong Fast",
                    "Top 5 Most Painful Fails", "5 Fails You Can't Unsee"],
    "unexpected": ["Top 5 Most Unexpected Moments", "5 Moments That Took a Turn",
                   "Top 5 Plot Twists in Real Life", "5 Times Nobody Was Ready"],
    "animals": ["Top 5 Animals Who Chose Chaos", "5 Animals With Zero Chill",
                "Top 5 Funniest Animal Moments", "5 Pets Who Did Too Much"],
    "pranks": ["Top 5 Pranks That Went Too Far", "5 Pranks Nobody Expected",
               "Top 5 Best Reactions to Pranks", "5 Pranks With a Perfect Payoff"],
    "sports": ["Top 5 Craziest Sports Moments", "5 Plays Nobody Saw Coming",
               "Top 5 Unreal Sports Moments", "5 Times Sports Got Weird"],
    "reactions": ["Top 5 Craziest Reactions", "5 Reactions That Say It All",
                  "Top 5 Most Priceless Reactions", "5 Reactions You'll Feel"],
}
HOOKS = ["WAIT FOR #1", "#1 IS UNREAL", "DON'T SKIP #1", "#1 GOT ME",
         "STAY FOR #1", "#1 IS INSANE"]
CAPTIONS = {
    5: ["Warming up...", "Okay, that's a start", "Just the opener", "Easy one first"],
    4: ["It escalates", "Didn't see that", "Getting worse", "Hold on..."],
    3: ["Now we're talking", "That timing though", "Zero hesitation", "Bold move"],
    2: ["Absolutely not", "How?!", "Instant regret", "Nobody was ready"],
    1: ["THE LEGEND", "PURE CHAOS", "UNMATCHED", "NO WORDS"],
}
OUTROS = ["Which one got you?", "Rank them in the comments", "Your #1 was?",
          "Did we get the order right?"]
# Subject-aware lines ({s} = "goose", {S} = "Goose"). Used when the moment's
# subject is known from its label/title; the generic lines above otherwise.
CONTEXT = {
    5: ["{S} is just warming up", "Okay {s}, we see you", "The {s} had a plan. Sort of.",
        "A gentle start from the {s}"],
    4: ["The {s} chose chaos", "Nobody warned the {s}", "{S} said: watch this",
        "This {s} has zero chill"],
    3: ["{S} with the bold move", "The {s} did not think this through",
        "Confidence of a {s}", "That {s} is unhinged"],
    2: ["Absolutely not, {s}", "{S} speedrunning trouble", "The {s} went too far",
        "Why is the {s} like this"],
    1: ["The {s} is the final boss", "Legendary {s} behavior", "Nobody beats this {s}",
        "{S} of the year"],
}
CONTEXT_HOOKS = ["WAIT FOR THE {S}", "STAY FOR THE {S}", "THE {S} AT #1 THO", "#1 {S} IS UNREAL"]
CONTEXT_TITLES = ["Top 5 {P} With Zero Chill", "5 {P} Who Chose Chaos",
                  "Top 5 {P} Who Had One Job", "Ranking 5 Unhinged {P}"]
PLURAL = {"goose": "geese", "sheep": "sheep", "puppy": "puppies", "bunny": "bunnies",
          "mouse": "mice", "fish": "fish"}
# Visual treatments rotate between uploads: same layout and type, different
# accent pairing, so a run of uploads doesn't look like one template.
TREATMENTS = {
    "red_yellow": {"primary": "#e11d2a", "accent": "#ffd400", "accent_ink": "#111111"},
    "blue_lime": {"primary": "#1d4ed8", "accent": "#b6f400", "accent_ink": "#0b1020"},
    "purple_orange": {"primary": "#7c3aed", "accent": "#ff8a00", "accent_ink": "#140a24"},
}

HASHTAGS = {
    "funny_fails": ["#fails", "#funnyfails", "#failarmy"],
    "unexpected": ["#unexpected", "#wait", "#plottwist"],
    "animals": ["#animals", "#funnyanimals", "#pets"],
    "pranks": ["#pranks", "#prank", "#reaction"],
    "sports": ["#sports", "#sportsmoments", "#crazyplays"],
    "reactions": ["#reaction", "#funnyreactions", "#priceless"],
}
CATEGORY_WORDS = {
    "funny_fails": "fails", "unexpected": "unexpected moments",
    "animals": "animal moments", "pranks": "pranks", "sports": "sports moments",
    "reactions": "reactions",
}


def _pick(channel: str, dimension: str, options: list[str], rng: random.Random) -> str:
    """Weighted away from recent picks via the shared rotation ledger."""
    weights = state.cooldown_weights(options, state.recent(channel, dimension))
    return rng.choices(options, weights=[weights[o] for o in options], k=1)[0]


def _plural(s: str) -> str:
    return PLURAL.get(s, s + "s")


def concept_copy(channel: str, category: str, seed: int, *,
                 subjects: dict[int, str] | None = None, labels: dict[int, str] | None = None,
                 writer: str = "template") -> dict:
    """Title, hook, per-rank captions and outro. Subject-aware when the
    moments' subjects are known; `writer="claude"` asks the local Claude CLI for
    original lines and falls back to these templates on any failure."""
    subjects = {int(k): v for k, v in (subjects or {}).items()}
    if writer == "claude":
        from . import copywriter
        got = copywriter.write(category, subjects, labels or {})
        if got:
            return got
    rng = random.Random(seed)
    known = [v for v in subjects.values() if v]
    top = max(set(known), key=known.count) if known else ""
    if top and known.count(top) >= 3:
        title = _pick(channel, "rank_title_ctx", CONTEXT_TITLES, rng).format(
            P=_plural(top).title())
    else:
        title = _pick(channel, f"rank_title_{category}", TITLES[category], rng)
    s1 = subjects.get(1, "")
    hook = (_pick(channel, "rank_hook_ctx", CONTEXT_HOOKS, rng).format(S=s1.upper())
            if s1 else _pick(channel, "rank_hook", HOOKS, rng))
    captions = {}
    for r in (5, 4, 3, 2, 1):
        sub = subjects.get(r, "")
        if sub:
            line = _pick(channel, f"rank_ctx_{r}", CONTEXT[r], rng)
            captions[r] = line.format(s=sub, S=sub.capitalize())
        else:
            captions[r] = _pick(channel, f"rank_caption_{r}", CAPTIONS[r], rng)
    outro = _pick(channel, "rank_outro", OUTROS, rng)
    return {"title": title, "hook": hook, "captions": captions, "outro": outro,
            "writer": "template"}


def treatment(channel: str, seed: int) -> dict:
    rng = random.Random(seed * 7 + 1)
    name = _pick(channel, "rank_treatment", list(TREATMENTS), rng)
    state.record(channel, "rank_treatment", name)
    return {"name": name, **TREATMENTS[name]}


def record_copy(channel: str, category: str, copy: dict) -> None:
    picks = {f"rank_title_{category}": copy["title"], "rank_hook": copy["hook"],
             "rank_outro": copy["outro"]}
    picks.update({f"rank_caption_{r}": c for r, c in copy["captions"].items()})
    state.record_many(channel, picks)


def metadata(concept: dict, channel_cfg: dict) -> dict:
    """YouTube metadata. Credits are mandatory for attribution licenses and are
    placed above the hashtags so they're visible without expanding."""
    p = concept["payload"]
    cat = concept["category"]
    words = CATEGORY_WORDS[cat]
    tags_cat = HASHTAGS[cat]
    hashtags = (tags_cat[:2] + ["#top5", "#shorts"])[:5]
    credits = sorted({c for c in (r.get("attribution", "") for r in p["ranks"]) if c})
    lines = [f"Counting down the 5 best {words} — stay for #1.",
             "", channel_cfg.get("cta", "Follow for a new Top 5 every day.")]
    if credits:
        lines += ["", "Credits:"] + [f"• {c}" for c in credits]
    lines += ["", " ".join(hashtags)]
    title = p["copy"]["title"]
    if len(title) + 8 <= 100:
        title = f"{title} #shorts"
    return {
        "title": title[:100],
        "description": "\n".join(lines)[:5000],
        "tags": ["top 5", words, "funny", "shorts", "countdown"] +
                [h.lstrip("#") for h in tags_cat],
        "hashtags": hashtags,
        "category_id": channel_cfg.get("youtube", {}).get("category_id", "23"),
        "made_for_kids": False,
        "default_language": "en-US",
        "contains_synthetic_media": False,
    }
