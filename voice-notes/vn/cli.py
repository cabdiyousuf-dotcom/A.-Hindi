"""Command-line entry point."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from . import audio, config, record, summarize, transcribe


def _tracks(args, cfg) -> tuple[list[audio.Track], list[str]]:
    """Resolve which devices to record, honouring --mic/--system overrides."""
    devices = audio.list_devices()
    if not devices:
        raise audio.AudioError("No audio input devices found.")

    default_mic, default_system = audio.pick_defaults(devices)
    mic = audio.resolve_device(devices, args.mic) if args.mic else default_mic
    system = audio.resolve_device(devices, args.system) if args.system else default_system

    if args.mic_only:
        system = None
    if args.system_only:
        mic = None

    tracks, warnings = [], []
    if mic:
        tracks.append(audio.make_track("mic", config.MIC_WAV, mic))
    if system:
        tracks.append(audio.make_track("system", config.SYSTEM_WAV, system))
    elif not args.mic_only:
        warnings.append(
            "No loopback device found, so only your microphone will be recorded.\n"
            "  On macOS install BlackHole (`brew install blackhole-2ch`) and route\n"
            "  output through a Multi-Output Device — see the README. Recording\n"
            "  mic-only is fine for in-person meetings."
        )
    if not tracks:
        raise audio.AudioError("Nothing to record — no usable input device.")
    return tracks, warnings


def cmd_devices(args, cfg) -> int:
    devices = audio.list_devices()
    if not devices:
        print("No audio input devices found.")
        return 1
    print(f"Audio inputs ({audio.backend_name()}):\n")
    for device in devices:
        print(f"  {device}")
    mic, system = audio.pick_defaults(devices)
    print(f"\nWould record  mic: {mic.name if mic else '—'}")
    print(f"           system: {system.name if system else '— (none found)'}")
    return 0


def cmd_record(args, cfg) -> int:
    tracks, warnings = _tracks(args, cfg)
    for warning in warnings:
        print(f"note: {warning}\n")
    session_dir = config.new_session_dir(cfg.home, args.title)
    record.record(session_dir, tracks, args.title)
    print(f"\nSession: {session_dir}")
    return 0


def cmd_transcribe(args, cfg) -> int:
    session_dir = config.resolve_session(cfg.home, args.session)
    started = time.monotonic()
    transcribe.transcribe_session(session_dir, cfg)
    print(f"Took {time.monotonic() - started:.0f}s → {session_dir / config.TRANSCRIPT_MD}")
    return 0


def cmd_summarize(args, cfg) -> int:
    session_dir = config.resolve_session(cfg.home, args.session)
    summarize.summarize_session(session_dir, cfg)
    print(f"\n{'-' * 60}")
    print((session_dir / config.NOTES_MD).read_text(encoding="utf-8"))
    return 0


def cmd_run(args, cfg) -> int:
    """Record, transcribe, summarize — the loop you actually use day to day."""
    tracks, warnings = _tracks(args, cfg)
    for warning in warnings:
        print(f"note: {warning}\n")
    session_dir = config.new_session_dir(cfg.home, args.title)
    record.record(session_dir, tracks, args.title)
    print()
    transcribe.transcribe_session(session_dir, cfg)
    print()
    summarize.summarize_session(session_dir, cfg)
    print(f"\n{'-' * 60}")
    print((session_dir / config.NOTES_MD).read_text(encoding="utf-8"))
    print(f"Session: {session_dir}")
    return 0


def cmd_import(args, cfg) -> int:
    """Adopt an existing recording (a Zoom export, a phone memo) as a session.

    The fastest way to judge whether the notes are any good is to point this at
    a meeting you already have, without waiting for the next one.
    """
    source = Path(args.audio).expanduser()
    if not source.is_file():
        raise FileNotFoundError(f"No such file: {source}")

    title = args.title or source.stem
    session_dir = config.new_session_dir(cfg.home, title)
    target = session_dir / config.MIC_WAV
    ffmpeg = audio.find_ffmpeg()

    import subprocess

    print(f"Converting {source.name}…")
    subprocess.run(
        [ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
         "-i", str(source), "-ac", "1", "-ar", str(audio.SAMPLE_RATE),
         "-c:a", "pcm_s16le", str(target)],
        check=True,
    )
    (session_dir / config.SESSION_JSON).write_text(json.dumps({
        "title": title,
        "started_at": None,
        "ended_at": None,
        "duration_sec": None,
        "source": str(source),
        "tracks": [{"label": "mic", "file": config.MIC_WAV}],
    }, indent=2), encoding="utf-8")

    transcribe.transcribe_session(session_dir, cfg)
    print()
    summarize.summarize_session(session_dir, cfg)
    print(f"\n{'-' * 60}")
    print((session_dir / config.NOTES_MD).read_text(encoding="utf-8"))
    print(f"Session: {session_dir}")
    return 0


def cmd_list(args, cfg) -> int:
    sessions = config.list_sessions(cfg.home)
    if not sessions:
        print(f"No sessions in {cfg.home}")
        return 0
    for session in sessions:
        has_audio = any((session / f).is_file() for f in config.AUDIO_FILES)
        state = "notes" if (session / config.NOTES_MD).is_file() else (
            "transcript" if (session / config.TRANSCRIPT_JSON).is_file() else "audio only"
        )
        print(f"  {session.name:<50} {state}{'' if has_audio else '  (audio pruned)'}")
    return 0


def cmd_prune(args, cfg) -> int:
    """Delete raw audio past the retention window; transcripts and notes stay.

    Audio is the only part of this that is genuinely sensitive and the only part
    that is large. Keeping it by default is a choice worth not making.
    """
    days = args.days if args.days is not None else cfg.audio_retention_days
    cutoff = time.time() - days * 86400
    freed, count = 0, 0
    for session in config.list_sessions(cfg.home):
        if not (session / config.TRANSCRIPT_JSON).is_file():
            continue  # never delete audio we haven't transcribed yet
        for name in config.AUDIO_FILES:
            path = session / name
            if path.is_file() and path.stat().st_mtime < cutoff:
                freed += path.stat().st_size
                if args.dry_run:
                    print(f"  would delete {path}")
                else:
                    path.unlink()
                count += 1
    verb = "Would free" if args.dry_run else "Freed"
    print(f"{verb} {freed / 1e6:.0f} MB from {count} file(s) older than {days} days.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vn", description="Record, transcribe and summarize your meetings."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def add_capture_flags(p):
        p.add_argument("--title", default="meeting", help="What this meeting is about.")
        p.add_argument("--mic", help="Microphone device (name substring or index).")
        p.add_argument("--system", help="System-audio/loopback device.")
        p.add_argument("--mic-only", action="store_true", help="In-person: microphone only.")
        p.add_argument("--system-only", action="store_true", help="Call audio only, not you.")

    sub.add_parser("devices", help="List audio inputs.").set_defaults(func=cmd_devices)

    p = sub.add_parser("record", help="Record only.")
    add_capture_flags(p)
    p.set_defaults(func=cmd_record)

    p = sub.add_parser("run", help="Record, transcribe and summarize.")
    add_capture_flags(p)
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("transcribe", help="Transcribe a recorded session.")
    p.add_argument("session", nargs="?", help="Session name or path. Default: most recent.")
    p.set_defaults(func=cmd_transcribe)

    p = sub.add_parser("summarize", help="Summarize a transcribed session.")
    p.add_argument("session", nargs="?", help="Session name or path. Default: most recent.")
    p.set_defaults(func=cmd_summarize)

    p = sub.add_parser("import", help="Process an existing audio or video file.")
    p.add_argument("audio", help="Path to an existing recording.")
    p.add_argument("--title", help="Defaults to the filename.")
    p.set_defaults(func=cmd_import)

    sub.add_parser("list", help="List sessions.").set_defaults(func=cmd_list)

    p = sub.add_parser("prune", help="Delete raw audio past the retention window.")
    p.add_argument("--days", type=int, help="Override VN_AUDIO_RETENTION_DAYS.")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_prune)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cfg = config.Config.from_env()
    cfg.home.mkdir(parents=True, exist_ok=True)
    try:
        return args.func(args, cfg)
    except KeyboardInterrupt:
        print("\nInterrupted.")
        return 130
    except (audio.AudioError, summarize.SummarizeError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 - map SDK errors to actionable advice
        return _report_unexpected(exc)


NO_CREDENTIALS = (
    "No usable Anthropic credentials. Put ANTHROPIC_API_KEY in voice-notes/.env,\n"
    "       export it in your shell, or run `ant auth login`."
)


def _report_unexpected(exc: Exception) -> int:
    """Map SDK failures to something you can act on.

    The transcript is already on disk by the time any of these can fire, so
    every message here says how to retry just the summarize step.
    """
    name = type(exc).__name__
    advice = {
        "AuthenticationError": NO_CREDENTIALS,
        "PermissionDeniedError": "That key is not allowed to call this model.",
        "RateLimitError": "Rate limited. Wait a moment, then re-run `vn summarize`.",
        "APIConnectionError": "Could not reach the Anthropic API. Check your connection.",
        "APITimeoutError": "The request timed out. Re-run `vn summarize`.",
    }.get(name)

    # The SDK raises a plain TypeError when no credential source resolves at all,
    # which is the most likely first-run failure and deserves the same advice.
    if advice is None and "Could not resolve authentication method" in str(exc):
        print(f"error: {NO_CREDENTIALS}", file=sys.stderr)
        return 1

    print(f"error: {name}: {exc}", file=sys.stderr)
    if advice:
        print(f"       {advice}", file=sys.stderr)
    return 1
