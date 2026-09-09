"""Local transcription with faster-whisper, merged into one speaker timeline."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from . import config

# Two segments from the same speaker separated by less than this are the same
# breath, not two turns. Whisper splits on its own internal boundaries, which
# are far shorter than a conversational turn.
TURN_GAP_SEC = 1.5


@dataclass
class Turn:
    speaker: str
    start: float
    end: float
    text: str


def merge_turns(segments: list[Turn], gap: float = TURN_GAP_SEC) -> list[Turn]:
    """Order segments by time and glue consecutive same-speaker runs together.

    This is what turns two independent per-track transcripts into a readable
    conversation, and it is the only place the two tracks meet.
    """
    ordered = sorted(segments, key=lambda s: (s.start, s.speaker))
    merged: list[Turn] = []
    for seg in ordered:
        text = seg.text.strip()
        if not text:
            continue
        previous = merged[-1] if merged else None
        if previous and previous.speaker == seg.speaker and seg.start - previous.end <= gap:
            previous.text = f"{previous.text} {text}"
            previous.end = max(previous.end, seg.end)
        else:
            merged.append(Turn(seg.speaker, seg.start, seg.end, text))
    return merged


def _load_model(model_size: str):
    """Import lazily so `vn devices` and `vn record` don't pay the import cost.

    device="auto" picks CUDA when present; int8 keeps CPU transcription usable
    and costs very little accuracy at this model size.
    """
    from faster_whisper import WhisperModel

    return WhisperModel(model_size, device="auto", compute_type="int8")


def transcribe_track(model, path: Path, speaker: str, language: str | None) -> list[Turn]:
    """Transcribe one track. Returns segments tagged with a speaker."""
    segments, info = model.transcribe(
        str(path),
        language=language,
        beam_size=5,
        # The bundled Silero VAD both skips silence (most of a track where one
        # side isn't talking) and makes Whisper cut on pauses rather than at a
        # fixed clock, which is what stops words being sliced in half.
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 500},
        condition_on_previous_text=False,  # avoids repetition loops on long audio
    )
    detected = getattr(info, "language", None)
    print(f"  {speaker}: language={detected or language or 'auto'}", flush=True)
    return [Turn(speaker, round(s.start, 2), round(s.end, 2), s.text.strip()) for s in segments]


def transcribe_session(session_dir: Path, cfg: config.Config) -> dict:
    """Transcribe every track present and write transcript.json / transcript.md."""
    meta = json.loads((session_dir / config.SESSION_JSON).read_text(encoding="utf-8"))
    speaker_for = {"mic": cfg.me, "system": "Them"}

    present = [t for t in meta["tracks"] if (session_dir / t["file"]).is_file()]
    if not present:
        raise FileNotFoundError(f"No audio files in {session_dir}")

    # A lone mic track means an in-person recording: everything is one mixed
    # stream, so promising a speaker name we cannot know would be a lie.
    solo = len(present) == 1 and present[0]["label"] == "mic"
    if solo:
        speaker_for["mic"] = "Speaker"

    print(f"Loading Whisper ({cfg.whisper_model})…", flush=True)
    model = _load_model(cfg.whisper_model)

    segments: list[Turn] = []
    for track in present:
        segments += transcribe_track(
            model,
            session_dir / track["file"],
            speaker_for.get(track["label"], track["label"]),
            cfg.language,
        )

    turns = merge_turns(segments)
    transcript = {
        "title": meta.get("title", ""),
        "started_at": meta.get("started_at"),
        "duration_sec": meta.get("duration_sec"),
        "transcribed_at": datetime.now(timezone.utc).isoformat(),
        "model": cfg.whisper_model,
        "speakers": sorted({t.speaker for t in turns}),
        "diarized": not solo,
        "turns": [asdict(t) for t in turns],
    }
    (session_dir / config.TRANSCRIPT_JSON).write_text(
        json.dumps(transcript, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (session_dir / config.TRANSCRIPT_MD).write_text(
        render_transcript(transcript), encoding="utf-8"
    )
    words = sum(len(t.text.split()) for t in turns)
    print(f"Transcript: {len(turns)} turns, ~{words} words")
    return transcript


def timestamp(seconds: float) -> str:
    total = int(seconds)
    return f"{total // 3600:02d}:{total // 60 % 60:02d}:{total % 60:02d}"


def render_transcript(transcript: dict) -> str:
    lines = [f"# Transcript — {transcript.get('title') or 'Untitled'}", ""]
    for turn in transcript["turns"]:
        lines.append(f"**[{timestamp(turn['start'])}] {turn['speaker']}:** {turn['text']}")
        lines.append("")
    return "\n".join(lines)


def transcript_as_text(transcript: dict) -> str:
    """Flat speaker-labelled text — what the summarizer actually reads."""
    return "\n".join(
        f"[{timestamp(t['start'])}] {t['speaker']}: {t['text']}" for t in transcript["turns"]
    )
