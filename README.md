# ai-youtube-summary

One YouTube tool: get a clean, de-duplicated transcript of a video — official captions when they
exist (no download at all), local Whisper transcription (audio only, never the video) when they
don't — so an agent can read it and write the summary; or download the actual audio/video file to
your local media library. A browser extension (see [`EXTENSION.md`](EXTENSION.md)) wraps both in a
side panel, with a local-model summarizer on top.

Transcript fetching is deliberately dumb: it does not call an LLM to summarise for you. Once the
transcript is in an agent's context, writing the summary is ordinary conversation (the extension's
`/summarize` endpoint is the one place an LLM — a local Ollama model — is actually called, and that's
opt-in, for the UI, not the CLI).

(This project absorbed the former standalone `ai-youtube` downloader on 2026-10-18 — same `song` /
`lofi` / `video` / `search` / `check` commands, now living here instead of their own repo.)

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

## Download instead of (or as well as) summarising

```bash
ai-youtube-summary search "<query>"     # top 5 YouTube results, no download
ai-youtube-summary check  "<query>"     # is this already in the local media library?
ai-youtube-summary song   <url-or-query>   # audio, best quality mp3 -> ~/Media/.../Songs
ai-youtube-summary lofi   <url-or-query>   # audio, 192kbps mp3     -> ~/Media/.../Lofi
ai-youtube-summary video  <url-or-query>   # video, mp4 + subs      -> ~/Media/.../Videos
```

`song`/`lofi`/`video` accept either a direct URL or search keywords (first hit is downloaded).
Output goes to `~/Media/Master-Media-Collection/{Songs,Lofi,Videos}` by default (override with
`AI_YOUTUBE_LIBRARY`). `check` does fuzzy title matching against what's already downloaded so you
don't fetch the same song/video twice — see `src/ai_youtube_summary/download.py` for the matching
rules.

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
- `src/ai_youtube_summary/core.py` — the transcript pipeline: captions first, Whisper only if there are none
- `src/ai_youtube_summary/transcribe_whisper.py` — runs inside the Whisper venv
- `src/ai_youtube_summary/download.py` — `song`/`lofi`/`video`/`search`/`check` (the former ai-youtube)
- `src/ai_youtube_summary/cli.py` — the `ai-youtube-summary` command dispatcher
- `extension/`, `server/` — the browser extension and its local HTTP bridge, see `EXTENSION.md`

## Licence

MIT (see `LICENSE`).
