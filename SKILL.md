---
name: ai-youtube-summary
description: One tool for YouTube — (1) get a clean, de-duplicated transcript (official captions when they exist, no download at all; local Whisper audio-only fallback when they don't) for you to read and summarise yourself, and (2) search/check/download songs, lofi, or videos to the local media library (absorbed the former ai-youtube project 2026-10-18, same song/lofi/video/search/check commands). Use for "summarise this video" / "what does this say" with a YouTube link, or "download this song/video" / "find a song" / "have I already got this".
compatibility: Python 3.9+, yt-dlp on PATH, ffmpeg (for audio extraction). Whisper fallback needs its own venv with faster-whisper installed (see Install below); without it, videos with no captions in the requested language will fail with a clear error instead of being summarised.
---

# ai-youtube-summary — a YouTube video's transcript, ready to summarise — and its downloader

## What this is and is not

The **transcript** side stops at **getting you a clean transcript**. It does not call an LLM to
write the summary itself, on purpose: once the transcript is in an agent's context, writing a good
summary is ordinary conversation, and baking an API call into the tool would only add a cost and a
dependency for something you can already do. **You (the agent) read the transcript and write the
summary.** (The browser extension's `/summarize` endpoint is the one exception — a local Ollama
model, used only by the extension's UI, not by this CLI.)

The **download** side (`search`/`check`/`song`/`lofi`/`video`) is a plain yt-dlp wrapper that writes
real files into `~/Media/Master-Media-Collection/`.

## When to use it — transcript/summary

Michael gives you a YouTube link and asks for a summary, the key points, "what does this video say",
or similar — **use this tool to get the transcript**, don't try to guess the content from the title.

## When to use it — download

- Michael says "下载一首歌"/"下视频" → **use `song`/`lofi`/`video`**. Don't manually go to a browser
  or install your own copy of yt-dlp — it's already here.
- Michael wants to "先搜搜看有什么"/试听 before deciding → **use `search`**.
- **Before recommending a song**, `check` it first: [命中] means he already has it locally (don't
  re-recommend it as new); [未命中] means it's safe to suggest. `check` takes a title/keywords, never
  a URL — its fuzzy matching is the standard answer for "do I have this already", more reliable than
  eyeballing filenames with `ls`/`find`.
- Typical flow: `check` → (未命中) → recommend → `search` (he wants to preview) → he picks one →
  `song`/`lofi`/`video` to actually save it.
- `song`/`lofi`/`video` accept either a URL or search keywords (first hit is downloaded) — no quotes
  needed for multi-word keywords.
- Execution discipline: once Michael says to download/search something, actually call the command
  immediately — don't just reply "好呀我这就去" and stop. Say you're starting, then start.

## Commands

```bash
ai-youtube-summary info  <url>              # title, channel, duration, which caption languages exist
ai-youtube-summary fetch <url>               # the transcript: captions if they exist, Whisper if not
ai-youtube-summary fetch <url> -o <folder>   # choose the output folder (default: named after the video)
ai-youtube-summary fetch <url> --lang en,zh-Hans   # try these caption languages in order (default: en)
ai-youtube-summary fetch <url> --force-whisper     # skip captions, transcribe with Whisper directly
```

## Workflow

1. **Run `fetch <url>`.** It tries, in order: manual captions in your language list, then
   auto-generated captions in that list, then (only if none exist) downloads the audio only — never
   the video — and transcribes it locally with Whisper. Whichever path was used is in
   `manifest.json`'s `"source"` field (`captions:manual:en`, `captions:auto:en`, or `whisper:small`),
   so you know how trustworthy the text is: manual captions are exact, auto-captions and Whisper can
   mishear a word here and there, especially names and numbers.
2. **Read `transcript.md`** (plain paragraphs) for the summary itself. Use
   `transcript.timestamped.txt` (one line per cue, `[MM:SS]` or `[HH:MM:SS]` markers) when you need
   to cite or jump to a specific moment.
3. **Write the summary yourself**, in your own words. A reasonable default shape: a one-line
   takeaway, 3–6 key points, and (if it's a talk or tutorial with real structure) a short list of
   moments worth jumping to with their timestamps. Match the length to the video: don't write 500
   words summarising a 2-minute clip.
4. **Say which source was used** if it matters for the ask (e.g. "this is from auto-generated
   captions, so names may be misspelled") — don't present a Whisper or auto-caption transcript as if
   it were as reliable as the speaker's own words.

## Install

```bash
# yt-dlp and ffmpeg are assumed already present (this household has them for ai-youtube).
python3 -m venv ~/.venvs/ai-youtube-summary
~/.venvs/ai-youtube-summary/bin/pip install faster-whisper av==18.0.0
# av 19+ breaks faster-whisper 1.2.1's call into PyAV (TypeError: metadata_errors); pin 18.0.0.
```

The main tool itself is pure standard library (no venv needed for it) — only the Whisper fallback
runs in its own venv, the same split `ai-book2video` uses for Kokoro. `WHISPER_PYTHON` overrides the
venv path if it ever moves.

## Known limits

- Caption fetching only tries the languages you give it (default just `en`); a video with only, say,
  Japanese captions and no English ones will fall through to Whisper unless you pass `--lang ja`.
- Whisper's `small` model (the default) is fast on CPU but will mishear uncommon names, jargon and
  numbers more than captions do; say so if it matters, and `--whisper-model medium` trades speed for
  accuracy on a video worth getting right.
- This only reads what was said, not what was shown on screen — a video that is mostly charts, code,
  or silent demonstration will transcribe to very little, and that is a real limit to mention, not a
  bug to paper over.
