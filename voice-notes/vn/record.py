"""Run the capture and write session metadata."""

from __future__ import annotations

import json
import signal
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from . import audio, config


def _write_session(session_dir: Path, data: dict) -> None:
    (session_dir / config.SESSION_JSON).write_text(
        json.dumps(data, indent=2), encoding="utf-8"
    )


def record(session_dir: Path, tracks: list[audio.Track], title: str) -> dict:
    """Record until Ctrl-C, then finalize the WAV files cleanly.

    ffmpeg is put in its own process group so the terminal's Ctrl-C reaches
    only this process. We then forward SIGINT ourselves, which makes ffmpeg
    write the WAV headers and flush — killing it outright leaves the files
    with a zero-length data chunk that nothing will play.
    """
    cmd = audio.build_record_command(tracks)
    started = datetime.now(timezone.utc)
    meta = {
        "title": title,
        "started_at": started.isoformat(),
        "ended_at": None,
        "duration_sec": None,
        "tracks": [{"label": t.label, "file": t.filename} for t in tracks],
    }
    _write_session(session_dir, meta)

    labels = ", ".join(t.label for t in tracks)
    print(f"Recording [{labels}] into {session_dir}")
    print("Press Ctrl-C to stop.\n")

    monotonic_start = time.monotonic()
    proc = subprocess.Popen(
        cmd,
        cwd=session_dir,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
    )

    try:
        proc.wait()
    except KeyboardInterrupt:
        print("\nStopping — finalizing audio…")
        _shutdown(proc)

    duration = round(time.monotonic() - monotonic_start, 2)
    meta["ended_at"] = datetime.now(timezone.utc).isoformat()
    meta["duration_sec"] = duration
    _write_session(session_dir, meta)

    _verify(session_dir, tracks)
    print(f"Recorded {duration / 60:.1f} min.")
    return meta


def _shutdown(proc: subprocess.Popen, grace: float = 10.0) -> None:
    """SIGINT, then SIGTERM, then SIGKILL — escalate only if ffmpeg ignores us."""
    for sig in (signal.SIGINT, signal.SIGTERM):
        if proc.poll() is not None:
            return
        try:
            proc.send_signal(sig)
            proc.wait(timeout=grace)
            return
        except subprocess.TimeoutExpired:
            continue
        except ProcessLookupError:
            return
    if proc.poll() is None:
        proc.kill()
        proc.wait()


def _verify(session_dir: Path, tracks: list[audio.Track]) -> None:
    """Warn loudly about a silent or missing track.

    The classic failure is a system track that recorded nothing because audio
    output was never routed through the loopback device. Better to say so now
    than after transcribing an hour of silence.
    """
    # 44 bytes of WAV header plus a second of 16-bit 16 kHz mono.
    floor = 44 + audio.SAMPLE_RATE * 2
    for track in tracks:
        path = session_dir / track.filename
        if not path.exists():
            print(f"  !! {track.label}: no file was written.")
        elif path.stat().st_size < floor:
            print(f"  !! {track.label}: file is essentially empty — check the device.")
        else:
            print(f"  ok {track.label}: {path.stat().st_size / 1e6:.1f} MB")
