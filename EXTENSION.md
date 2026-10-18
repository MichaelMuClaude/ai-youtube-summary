# ai-youtube-summary — YouTube Video Summary for your Browser

A browser extension that fetches YouTube transcript summaries in your side panel, powered by `[ai-youtube-summary](https://github.com/MichaelMuClaude/ai-youtube-summary)` CLI.

## Architecture

```
Browser Extension  <HTTP API>  Local Server (port 9877)
                                      |
                              ai-youtube-summary CLI
                                      |
                               yt-dlp + Whisper
```

**Why a local server?**  
The extension runs in browser JS and cannot execute Python processes. A lightweight HTTP bridge wraps the CLI as REST endpoints.

## Quick Start

### 1. Start the API Server

```bash
cd ~/repos/ai-youtube-summary
python3 -m server.api
```

Or directly:
```bash
cd ~/repos/ai-youtube-summary && python server/api.py
```

The server starts on `http://127.0.0.1:9877` with CORS enabled for any origin.

### 2. Load the Extension in Edge

1. Open **edge://extensions** in Microsoft Edge
2. Enable **Developer mode** (toggle at bottom-left)
3. Click **Load unpacked**
4. Select the `extension/` folder

### 3. Use It

- Navigate to any YouTube video page
- Click the side panel icon (puzzle piece → "YouTube Video Summary")
- Or click the extension toolbar icon and open side panel
- The transcript will be fetched automatically
- To save the actual file instead (or as well), pick **Audio (mp3)** or **Video (mp4)** in the
  Download row and click **Download** — it saves straight into your local Media library
  (`~/Media/Master-Media-Collection/Songs` or `.../Videos`), the same place the `ai-youtube-summary
  song`/`video` CLI commands write to

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /status | List all active tasks and their status |
| POST | /fetch | Start a fetch. Body: `{url: "...", lang: ["en"]}` |
| GET | /task/{id} | Poll for task progress (status: pending/fetching/done/failed) |
| GET | /info | Quick video info without transcription |
| POST | /summarize | Summarize via local Ollama. Body: `{title, transcript, lang}` (`lang`: `"zh"` default, `"en"`, or `"auto"` to match the transcript) |
| POST | /download | Download the video itself. Body: `{url, kind}` (`kind`: `"song"` for best-quality mp3, or `"video"` for mp4+subs). Returns `{id, status}`, poll `/task/{id}` same as `/fetch`; on `"done"` the task has a `path` field with where it was saved |

## Extension Files

```
extension/
  manifest.json      # Edge extension manifest v3
  sidepanel.html     # Side panel UI template
  sidepanel.css      # Side panel styles
  sidepanel.js       # Side panel logic (fetch + poll + render)
  popup.html         # Toolbar popup
  popup.js           # Popup click handler
  icon.svg           # Extension icon
```

## Requirements

- yt-dlp on PATH
- ffmpeg on PATH
- Python 3.9+ for the API server
- Microsoft Edge (or Chrome with manifest v2 mode)
- [Ollama](https://ollama.com) running locally on port 11434, with the model named in
  `OLLAMA_MODEL` (`server/api.py`) pulled — default is `qwen3.6:35b-a3b`

### A local GPU is effectively required for the summary step

Caption fetching needs no GPU at all (no model runs), and the Whisper fallback (for videos
with no captions) currently runs CPU-only on this project — see `transcribe_whisper.py` for
why GPU support there is deferred.

But the **summarization** step calls a real LLM through Ollama. Even a "small" local model in
this class (a few billion active parameters, more if you pick a denser one than the MoE
default) is impractical to run well on CPU alone — expect it to be extremely slow, or to
time out the 180s limit in `server/api.py`, on a CPU-only machine. If Ollama has no usable
GPU, either point `OLLAMA_MODEL` at a much smaller model (e.g. `openbmb/minicpm5:latest`,
~1B params, still CPU-runnable but noticeably lower summary quality) or skip the `/summarize`
call entirely and just read the Transcript/Raw JSON tabs.
