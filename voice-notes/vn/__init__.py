"""Stage 0 of a personal meeting note-taker.

Pipeline: record two audio tracks -> transcribe each locally -> merge into one
speaker-labelled timeline -> ask Claude for structured notes -> write markdown.

The two-track recording is the load-bearing idea: your microphone is captured
separately from your system output, so "who said this" falls out of which file
the audio came from and no diarization model is needed.
"""

__version__ = "0.1.0"
