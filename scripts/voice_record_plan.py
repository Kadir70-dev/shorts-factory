#!/usr/bin/env python3
"""
Generate the recording script for cloning your narration voice.

A voice clone is only as good as its source session, and the failure mode is
always the same: 25 minutes of audio that all sounds the same, so the model
learns one cadence and every video afterwards sounds like a man reading a list.

This builds a session that avoids that, in four blocks:

  1. PHONETIC COVERAGE  — sentences chosen so every English phoneme and the
     common consonant clusters appear several times. This is what stops specific
     words coming out mangled later.
  2. DOMAIN DRILLS      — the vocabulary this channel actually says: tickers,
     agencies, percentages, magnitudes, years. If "CPI" and "basis points" never
     appear in the training audio, the clone guesses at them forever.
  3. PROSODY RANGE      — the same content delivered as hook, explanation, reveal
     and close. This is the block that gives the clone more than one gear.
  4. LONG FORM          — unbroken 60–90 second passages. Short clips alone teach
     a model to sound clipped; sustained reading teaches natural breath and
     phrase-level rhythm.

    python scripts/voice_record_plan.py --identity k70_host_v1 --minutes 25

Writes data/voice/<identity>/script/ with one .txt per take, a printable
SESSION.md, and a manifest the dataset builder reads back.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Words per minute when reading aloud at documentary pace, used to size the
# session. Deliberately conservative: over-running the target is harmless,
# under-running it costs clone quality.
WPM = 135

# --------------------------------------------------------------------------- #
# Block 1 — phonetic coverage
# --------------------------------------------------------------------------- #
PHONETIC = [
    "The quick brown fox jumps over the lazy dog while the judge watches.",
    "She sells sea shells by the shore, and the shrill wind shifts them.",
    "Three thin thieves thought they thrilled the throne room.",
    "Vivid violet vines were viewed favourably by every visitor.",
    "The zoo's zebras zigzagged as the buzzing bees crossed the lawn.",
    "Charles chose a cheap chair, then changed his mind and chuckled.",
    "Measure the beige garage azure, said the usual visionary.",
    "Ring the long strong gong, and the singer will bring something.",
    "Whether the weather is warm or wet, we will walk the whole way.",
    "A rural jury ruled the railway repairs were rarely worth rushing.",
    "Bright lights blinked behind the black bricks of the old building.",
    "Twelve tall trucks travelled straight through the crowded street.",
    "He asked her to answer honestly about the awkward hourly arrangement.",
    "Splendid strategists sprint past sprawling springs in spring.",
    "The film's plot pulled apart, but the people applauded politely.",
    "Our house on the mountain now allows loud crowds around it.",
    "Joy and boys enjoyed the noisy oyster boil by the point.",
    "Few beautiful cured views amused the curious student community.",
    "Not a single soldier could hold the older, colder shoulder.",
    "Isn't it odd that a hard heart hardly ever hears anything?",
    "Exactly six exhausted experts examined the extra exhibits.",
    "The government's judgement encouraged an enormous engagement.",
    "Comfortable, vegetable, temperature, laboratory, February, library.",
    "Particularly, regularly, similarly, necessarily, extraordinarily.",
]

# --------------------------------------------------------------------------- #
# Block 2 — the vocabulary this channel actually speaks
# --------------------------------------------------------------------------- #
DOMAIN = [
    "The Consumer Price Index rose three point four percent year over year.",
    "According to the Bureau of Labor Statistics, unemployment held at four point one percent.",
    "The Federal Reserve cut rates by twenty-five basis points at the March meeting.",
    "Core P C E inflation cooled to two point six percent, the lowest since twenty twenty-one.",
    "The S and P five hundred closed at five thousand two hundred and eleven.",
    "Nasdaq futures slipped, while the Dow added one hundred and forty points.",
    "The company reported four point two billion dollars in quarterly revenue.",
    "Operating margin expanded from eleven percent to nineteen percent in three years.",
    "Median household income reached seventy-four thousand five hundred and eighty dollars.",
    "The median home price climbed from two hundred seventy-four thousand to four hundred nineteen thousand.",
    "Treasury yields on the ten year note touched four point six eight percent.",
    "West Texas Intermediate crude settled near seventy-eight dollars a barrel.",
    "The Congressional Budget Office projects a one point nine trillion dollar deficit.",
    "In its ten K filing, the company disclosed a two hundred million dollar write-down.",
    "Earnings per share came in at three dollars and eleven cents, beating estimates.",
    "The merger was valued at sixty-eight billion dollars, subject to regulatory review.",
    "Analysts at Goldman Sachs and Morgan Stanley raised their forecasts.",
    "The S E C opened an inquiry; the F D I C took control of the bank.",
    "Between nineteen eighty and two thousand and eight, the ratio tripled.",
    "By the nineteen nineties, that share had fallen to under twelve percent.",
    "Quarterly revenue grew nine percent in Q one and fourteen percent in Q three.",
    "Return on invested capital averaged twenty-two percent over the decade.",
    "That is a compound annual growth rate of just over seven percent.",
    "Roughly fifty-nine percent of American adults have under one thousand dollars saved.",
    "The top ten holdings now make up thirty-seven percent of the entire index.",
    "It traded at a price to earnings ratio of thirty-one, versus a historical average of sixteen.",
    "Household debt reached seventeen point five trillion dollars in the fourth quarter.",
    "The E C B held rates while the Bank of England signalled a pause.",
    "Free cash flow doubled from one point one billion to two point three billion dollars.",
    "Same-store sales grew six point two percent, ahead of the four percent consensus.",
    "Its market capitalisation crossed three trillion dollars for the first time.",
    "The I R S collected four point nine trillion dollars in gross receipts.",
    "Thirty-year fixed mortgage rates averaged six point eight seven percent.",
    "Retail inventories rose two point one percent month over month.",
    "The unemployment rate among twenty-five to fifty-four year olds fell to three point three percent.",
    "Buybacks totalled nine hundred and twenty-three billion dollars across the S and P five hundred.",
    "Gross margin held at forty-six percent despite the twelve percent rise in input costs.",
    "That works out to about one hundred and eighty dollars per household, per year.",
    "The ratio moved from zero point eight to one point four over eighteen months.",
    "Between two thousand and seven and two thousand and nine, it fell fifty-seven percent.",
]

# --------------------------------------------------------------------------- #
# Block 3 — prosody range: the same register the pipeline will ask for
# --------------------------------------------------------------------------- #
PROSODY = [
    ("hook", "Costco has sold the same hot dog for the same price since nineteen eighty-five."),
    ("hook", "Three numbers explain why this collapsed, and none of them were secret."),
    ("hook", "Everyone believes this is true. The data says the opposite."),
    ("hook", "There is a reason nobody talks about what happened next."),
    ("explain", "Here is how the mechanism actually works, step by step, from the beginning."),
    ("explain", "The company was not selling the product. It was buying something else entirely."),
    ("explain", "To understand why, you have to look at what the incentives rewarded."),
    ("explain", "It comes down to a single line buried in the regulatory filing."),
    ("reveal", "And that is when the whole thing turned around."),
    ("reveal", "The number was not wrong. It was measuring something else."),
    ("reveal", "That single decision cost them the entire market."),
    ("reveal", "What they were really building was a moat nobody could cross."),
    ("close", "The lesson is simple, and it applies far beyond this one company."),
    ("close", "Watch that number. It tells you what happens next."),
    ("close", "Follow for more of the systems behind the headlines."),
    ("close", "That is how a small advantage compounds into an unassailable one."),
]

# --------------------------------------------------------------------------- #
# Block 4 — sustained reading (natural breath and phrase rhythm)
# --------------------------------------------------------------------------- #
LONGFORM = [
    """In nineteen eighty-five, Costco began selling a hot dog and a soda for one
    dollar and fifty cents. Four decades later, the price has not moved. Inflation
    over that period ran to roughly two hundred and ninety percent, which means the
    real price of that hot dog has fallen by nearly three quarters. The company
    loses money on every one it sells, and it sells more than a hundred million of
    them a year. That looks like a mistake until you understand what the hot dog is
    for. It is not a product. It is the last thing a member sees on the way out,
    and it is the reason ninety-two percent of them renew.""",

    """The Federal Reserve has two jobs that frequently disagree with each other.
    It is asked to keep prices stable and to keep employment high, and in most
    economic conditions, pushing on one of those pulls against the other. When
    inflation runs hot, the standard response is to raise interest rates, which
    slows borrowing, slows hiring, and cools demand. The trouble is that the effect
    arrives late. Rate changes take somewhere between six and eighteen months to
    work through the real economy, so the committee is always steering a car whose
    windscreen shows the road it drove last year.""",

    """Between two thousand and twenty and two thousand and twenty-two, the American
    consumer price index rose from one point four percent to eight percent, the
    fastest acceleration in four decades. Economists disagreed sharply about the
    cause. Some pointed to supply chains that had not recovered from the pandemic.
    Others pointed to fiscal stimulus, to energy markets, or to a labour force that
    had simply not returned. The honest answer is that all of them contributed, in
    proportions that are still being argued over, and that anyone claiming a single
    cause is selling something.""",

    """Every business has a story it tells about itself and a story its balance
    sheet tells. Usually they roughly agree. Occasionally they diverge so far that
    the gap becomes the whole story. A company can grow revenue every quarter for a
    decade and still be destroying value, if each new dollar of sales costs more
    than a dollar to acquire. The market can take a very long time to notice this.
    It notices all at once. What follows is rarely a gentle correction. It is a
    repricing, and it happens in the space of a single earnings call, because the
    information was always available and nobody wanted to be the first to act on
    it.""",

    """There is a particular kind of business that looks unprofitable right up
    until you understand what it is actually selling. A grocery chain that loses
    money on milk is not bad at pricing milk. It has worked out that milk is at the
    back of the store, and that the walk to the back of the store passes everything
    else. The loss on the milk buys the walk. Once you start looking for this
    pattern you find it everywhere: the cheap printer and the expensive ink, the
    free checking account and the overdraft fee, the two-day shipping that only
    makes sense if it changes how often you order. In each case the visible price
    is not the product. It is the entry fee for a relationship that pays for itself
    many times over.""",

    """The most expensive assumption in finance is that the past distribution of
    outcomes describes the future one. It usually does, which is exactly what makes
    it dangerous. A model calibrated on thirty years of data will be right almost
    every day, and the days it is wrong will be the days that matter. This is not
    an argument against models. It is an argument for knowing which of your
    assumptions are load-bearing. Before two thousand and eight, a great many
    institutions held positions that were safe under every scenario they had
    modelled, and catastrophic under one they had not. The scenario was not exotic.
    It was that house prices could fall nationally at the same time.""",

    """Compounding is described so often that the description has stopped landing.
    So here is the version with numbers in it. A business earning a twenty percent
    return on capital, reinvesting all of it, doubles roughly every four years. Over
    twenty years that is a factor of thirty-two. A business earning ten percent
    doubles every seven, which over the same twenty years is a factor of about six.
    The gap between those two businesses is not two to one, matching the difference
    in their returns. It is five to one, and it widens every year the clock runs.
    This is why durable advantage is worth so much more than a good quarter, and
    why the market pays such extraordinary multiples for it.""",

    """When a government borrows in a currency it issues itself, the constraint is
    not that it will run out of money. The constraint is inflation, and the
    exchange rate, and eventually the price it has to pay to keep finding lenders.
    Those are real constraints, and they bind hard, but they bind differently from
    the way a household budget binds. Confusing the two produces a great deal of
    confident commentary that turns out to be wrong in both directions. The useful
    questions are narrower: what is the debt being spent on, does it grow the
    economy faster than it grows the interest bill, and who holds it.""",

    """A monopoly rarely looks like a monopoly from the inside. It looks like a
    company with unusually happy customers, unusually good margins, and a
    competitive landscape that keeps failing to produce a serious competitor. The
    company's own explanation is always that it is simply better at the job, and
    quite often that is even true. What makes it a monopoly is not the quality. It
    is that a new entrant doing everything right would still lose, because the
    advantage sits in something other than the product: a distribution agreement, a
    default setting, a network that gets more valuable with every user, a switching
    cost paid in years of accumulated data.""",

    """The problem with forecasting interest rates is that the people setting them
    are also forecasting, and they are reacting to the same data you are. This
    makes the whole system reflexive. If everyone expects a cut, markets price the
    cut in advance, financial conditions loosen, and the case for actually cutting
    gets weaker. If nobody expects it, conditions stay tight, and the case gets
    stronger. The result is that being right about the economy and being right
    about rates are two different skills, and the second one is considerably
    harder.""",

    """Survivorship bias is the reason so much business advice is useless. We study
    the companies that made it, extract the practices they had in common, and
    present those practices as the cause. But the companies that failed had many of
    the same practices. What separated them was frequently timing, or capital
    access, or a single customer decision that could have gone either way. This
    does not mean nothing is learnable. It means the honest lesson is usually about
    process rather than outcome: what did they do that improved their odds, as
    opposed to what did they do that happened to precede success.""",

    """An index fund is a strange object when you look at it directly. It has no
    opinion. It buys more of whatever has already gone up, simply because it got
    bigger, and less of whatever has fallen. Described that way it sounds like the
    worst strategy imaginable, and for decades professional investors said exactly
    that. It has nevertheless outperformed most of them, after fees, over almost
    every long period anyone has measured. The reason is not that indexing is
    clever. It is that the costs of being clever, compounded over thirty years,
    exceed the value that most cleverness adds.""",

    """Every large fraud has the same structure underneath the details. There is a
    number that cannot be independently verified, an incentive to keep it high, and
    a period during which nobody with the standing to check has any reason to. The
    fraud is not usually a single decision. It is a series of small
    reclassifications, each of which is defensible on its own, and none of which
    anyone reverses. By the time the gap between the reported number and the real
    one is large enough to be obvious, it is also large enough that admitting it
    ends the company. Which is why these things are almost never confessed. They
    are discovered.""",

    """Productivity statistics are the most consequential numbers almost nobody
    follows. Over a single year they tell you very little; the measurement noise
    swamps the signal. Over thirty years they determine essentially everything
    about how wealthy a country becomes, because output per hour is what wages can
    ultimately be paid out of. The uncomfortable part is that economists do not
    fully agree on what drives them. Technology clearly matters. So does capital
    investment, education, infrastructure, and the ease of moving resources from a
    failing use to a better one. The relative weights are still argued over, which
    is worth remembering whenever someone offers a confident single-lever
    solution.""",

    """The word bubble gets used for two different things and the confusion is
    expensive. Sometimes it means an asset is expensive relative to its history,
    which is a statement about valuation and can persist for a decade. Sometimes it
    means the price is being sustained by the belief that someone else will pay
    more, with no underlying cash flow that could justify it. The first is a reason
    for lower expected returns. The second is a reason for a crash. They look
    similar from the outside, and telling them apart in advance is one of the
    genuinely difficult problems in finance.""",
]


def build(identity: str, minutes: int) -> dict:
    """Assemble takes until the target minutes are covered, keeping block balance."""
    takes: list[dict] = []
    n = 0

    def add(block: str, text: str, note: str = "") -> None:
        nonlocal n
        n += 1
        clean = " ".join(text.split())
        takes.append({"id": f"{n:03d}", "block": block, "note": note,
                      "text": clean, "words": len(clean.split())})

    for t in PHONETIC:
        add("phonetic", t, "Neutral read. Clear, unhurried, no performance.")
    for t in DOMAIN:
        add("domain", t, "Say numbers exactly as written.")
    for tone, t in PROSODY:
        note = {
            "hook": "Punchy. Lean in. This is the first line of a video.",
            "explain": "Calm and measured. You are teaching, not selling.",
            "reveal": "Slight lift. The payoff lands here.",
            "close": "Settle. Warm and certain.",
        }[tone]
        add(f"prosody_{tone}", t, note)
    for t in LONGFORM:
        add("longform", t, "One continuous take. Breathe naturally; do not reset "
                           "between sentences.")

    total_words = sum(t["words"] for t in takes)
    est_minutes = total_words / WPM

    # Top up toward the target with second readings of the long-form passages —
    # sustained reading is the most useful marginal minute for a clone, and a
    # second pass on the same text teaches prosodic variation rather than just
    # more words. Added ONE at a time so a 25-minute request doesn't become a
    # 31-minute session nobody wants to sit through.
    i = 0
    while est_minutes < minutes and i < len(LONGFORM) * 2:
        t = LONGFORM[i % len(LONGFORM)]
        add("longform", t, f"Second reading. Vary the emphasis and phrasing — "
                           "not the character.")
        i += 1
        total_words = sum(x["words"] for x in takes)
        est_minutes = total_words / WPM

    return {"identity": identity, "wpm": WPM, "target_minutes": minutes,
            "estimated_minutes": round(est_minutes, 1),
            "total_words": total_words, "takes": takes}


SESSION_HEADER = """# Voice recording session — {identity}

