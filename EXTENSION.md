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

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /status | List all active tasks and their status |
| POST | /fetch | Start a fetch. Body: `{url: "...", lang: ["en"]}` |
| GET | /task/{id} | Poll for task progress (status: pending/fetching/done/failed) |
| GET | /info | Quick video info without transcription |

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
