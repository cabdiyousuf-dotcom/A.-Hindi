"""Turn a transcript into structured notes with Claude."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field

from . import config, notes as notes_render, prompts, transcribe

MODEL = "claude-opus-5"

# Claude Opus 5 pricing, USD per million tokens, for the cost line printed after
# each run. Update if the rates change.
INPUT_PER_MTOK = 5.00
OUTPUT_PER_MTOK = 25.00

# Every field is required and non-optional: JSON-schema structured outputs want a
# closed schema, and "" / [] express absence perfectly well.


class ActionItem(BaseModel):
    owner: str = Field(description="Who owns this, by name. Empty if genuinely unclear.")
    task: str = Field(description="What they committed to do, in one line.")
    due: str = Field(description="Due date as stated in the meeting, or empty if none was.")
    mine: bool = Field(description="True if the notes' owner took this on themselves.")


class Quote(BaseModel):
    speaker: str
    text: str = Field(description="Verbatim from the transcript.")


class MeetingNotes(BaseModel):
    title: str = Field(description="Short specific subject line for this meeting.")
    summary: str = Field(description="Three to six sentences on what happened and why it mattered.")
    decisions: list[str] = Field(description="Things that were actually settled.")
    action_items: list[ActionItem]
    open_questions: list[str] = Field(description="Raised but left unresolved.")
    quotes: list[Quote] = Field(description="At most three; usually zero.")
    follow_up_email: str = Field(description="A short email the owner could send after this meeting.")


class SummarizeError(RuntimeError):
    pass


def _extract_fallback(response) -> MeetingNotes:
    """If the SDK's parsed_output is empty, recover the JSON from the text block."""
    for block in response.content:
        if block.type == "text" and block.text.strip():
            return MeetingNotes.model_validate_json(block.text)
    raise SummarizeError("Model returned no parsable notes.")


def summarize(transcript: dict, cfg: config.Config) -> tuple[MeetingNotes, dict]:
    import anthropic

    text = transcribe.transcript_as_text(transcript)
    if not text.strip():
        raise SummarizeError("Transcript is empty — nothing to summarize.")

    client = anthropic.Anthropic()
    response = client.messages.parse(
        model=MODEL,
        max_tokens=16000,
        # Sorting a rambling conversation into decisions vs. discussion, and
        # attributing commitments correctly, is exactly the kind of work that
        # benefits from letting the model think first.
        thinking={"type": "adaptive"},
        system=prompts.system_prompt(cfg.me, transcript.get("diarized", True)),
        messages=[{
            "role": "user",
            "content": prompts.user_prompt(
                transcript.get("title", ""),
                transcript.get("started_at", ""),
                text,
            ),
        }],
        output_format=MeetingNotes,
    )

    if response.stop_reason == "refusal":
        raise SummarizeError(
            "The model declined to summarize this recording. "
            f"Reason: {getattr(response.stop_details, 'category', 'unspecified')}"
        )

    notes = response.parsed_output or _extract_fallback(response)
    usage = {
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
        "cost_usd": round(
            response.usage.input_tokens / 1e6 * INPUT_PER_MTOK
            + response.usage.output_tokens / 1e6 * OUTPUT_PER_MTOK,
            4,
        ),
    }
    return notes, usage


def summarize_session(session_dir: Path, cfg: config.Config) -> MeetingNotes:
    transcript_path = session_dir / config.TRANSCRIPT_JSON
    if not transcript_path.is_file():
        raise FileNotFoundError(f"No transcript in {session_dir}. Run `vn transcribe` first.")

    transcript = json.loads(transcript_path.read_text(encoding="utf-8"))
    print(f"Summarizing with {MODEL}…", flush=True)
    notes, usage = summarize(transcript, cfg)

    (session_dir / config.NOTES_JSON).write_text(
        notes.model_dump_json(indent=2), encoding="utf-8"
    )
    (session_dir / config.NOTES_MD).write_text(
        notes_render.render(notes, transcript), encoding="utf-8"
    )
    print(
        f"Notes written. {usage['input_tokens']} in / {usage['output_tokens']} out "
        f"— ${usage['cost_usd']:.3f}"
    )
    return notes