**{count} takes · ~{minutes} minutes of speech · {words} words**

Record once, use forever. The clone you build from this session narrates every
future Short, so the twenty minutes you spend getting the setup right is the
highest-leverage twenty minutes in this whole pipeline.

## Before you start

**Room.** The single biggest quality factor is not your microphone, it is your
room. Record somewhere with soft furnishings — a bedroom with a wardrobe open, or
under a duvet draped over a chair. You are trying to kill reflections. If you can
clap and hear a ring, the room is too live.

**Mic.** Any decent USB condenser or dynamic mic. Position it a hand's width from
your mouth, slightly off-axis so plosives pass by rather than into it.

**Levels.** Aim for peaks around -6 dBFS. If anything clips, that take is
unusable — the clone will learn the distortion. Leave headroom.

**Settings.** 48 kHz, 24-bit if your interface allows, mono, WAV. No compression,
no EQ, no noise gate, no "voice enhancement". The dataset builder does the
processing, and it cannot undo a gate that swallowed your consonants.

**Consistency.** Record the whole session in ONE sitting if you can, at the same
distance, in the same room, at the same time of day. A clone trained on a voice
that changes halfway through learns the average of two voices.

## How to read

Read as the narrator of a serious documentary. Not a newsreader, not an
advertisement. Calm, certain, interested in the material.

