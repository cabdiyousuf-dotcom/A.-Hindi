"""Configuration, paths, and session layout."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

# Files inside a session directory.
MIC_WAV = "mic.wav"
SYSTEM_WAV = "system.wav"
SESSION_JSON = "session.json"
TRANSCRIPT_JSON = "transcript.json"
TRANSCRIPT_MD = "transcript.md"
NOTES_MD = "notes.md"
NOTES_JSON = "notes.json"

AUDIO_FILES = (MIC_WAV, SYSTEM_WAV)


def load_dotenv(path: Path) -> None:
    """Minimal .env loader — avoids a dependency for ten lines of parsing.

    Existing environment variables always win, so `VN_ME=Abdi vn run` overrides
    the file for a single invocation.
    """
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = value


@dataclass(frozen=True)
class Config:
    home: Path
    me: str
    whisper_model: str
    language: str | None
    audio_retention_days: int

    @classmethod
    def from_env(cls) -> "Config":
        load_dotenv(Path(__file__).resolve().parent.parent / ".env")
        language = os.environ.get("VN_LANGUAGE", "").strip()
        return cls(
            home=Path(os.environ.get("VN_HOME", "~/VoiceNotes")).expanduser(),
            me=os.environ.get("VN_ME", "Me").strip() or "Me",
            whisper_model=os.environ.get("VN_WHISPER_MODEL", "large-v3-turbo").strip(),
            language=language or None,
            audio_retention_days=int(os.environ.get("VN_AUDIO_RETENTION_DAYS", "7")),
        )


def slugify(text: str, max_len: int = 40) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:max_len].strip("-") or "meeting"


def new_session_dir(home: Path, title: str, now: datetime | None = None) -> Path:
    """Create and return a fresh session directory.

    Named `YYYY-MM-DD-HHMM-slug` so the directory listing sorts chronologically
    and is still readable at a glance.
    """
    now = now or datetime.now()
    base = f"{now:%Y-%m-%d-%H%M}-{slugify(title)}"
    path = home / base
    suffix = 2
    while path.exists():
        path = home / f"{base}-{suffix}"
        suffix += 1
    path.mkdir(parents=True)
    return path


def resolve_session(home: Path, ref: str | None) -> Path:
    """Resolve a session reference: a path, a directory name, or None for latest."""
    if ref:
        candidate = Path(ref).expanduser()
        if candidate.is_dir():
            return candidate
        candidate = home / ref
        if candidate.is_dir():
            return candidate
        raise FileNotFoundError(f"No such session: {ref}")

    sessions = list_sessions(home)
    if not sessions:
        raise FileNotFoundError(f"No sessions yet in {home}")
    return sessions[-1]


def list_sessions(home: Path) -> list[Path]:
    """Sessions oldest-first. The date-prefixed names make this a plain sort."""
    if not home.is_dir():
        return []
    return sorted(p for p in home.iterdir() if p.is_dir() and (p / SESSION_JSON).is_file())
