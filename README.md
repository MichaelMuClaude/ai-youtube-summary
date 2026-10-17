# ai-youtube-summary

Get a clean, de-duplicated transcript of a YouTube video — official captions when they exist (no
download at all), local Whisper transcription (audio only, never the video) when they don't — so an
agent can read it and write the summary.

Deliberately stops there: it does not call an LLM to summarise for you. Once the transcript is in an
agent's context, writing the summary is ordinary conversation.

## Install

```bash
# needs yt-dlp and ffmpeg on PATH already
python3 -m venv ~/.venvs/ai-youtube-summary
~/.venvs/ai-youtube-summary/bin/pip install faster-whisper av==18.0.0
# av 19+ breaks faster-whisper 1.2.1 (TypeError: metadata_errors); pin 18.0.0.
```

The CLI itself needs nothing but the standard library — only the Whisper fallback runs in its own
venv (the same split `ai-book2video` uses for its TTS voice).

## Use

```bash
ai-youtube-summary info  <url>
ai-youtube-summary fetch <url>
```

`fetch` tries manual captions, then auto-generated captions, then (only if neither exists) downloads
the audio and transcribes it locally with Whisper — and writes, into a folder named after the video
(or `-o <folder>`):

| File | What |
|---|---|
| `transcript.md` | plain paragraphs, for reading and summarising |
| `transcript.timestamped.txt` | one line per cue with a `[MM:SS]` marker, for citing a moment |
| `info.json` | title, channel, duration, upload date, which caption languages exist |
| `manifest.json` | the above plus `source` (`captions:manual:en` / `captions:auto:en` / `whisper:small`) and cue count |

```bash
ai-youtube-summary fetch <url> --lang en,zh-Hans   # try these languages in order (default: en)
ai-youtube-summary fetch <url> --force-whisper     # skip captions, transcribe directly
ai-youtube-summary fetch <url> --whisper-model medium  # slower, more accurate fallback
```

## Why captions first

Fetching an existing caption file takes a couple of seconds and downloads nothing but the text.
Whisper transcription needs the full audio downloaded and run through a model — slower, and a real
compute cost. Most YouTube videos already have auto-generated captions, so the slow path is the
exception, not the rule.

## The parsing problem this solves

YouTube's own auto-captions scroll: each cue repeats the previous, already-settled line and adds the
next line being typed out word by word (with inline `<00:00:01.234><c>...</c>` timing tags), plus
near-zero-duration "freeze" cues that just repeat the same line again. Naively joining every cue's
text produces a transcript where every sentence appears two or three times. Manual captions (TED,
Amara, ...) are the opposite problem: one utterance word-wrapped over several lines with *no*
repetition, often opening with a "Translator: ... / Reviewer: ..." credits cue that was never
spoken.

`vtt.py` handles both with one rule: compare each cue's lines against the end of the previous cue's
lines, drop the longest matching run at the start (that was the repeated part), and whatever is left
is genuinely new. A block with nothing left after that is a pure repeat and is dropped; so is a
credits line. See `tests/test_vtt.py` for both real formats, captured from real videos.

## Layout

- `src/ai_youtube_summary/vtt.py` — parses both caption styles into clean, de-duplicated cues
- `src/ai_youtube_summary/core.py` — the pipeline: captions first, Whisper only if there are none
- `src/ai_youtube_summary/transcribe_whisper.py` — runs inside the Whisper venv
- `src/ai_youtube_summary/cli.py` — the `ai-youtube-summary` commands

## Licence

MIT (see `LICENSE`).