- Leave one second of silence at the start and end of every take.
- If you fluff a line, pause for two seconds and read the whole line again. Keep
  the take; the builder detects and drops the bad attempt.
- Do not smile through it, do not push energy, do not "sound professional". The
  clone copies what you do, including the strain.
- Sip water often. A dry mouth is audible and it accumulates over 25 minutes.

## Recording

Save each take as `<id>.wav` in `data/voice/{identity}/raw/` — the filename must
match the take id below (e.g. `001.wav`).

If you prefer to record continuously into one long file, save it as
`data/voice/{identity}/raw/session.wav` and the builder will split it on silence.

When you are done:

```bash
python scripts/voice_build_dataset.py --identity {identity}
```

---

"""


def write_session(plan: dict, out_dir: Path) -> None:
    script_dir = out_dir / "script"
    script_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "raw").mkdir(parents=True, exist_ok=True)

    lines = [SESSION_HEADER.format(
        identity=plan["identity"], count=len(plan["takes"]),
        minutes=plan["estimated_minutes"], words=plan["total_words"])]

    current_block = None
    for t in plan["takes"]:
        if t["block"] != current_block:
            current_block = t["block"]
            lines.append(f"\n## Block: {current_block}\n")
        lines.append(f"### {t['id']}\n")
        if t["note"]:
            lines.append(f"*{t['note']}*\n")
        lines.append(f"> {t['text']}\n")
        (script_dir / f"{t['id']}.txt").write_text(t["text"] + "\n")

    (out_dir / "SESSION.md").write_text("\n".join(lines))
    (out_dir / "manifest.json").write_text(json.dumps(plan, indent=2))
    # A distraction-free continuous teleprompter. The phonetic warm-up remains
    # in SESSION.md, while this file is finance narration only.
    finance_takes = [t for t in plan["takes"] if t["block"] != "phonetic"]
    teleprompter = "\n\n".join(t["text"] for t in finance_takes) + "\n"
    (out_dir / "RECORDING_SCRIPT.txt").write_text(teleprompter)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--identity", default="k70_host_v1",
                    help="voice identity id (matches config/voice/profile.yaml)")
    ap.add_argument("--minutes", type=int, default=25,
                    help="target minutes of speech (20-30 recommended)")
    args = ap.parse_args()

    if not 10 <= args.minutes <= 90:
        print("✗ --minutes should be between 10 and 90; 20-30 is the sweet spot "
              "for both Piper fine-tuning and an ElevenLabs professional clone.")
        return 1

    plan = build(args.identity, args.minutes)
    out_dir = ROOT / "data" / "voice" / args.identity
    write_session(plan, out_dir)

    print(f"● Recording session for '{args.identity}'")
    print(f"   {len(plan['takes'])} takes · ~{plan['estimated_minutes']} min · "
          f"{plan['total_words']} words")
    blocks: dict[str, int] = {}
    for t in plan["takes"]:
        blocks[t["block"]] = blocks.get(t["block"], 0) + 1
    for b, c in blocks.items():
        print(f"     {b:18} {c:3d} takes")
    print()
    print(f"   📄 read this : {out_dir / 'SESSION.md'}")
    print(f"   🎙  record to : {out_dir / 'raw'}/<id>.wav   (or raw/session.wav)")
    print(f"   ▶  then run  : python scripts/voice_build_dataset.py "
          f"--identity {args.identity}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
