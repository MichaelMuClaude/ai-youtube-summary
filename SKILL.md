---
name: ai-youtube-summary
description: Get a clean, de-duplicated transcript of a YouTube video — official captions when they exist (no download at all), local Whisper transcription (audio only, no video download) when they don't — then read it and write the summary yourself. Use this whenever someone wants a YouTube video summarised, its key points pulled out, or asks "what is this video about" with a YouTube link.
compatibility: Python 3.9+, yt-dlp on PATH, ffmpeg (for audio extraction). Whisper fallback needs its own venv with faster-whisper installed (see Install below); without it, videos with no captions in the requested language will fail with a clear error instead of being summarised.
---

# ai-youtube-summary — a YouTube video's transcript, ready to summarise

## What this is and is not

This tool's job stops at **getting you a clean transcript**. It does not call an LLM to write the
summary itself, on purpose: once the transcript is in an agent's context, writing a good summary is
ordinary conversation, and baking an API call into the tool would only add a cost and a dependency
for something you can already do. **You (the agent) read the transcript and write the summary.**

## When to use it

Michael gives you a YouTube link and asks for a summary, the key points, "what does this video say",
or similar — **use this tool to get the transcript**, don't try to guess the content from the title.

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
