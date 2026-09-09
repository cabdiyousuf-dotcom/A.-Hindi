"""Tests for the parts that don't need a microphone or an API key.

Run with:  python3 -m pytest tests/ -q   (or: python3 tests/test_pipeline.py)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from vn.audio import AudioDevice, Track, build_record_command, pick_defaults, resolve_device
from vn.config import slugify
from vn.notes import render
from vn.summarize import ActionItem, MeetingNotes, Quote
from vn.transcribe import Turn, merge_turns, timestamp


def test_slugify():
    assert slugify("Weekly sync — Ahmed & Sara!!") == "weekly-sync-ahmed-sara"
    assert slugify("") == "meeting"
    assert len(slugify("x" * 200)) <= 40


def test_loopback_detection():
    devices = [AudioDevice("MacBook Pro Microphone", ":0"), AudioDevice("BlackHole 2ch", ":1")]
    mic, system = pick_defaults(devices)
    assert mic.spec == ":0" and system.spec == ":1"
    assert system.is_loopback and not mic.is_loopback


def test_resolve_device_by_name_and_index():
    devices = [AudioDevice("MacBook Pro Microphone", ":0"), AudioDevice("BlackHole 2ch", ":1")]
    assert resolve_device(devices, "blackhole").spec == ":1"
    assert resolve_device(devices, "0").name == "MacBook Pro Microphone"


def test_record_command_maps_each_input_to_its_own_file(monkeypatch):
    import vn.audio
    monkeypatch.setattr(vn.audio.shutil, "which", lambda _: "/usr/bin/ffmpeg")
    tracks = [
        Track("mic", "mic.wav", ["-f", "avfoundation", "-i", ":0"]),
        Track("system", "system.wav", ["-f", "avfoundation", "-i", ":1"]),
    ]
    cmd = " ".join(build_record_command(tracks))
    assert "-map 0:a" in cmd and "mic.wav" in cmd
    assert "-map 1:a" in cmd and "system.wav" in cmd
    assert cmd.index("mic.wav") < cmd.index("-map 1:a")


def test_merge_turns_interleaves_two_tracks_by_time():
    segments = [
        Turn("Them", 4.0, 6.0, "Did you get the draft?"),
        Turn("Abdi", 0.0, 3.2, "Hey Ahmed,"),
        Turn("Abdi", 3.4, 3.9, "can you hear me?"),
        Turn("Abdi", 30.0, 32.0, "Sorry, I was muted."),
        Turn("Them", 8.5, 9.0, "   "),
    ]
    turns = merge_turns(segments)
    assert [t.speaker for t in turns] == ["Abdi", "Them", "Abdi"]
    # Same speaker, 0.2s apart -> one turn.
    assert turns[0].text == "Hey Ahmed, can you hear me?"
    assert turns[0].end == 3.9
    # Same speaker, 22s apart -> kept separate.
    assert turns[2].text == "Sorry, I was muted."


def test_merge_turns_drops_blank_segments():
    assert merge_turns([Turn("Abdi", 0.0, 1.0, "  ")]) == []


def test_timestamp_formats_past_an_hour():
    assert timestamp(0) == "00:00:00"
    assert timestamp(3725) == "01:02:05"


def _notes():
    return MeetingNotes(
        title="Q4 budget and the Hargeisa site visit",
        summary="Ahmed confirmed the Q4 envelope is unchanged.",
        decisions=["Q4 budget stays at $180k."],
        action_items=[
            ActionItem(owner="Abdi", task="Send the revised budget sheet", due="Friday", mine=True),
            ActionItem(owner="Ahmed", task="Confirm the site visit dates", due="", mine=False),
        ],
        open_questions=["Who signs off if Ahmed is travelling?"],
        quotes=[Quote(speaker="Ahmed", text="We are not moving that number again.")],
        follow_up_email="Ahmed — thanks for this. Sheet lands Friday.",
    )


def test_render_splits_commitments_by_owner():
    md = render(_notes(), {"started_at": "2026-09-09T14:30:00+00:00", "duration_sec": 1800})
    assert "## My commitments" in md and "## Waiting on others" in md
    mine, theirs = md.index("## My commitments"), md.index("## Waiting on others")
    assert mine < theirs
    # My own items don't repeat my name; other people's do.
    assert "- [ ] Send the revised budget sheet _(due Friday)_" in md
    assert "**Ahmed** — Confirm the site visit dates" in md
    # An empty due date leaves no dangling "(due )".
    assert "(due )" not in md


def test_render_omits_empty_sections():
    notes = _notes()
    notes.quotes, notes.decisions, notes.open_questions = [], [], []
    notes.action_items = [a for a in notes.action_items if a.mine]
    md = render(notes, {})
    for absent in ("Worth keeping", "## Decisions", "## Open questions", "## Waiting on others"):
        assert absent not in md
    assert "## My commitments" in md and "## Summary" in md


def test_render_flags_single_mic_recordings():
    md = render(_notes(), {"diarized": False})
    assert "speakers not separated" in md


if __name__ == "__main__":
    import traceback
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    failed = 0
    for name, fn in fns:
        try:
            if "monkeypatch" in fn.__code__.co_varnames[: fn.__code__.co_argcount]:
                import vn.audio
                original = vn.audio.shutil.which
                vn.audio.shutil.which = lambda _: "/usr/bin/ffmpeg"

                class _MP:
                    setattr = staticmethod(lambda obj, attr, val: None)

                fn(_MP())
                vn.audio.shutil.which = original
            else:
                fn()
            print(f"  PASS  {name}")
        except Exception:
            failed += 1
            print(f"  FAIL  {name}")
            traceback.print_exc()
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
