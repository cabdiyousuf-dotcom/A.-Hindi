# vn — Stage 0 meeting note-taker

Records a meeting, transcribes it locally, and turns it into structured notes:
decisions, commitments split by who owns them, open questions, and a follow-up
draft. Command line only, no UI.

This is Stage 0 of a larger plan. The point of Stage 0 is to answer one
question — **are the notes good enough to be worth building an app around?** —
before any effort goes into a menu bar app, a database, or search. Run it on
five real meetings and judge the output.

## The idea it's built on

It records **two separate audio tracks**: your microphone, and whatever your
speakers are playing. Everything on the first track is you; everything on the
second is everyone else. Speaker attribution falls out of which file the audio
came from, so there's no diarization model, no voice enrollment, and nothing to
train. `vn/transcribe.py` transcribes each track independently and interleaves
them by timestamp into a single conversation.

That's the whole trick, and it's why this is a weekend's work instead of a month's.

## Install

**1. ffmpeg**

```bash
brew install ffmpeg          # macOS
sudo apt install ffmpeg      # Debian/Ubuntu
winget install Gyan.FFmpeg   # Windows
```

**2. Python dependencies**

```bash
cd voice-notes
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

The first `vn transcribe` downloads the Whisper weights (~1.5 GB for
`large-v3-turbo`). That happens once.

**3. Your API key**

```bash
cp .env.example .env    # then edit it
```

**4. A loopback device, so the app can hear the other side**

Operating systems don't let an app record system audio directly — you need a
virtual output device that your audio passes through on its way to your ears.
Skip this if you only record in-person meetings; use `--mic-only` for those.

<details>
<summary><b>macOS</b> (BlackHole, free)</summary>

```bash
brew install blackhole-2ch
```

Then, so you can still *hear* the meeting while it's being captured:

1. Open **Audio MIDI Setup** (in `/Applications/Utilities`).
2. Click **+** at the bottom left → **Create Multi-Output Device**.
3. Tick both your real output (headphones or speakers) **and BlackHole 2ch**.
4. Put your real output *first* in the list — it becomes the primary clock —
   and tick **Drift Correction** on BlackHole.
5. Set your Mac's sound output to that Multi-Output Device before a meeting.

One annoyance worth knowing: while a Multi-Output Device is selected, the volume
keys on the keyboard stop working. Change volume in the app itself, or switch
output back afterwards.
</details>

<details>
<summary><b>Linux</b> (PulseAudio / PipeWire — nothing to install)</summary>

Monitor sources already exist. `vn devices` lists them; anything ending in
`.monitor` is the loopback and is picked automatically.
</details>

<details>
<summary><b>Windows</b></summary>

Enable **Stereo Mix** in Sound settings → Recording, if your driver offers it.
If it doesn't, install [VB-CABLE](https://vb-audio.com/Cable/) and select
"CABLE Output" with `--system`.
</details>

Check it worked:

```bash
python3 -m vn devices
```

Your loopback device should be listed and marked `[loopback — this is 'them']`.

## Use it

```bash
# The main loop: record, transcribe, summarize.
python3 -m vn run --title "Budget sync with Ahmed"
#   ... talk ...
#   Ctrl-C to stop. Notes print when it's done.

# In-person, one microphone in the room:
python3 -m vn run --title "Coffee with Sara" --mic-only

# Try it on a meeting you already recorded — the fastest way to judge the output:
python3 -m vn import ~/Downloads/zoom-recording.m4a
```

| Command | What it does |
|---|---|
| `vn devices` | List audio inputs and show what would be recorded |
| `vn run` | Record → transcribe → summarize |
| `vn record` | Record only |
| `vn transcribe [session]` | Transcribe a recording (default: most recent) |
| `vn summarize [session]` | Re-summarize an existing transcript |
| `vn import FILE` | Process an existing audio or video file |
| `vn list` | List sessions |
| `vn prune --dry-run` | Delete raw audio past the retention window |

Every command takes the most recent session when you don't name one, so
`vn summarize` on its own re-runs the last meeting — which is what you'll do
constantly while tuning the prompt.

Each session is a directory under `~/VoiceNotes/`:

```
2026-09-09-1430-budget-sync-with-ahmed/
├── session.json      what was recorded, when, for how long
├── mic.wav           you
├── system.wav        everyone else
├── transcript.json   speaker-labelled turns with timestamps
├── transcript.md     the same thing, readable
├── notes.json        structured notes
└── notes.md          ← the output you actually read
```

## Tuning it

**The prompt is the product.** `vn/prompts.py` is where the quality lives, and
it's the only file worth iterating on at this stage. Edit it, then:

```bash
python3 -m vn summarize    # re-runs the last meeting, no re-recording
```

Costs a few cents per iteration. The structured schema the model must fill —
what a "decision" is, what an action item requires — is in `vn/summarize.py`.
Add or remove fields there and the markdown in `vn/notes.py` to match.

**Language.** Whisper auto-detects, badly, on short or code-switched audio. If
your meetings are in one language, set `VN_LANGUAGE=en` (or `so`, `hi`, `ar`)
in `.env`. Be warned that Whisper's Somali is weak, and no ASR system handles
mid-sentence Somali/English switching well — if that's most of your meetings,
test `import` on one before investing further.

**Speed.** `large-v3-turbo` runs faster than real-time on Apple Silicon. On an
older CPU, drop to `VN_WHISPER_MODEL=small` for a first pass.

## Cost and privacy

Transcription is local and free — audio never leaves the machine. Only the text
transcript is sent to the API, and only when you summarize. A one-hour meeting
costs roughly 3–8¢ in tokens; the exact figure prints after every run.

Raw audio is the sensitive part and the only part that's large. `vn prune`
deletes it past `VN_AUDIO_RETENTION_DAYS` (default 7) while keeping transcripts
and notes, and it refuses to delete audio that hasn't been transcribed yet. Run
it from cron if you want it automatic.

**Recording other people.** In Canada you may lawfully record a conversation
you are part of (Criminal Code s. 184(2), one-party consent). That doesn't make
it fine to do quietly — tell people you're taking automated notes. If this ever
touches commercial work, the transcripts are personal information under PIPEDA.

## Tests

```bash
python3 -m pytest tests/ -q      # or: python3 tests/test_pipeline.py
```

Covers the parts that don't need a microphone: device selection, ffmpeg command
construction, the two-track merge, and markdown rendering.

## What Stage 0 deliberately doesn't do

No UI, no database, no search, no calendar integration, no memory across
meetings. Those are Stages 1–3, and they're only worth building if the notes
this produces turn out to be good. Judge that first.
