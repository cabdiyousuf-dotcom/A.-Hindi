"""Render structured notes as markdown."""

from __future__ import annotations

from datetime import datetime


def _when(transcript: dict) -> str:
    raw = transcript.get("started_at") or ""
    try:
        return datetime.fromisoformat(raw).astimezone().strftime("%A %d %B %Y, %H:%M")
    except ValueError:
        return raw


def render(notes, transcript: dict) -> str:
    """Notes ordered by what you look for first: commitments, then context."""
    out: list[str] = [f"# {notes.title}", ""]

    meta = [_when(transcript)]
    duration = transcript.get("duration_sec")
    if duration:
        meta.append(f"{duration / 60:.0f} min")
    if not transcript.get("diarized", True):
        meta.append("single-mic recording — speakers not separated")
    out += [f"*{' · '.join(m for m in meta if m)}*", ""]

    mine = [a for a in notes.action_items if a.mine]
    theirs = [a for a in notes.action_items if not a.mine]

    if mine:
        out += ["## My commitments", ""]
        out += [_action_line(a) for a in mine]
        out += [""]

    if theirs:
        out += ["## Waiting on others", ""]
        out += [_action_line(a) for a in theirs]
        out += [""]

    if notes.decisions:
        out += ["## Decisions", ""]
        out += [f"- {d}" for d in notes.decisions]
        out += [""]

    if notes.open_questions:
        out += ["## Open questions", ""]
        out += [f"- {q}" for q in notes.open_questions]
        out += [""]

    out += ["## Summary", "", notes.summary, ""]

    if notes.quotes:
        out += ["## Worth keeping", ""]
        for quote in notes.quotes:
            out += [f"> {quote.text}", f">", f"> — {quote.speaker}", ""]

    if notes.follow_up_email.strip():
        out += ["## Follow-up draft", "", "```", notes.follow_up_email.strip(), "```", ""]

    return "\n".join(out).rstrip() + "\n"


def _action_line(action) -> str:
    """`- [ ] Owner — task _(due)_`, with the owner dropped when it's redundant."""
    parts = []
    if action.owner and not action.mine:
        parts.append(f"**{action.owner}** — ")
    line = f"- [ ] {''.join(parts)}{action.task}"
    if action.due.strip():
        line += f" _(due {action.due.strip()})_"
    return line
