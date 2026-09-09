"""Audio device discovery and ffmpeg capture commands.

Everything platform-specific lives here. The rest of the pipeline only ever
sees WAV files, so porting to a new OS means adding a backend below and
nothing else.
"""

from __future__ import annotations

import platform
import re
import shutil
import subprocess
from dataclasses import dataclass, field

# Whisper resamples to 16 kHz mono internally, so capturing at that rate costs
# nothing in accuracy and makes an hour of audio ~115 MB instead of ~635 MB.
SAMPLE_RATE = 16000

# Substrings that identify a virtual loopback device — the thing that carries
# what your speakers are playing, i.e. everyone else on the call.
LOOPBACK_HINTS = (
    "blackhole",
    "loopback",
    "soundflower",
    "ishowu",
    "stereo mix",
    "cable output",
    "vb-audio",
    "voicemeeter",
    ".monitor",
)

FFMPEG_HINT = {
    "Darwin": "brew install ffmpeg",
    "Linux": "sudo apt install ffmpeg   # or: sudo dnf install ffmpeg",
    "Windows": "winget install Gyan.FFmpeg",
}


class AudioError(RuntimeError):
    pass


@dataclass(frozen=True)
class AudioDevice:
    """One capturable input. `spec` is what ffmpeg wants after -i."""

    name: str
    spec: str

    @property
    def is_loopback(self) -> bool:
        low = self.name.lower()
        return any(hint in low for hint in LOOPBACK_HINTS)

    def __str__(self) -> str:
        tag = "  [loopback — this is 'them']" if self.is_loopback else ""
        return f"{self.spec:<24} {self.name}{tag}"


@dataclass(frozen=True)
class Track:
    """One recorded track: an ffmpeg input plus the file it lands in."""

    label: str
    filename: str
    input_args: list[str] = field(default_factory=list)


def find_ffmpeg() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        hint = FFMPEG_HINT.get(platform.system(), "install ffmpeg")
        raise AudioError(f"ffmpeg not found on PATH. Install it with:\n    {hint}")
    return path


def _run(cmd: list[str]) -> str:
    """Run an ffmpeg/pactl probe. ffmpeg writes device lists to stderr and
    exits non-zero on the -list_devices form, so we ignore the return code."""
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    return proc.stdout + proc.stderr


# --------------------------------------------------------------------------
# Per-platform device discovery
# --------------------------------------------------------------------------

def _devices_macos() -> list[AudioDevice]:
    out = _run([find_ffmpeg(), "-hide_banner", "-f", "avfoundation",
                "-list_devices", "true", "-i", ""])
    devices: list[AudioDevice] = []
    in_audio = False
    for line in out.splitlines():
        if "audio devices" in line.lower():
            in_audio = True
            continue
        if "video devices" in line.lower():
            in_audio = False
            continue
        if not in_audio:
            continue
        match = re.search(r"\[(\d+)\]\s+(.+?)\s*$", line)
        if match:
            devices.append(AudioDevice(name=match.group(2), spec=f":{match.group(1)}"))
    return devices


def _devices_linux() -> list[AudioDevice]:
    if not shutil.which("pactl"):
        raise AudioError("pactl not found — this backend expects PulseAudio or PipeWire.")
    out = _run(["pactl", "list", "short", "sources"])
    devices: list[AudioDevice] = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            devices.append(AudioDevice(name=parts[1], spec=parts[1]))
    return devices


def _devices_windows() -> list[AudioDevice]:
    out = _run([find_ffmpeg(), "-hide_banner", "-list_devices", "true",
                "-f", "dshow", "-i", "dummy"])
    devices = []
    for line in out.splitlines():
        match = re.search(r'"([^"]+)"\s*\(audio\)', line)
        if match:
            name = match.group(1)
            devices.append(AudioDevice(name=name, spec=f"audio={name}"))
    return devices


_BACKENDS = {
    "Darwin": ("avfoundation", _devices_macos),
    "Linux": ("pulse", _devices_linux),
    "Windows": ("dshow", _devices_windows),
}


def backend_name() -> str:
    system = platform.system()
    if system not in _BACKENDS:
        raise AudioError(f"Unsupported platform: {system}")
    return _BACKENDS[system][0]


def list_devices() -> list[AudioDevice]:
    system = platform.system()
    if system not in _BACKENDS:
        raise AudioError(f"Unsupported platform: {system}")
    return _BACKENDS[system][1]()


def pick_defaults(devices: list[AudioDevice]) -> tuple[AudioDevice | None, AudioDevice | None]:
    """Guess (mic, system) from the device list.

    The loopback device is identifiable by name; the microphone is just the
    first thing that isn't one. Both guesses are overridable on the CLI.
    """
    loopbacks = [d for d in devices if d.is_loopback]
    mics = [d for d in devices if not d.is_loopback]
    return (mics[0] if mics else None, loopbacks[0] if loopbacks else None)


def resolve_device(devices: list[AudioDevice], ref: str) -> AudioDevice:
    """Match a user-supplied device by exact spec, then by name substring."""
    for device in devices:
        if device.spec == ref or device.spec == f":{ref}":
            return device
    matches = [d for d in devices if ref.lower() in d.name.lower()]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise AudioError(f"No audio device matching {ref!r}. Run `vn devices` to list them.")
    names = ", ".join(repr(m.name) for m in matches)
    raise AudioError(f"{ref!r} is ambiguous — matches {names}.")


def make_track(label: str, filename: str, device: AudioDevice) -> Track:
    # thread_queue_size is raised because two live inputs in one process will
    # otherwise drop packets on the slower of the two.
    return Track(
        label=label,
        filename=filename,
        input_args=["-thread_queue_size", "1024", "-f", backend_name(), "-i", device.spec],
    )


def build_record_command(tracks: list[Track]) -> list[str]:
    """One ffmpeg process, N inputs, N outputs.

    A single process matters: two processes started back to back drift apart by
    however long the second one took to open its device, and the whole
    speaker-attribution trick depends on the two tracks sharing a clock.
    """
    if not tracks:
        raise AudioError("Nothing to record: at least one track is required.")

    cmd = [find_ffmpeg(), "-hide_banner", "-loglevel", "warning", "-nostdin", "-y"]
    for track in tracks:
        cmd += track.input_args
    for index, track in enumerate(tracks):
        cmd += [
            "-map", f"{index}:a",
            "-ac", "1",
            "-ar", str(SAMPLE_RATE),
            "-c:a", "pcm_s16le",
            track.filename,
        ]
    return cmd
