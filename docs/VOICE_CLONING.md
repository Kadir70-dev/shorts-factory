# Cloning your voice

Every Short this pipeline makes will be narrated by you. This is the one-off setup.

---

## Why not Kokoro

Kokoro cannot clone a voice, and no amount of reference audio changes that. It is
a small StyleTTS2-derived model that ships a fixed pack of pre-trained speaker
embeddings — the voices are baked into the weights, and there is no supported
zero-shot cloning or fine-tuning path. It stays in the codebase as a legacy
fallback for the period before your clone exists; it is not part of the target
architecture.

## What replaces it

Two engines, both cloned from the **same recording session**, so a fallback
changes fidelity but never *who is speaking*.

| | Piper fine-tune | ElevenLabs clone |
|---|---|---|
| **Role** | default, every video | premium tier |
| **Licence** | MIT — unrestricted commercial use | licensed on paid plans |
| **Cost per render** | zero | per character |
| **Speed** | faster than real time on CPU | network round-trip |
| **Needs a GPU** | to train once (free Colab); never to run | no |
| **Audio required** | 20–40 min | ~30 min for a professional clone |
| **Quality** | very good | best available |

Piper is the workhorse specifically *because* it is free and local: at thousands
of Shorts, a per-character narration bill is the difference between a viable
channel and an expensive hobby. ElevenLabs is there for when a video is worth
the extra fidelity, and as the tier that runs while you have credits.

Two more are supported and off by default:

- **Chatterbox** (MIT, zero-shot, no training) — good, wants a GPU to be practical.
- **XTTS-v2** — excellent, but ships under Coqui's **non-commercial** model
  licence. The pipeline refuses to put it in the cascade unless you explicitly set
  `acknowledge_noncommercial: true`. Do not use it on a monetised channel.

---

## The setup, end to end

### 1. Get the script

```bash
python scripts/voice_record_plan.py --identity k70_host_v1 --minutes 25
```

Writes `data/voice/k70_host_v1/SESSION.md` — read that file, it contains the
recording guidance. The session is built in four blocks (phonetic coverage,
finance vocabulary, prosody range, long-form passages) because a clone trained on
25 minutes of identical-sounding sentences learns exactly one delivery, and every
video afterwards sounds like a man reading a list.

### 2. Record

Read `SESSION.md`. The short version:

- **The room matters more than the microphone.** Somewhere soft — a bedroom, a
  wardrobe open behind you. If you clap and hear a ring, find another room.
- **48 kHz, mono, WAV, no processing.** No compression, no EQ, no noise gate.
  The dataset builder does the processing and cannot undo a gate that ate your
  consonants.
- **Peaks around −6 dBFS.** Anything that clips is unusable — the clone learns the
  distortion.
- **One sitting, same distance, same room.** A voice that changes halfway through
  trains a clone on the average of two voices.

Save as `data/voice/k70_host_v1/raw/001.wav`, `002.wav`, … matching the take ids.
Or record continuously into `raw/session.wav` and the builder splits it on silence.

### 3. Build the dataset

```bash
python scripts/voice_build_dataset.py --identity k70_host_v1
```

Cleans, trims, normalises and QAs the session, then produces:

- `dataset/` — LJSpeech corpus for Piper fine-tuning
- `reference/` — the three cleanest clips, for zero-shot engines
- `elevenlabs/` — one concatenated file ready to upload
- `QUALITY.md` — **read this**

The quality gate blocks the build if the session has real problems (clipping, poor
signal-to-noise, not enough audio). That is deliberate: re-recording now costs
twenty-five minutes, and a weak clone costs every video you make from here.

### 4. Train the local clone

```bash
python scripts/voice_train_piper.py --identity k70_host_v1
```

With a CUDA GPU it trains locally. Without one — which is the normal case — it
writes a training bundle and a ready-to-run Colab notebook. Free Colab handles a
fine-tune of this size; expect one to three hours, and you can stop early and
still get a usable voice.

Drop the resulting files into `data/models/piper/k70_host_v1/`.

### 5. Optionally add the premium tier

```bash
python scripts/voice_enroll_elevenlabs.py --identity k70_host_v1
# or, with a Creator+ plan and ~30 min of audio:
python scripts/voice_enroll_elevenlabs.py --identity k70_host_v1 --professional
```

Writes the `voice_id` straight into your profile.

### 6. Turn it on

```bash
cp config/voice/profile.example.yaml config/voice/profile.yaml
```

Edit it if needed, then:

```bash
python scripts/voice_verify.py --identity k70_host_v1 --keep
```

This renders the same passage through every configured tier and compares them.
Listen to the output. It also checks that the tiers *agree* on pacing — if
ElevenLabs speaks 30% faster than your Piper clone, viewers hear a different
narrator depending on whether you had credits that day, which defeats the point.

From here every render uses your voice automatically. There is no per-video
switch.

---

## The identity lock

```yaml
locked: true
allow_stock_fallback: false
```

With this set, a render **fails** when no engine can produce your voice, instead
of falling back to a stock narrator.

This is the correct setting, and it is worth being explicit about why. The old
cascade degraded across *different people* — ElevenLabs' Adam, then Kokoro's
am_michael, then Piper's Ryan. For a channel whose brand is your voice, a stranger
reading your script is worse than a failed render, because a failed render is
something you notice and a substituted narrator is something your audience notices
after you have published it.

Set `allow_stock_fallback: true` only as a deliberate temporary measure.

---

## Keeping the voice consistent

Four mechanisms, all in `config/voice/profile.yaml`:

**One speaking rate.** `prosody.speed` applies to every video. Emotion in this
pipeline comes from the writing and the music bed, not from changing how the
narrator sounds. A voice that varies its character between videos is not an
identity.

**A pronunciation lexicon.** Applied *before* synthesis, so both tiers pronounce
things identically:

```yaml
pronunciation:
  lexicon:
    "S&P 500": "S and P five hundred"
    "EBITDA": "ee-bit-dah"
  say_as:
    CPI: "C P I"
```

**Number normalisation.** `$4.2B` becomes "four point two billion dollars",
`2024` becomes "twenty twenty-four", `1980s` becomes "nineteen eighties" — in the
pipeline, not inside each engine, because engines disagree with each other about
number grouping. The *written* form is untouched, so the screen still shows
`$4.2B`.

**A stable identity id.** Bump `k70_host_v1` → `_v2` only for a genuine
re-recording. It is what ties the profile to the dataset on disk.

---

## Adding words the clone gets wrong

When you hear a mispronunciation, add it to the lexicon and re-render — no
retraining:

```yaml
pronunciation:
  lexicon:
    "Nvidia": "en-vid-ia"
    "Powell": "pow-ell"
```

If the same word is wrong across many videos and the lexicon workaround grates,
record ten sentences containing it, add them to the dataset, and re-run the
fine-tune. That is a one-hour job, not a re-record.
