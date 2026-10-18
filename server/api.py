#!/usr/bin/env python3
"""Local HTTP API for ai-youtube-summary.
Python stdlib only — no pip install needed.

Usage: cd ~/repos/ai-youtube-summary && python server/api.py
Runs on http://127.0.0.1:9877
"""

import atexit
import json
import os
import shutil
import subprocess as sp
import sys
import threading
import urllib.error
import urllib.request
import uuid
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from socketserver import ThreadingMixIn
from urllib.parse import parse_qs, quote, urlparse

# Config
BASE_DIR   = Path(__file__).resolve().parent.parent
TMP_DIR    = BASE_DIR / "tmp" / "browser"
IP         = "127.0.0.1"
PORT       = 9877
LAUNCHER   = str(Path.home() / ".local/bin/ai-youtube-summary")

# The download/search/check logic (merged in from the former ai-youtube project) is
# imported directly rather than shelled out to, since it's now part of this same package.
sys.path.insert(0, str(BASE_DIR / "src"))
from ai_youtube_summary import download as download_mod  # noqa: E402
from ai_youtube_summary.errors import SummaryError  # noqa: E402

DOWNLOAD_KINDS = {"song", "video"}  # extension exposes audio (best mp3) and video (mp4)

# Local-model summarization. Proxied through this server (instead of the
# extension calling Ollama directly) because Ollama rejects requests whose
# Origin header is chrome-extension://... with a 403 by default; a plain
# Python request has no such header and goes straight through.
#
# OLLAMA_MODEL defaults to a model that happens to be pulled on the machine
# this was built on — it's very unlikely to exist on a fresh clone. Override
# it with the OLLAMA_MODEL env var to whatever `ollama list` shows you have
# (see README.md's Quick start for picking one that fits your GPU).
OLLAMA_URL         = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434/api/chat")
OLLAMA_MODEL       = os.environ.get("OLLAMA_MODEL", "qwen3.6:35b-a3b")
SUMMARY_MAX_CHARS  = 20000
SUMMARY_SYSTEM_PROMPT_BASE = (
    "You are a careful video summarizer. Read the YouTube transcript the user gives you. "
    "Structure your reply as markdown with: a one-line overall summary, then a '## Key Points' "
    "bullet list, then a '## Notable Moments' bullet list (include a timestamp like mm:ss when "
    "the transcript gives timing cues). Be concise and do not invent facts not in the transcript."
)
SUMMARY_LANG_INSTRUCTIONS = {
    "zh": "Reply in Simplified Chinese (简体中文), regardless of what language the transcript is in.",
    "en": "Reply in English, regardless of what language the transcript is in.",
    "auto": "Reply in the same language the transcript is mostly written in.",
}


def _summarize(title, transcript, lang=None):
    text = transcript or ""
    truncated = len(text) > SUMMARY_MAX_CHARS
    if truncated:
        text = text[:SUMMARY_MAX_CHARS]

    user_prompt = "Title: " + (title or "(unknown)") + "\n\nTranscript:\n" + text
    if truncated:
        user_prompt += "\n\n[transcript truncated for length]"

    lang_instruction = SUMMARY_LANG_INSTRUCTIONS.get(lang, SUMMARY_LANG_INSTRUCTIONS["zh"])
    system_prompt = SUMMARY_SYSTEM_PROMPT_BASE + " " + lang_instruction

    payload = json.dumps({
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
    }).encode("utf-8")

    req = urllib.request.Request(OLLAMA_URL, data=payload,
                                  headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as resp:
        data = json.loads(resp.read())
    content = (data.get("message") or {}).get("content")
    if not content:
        raise ValueError("Ollama returned no content")
    return content

# Task store
_tasks_     = {}
_lock       = threading.Lock()
TMP_DIR.mkdir(parents=True, exist_ok=True)


def _cleanup():
    try:
        shutil.rmtree(TMP_DIR, ignore_errors=True)
    except Exception:
        pass
atexit.register(_cleanup)


# ---- Background fetch worker ----

def _fetch_task(task_id, url, langs):
    """Runs in a background thread."""
    outdir = TMP_DIR / task_id
    outdir.mkdir(parents=True, exist_ok=True)

    cmd = ["python3", "-m", "ai_youtube_summary", "fetch", url, "-o", str(outdir)]
    if langs:
        cmd += ["--lang", ",".join(langs)]

    env = os.environ.copy()
    src_path = str(BASE_DIR / "src")
    old = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = src_path + ":" + old if old else src_path

    with _lock:
        _tasks_[task_id] = {"status": "fetching", "progress": "Starting..."}

    result = sp.run(cmd, capture_output=True, text=True, timeout=600,
                    cwd=str(BASE_DIR), env=env)

    manifest_path = outdir / "manifest.json"
    if result.returncode != 0 or not manifest_path.exists():
        with _lock:
            _tasks_[task_id]["status"] = "failed"
            _tasks_[task_id]["progress"] = (result.stderr or result.stdout).strip()[-500:]
        return

    manifest = json.loads(manifest_path.read_text())
    with _lock:
        _tasks_[task_id]["manifest"] = manifest
        _tasks_[task_id]["status"] = "done"
        _tasks_[task_id]["progress"] = "Ready!"
        
        tx = outdir / "transcript.md"
        if tx.exists():
            _tasks_[task_id]["transcript"] = tx.read_text(encoding="utf-8")
        
        ts = outdir / "transcript.timestamped.txt"
        if ts.exists():
            _tasks_[task_id]["timestamped"] = ts.read_text(encoding="utf-8")


def _download_task(task_id, url, kind):
    """Runs in a background thread. Downloads straight into the shared Media library."""
    with _lock:
        _tasks_[task_id] = {"status": "fetching", "progress": "Starting download..."}

    try:
        path = download_mod.download(kind, url)
    except SummaryError as error:
        with _lock:
            _tasks_[task_id]["status"] = "failed"
            _tasks_[task_id]["progress"] = str(error)
        return
    except Exception as error:
        with _lock:
            _tasks_[task_id]["status"] = "failed"
            _tasks_[task_id]["progress"] = str(error)
        return

    with _lock:
        _tasks_[task_id]["status"] = "done"
        _tasks_[task_id]["progress"] = "Ready!"
        _tasks_[task_id]["path"] = path


# ---- HTTP Handler ----

class H(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # suppress logs

    def _respond(self, code, body):
        raw = json.dumps(body) if isinstance(body, dict) else str(body)
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(raw.encode("utf-8"))

    def do_OPTIONS(self):
        self._respond(204, {})

    def do_GET(self):
        parsed = urlparse(self.path)
        path   = parsed.path
        params = parse_qs(parsed.query)

        if path == "/config":
            self._respond(200, {"ollama_model": OLLAMA_MODEL})
            return

        if path == "/status":
            with _lock:
                result = {}
                for tid, info in _tasks_.items():
                    d = dict(info)
                    for k in ("transcript", "timestamped", "manifest"):
                        d.pop(k, None)
                    result[tid] = d
            self._respond(200, result)
            return

        if path == "/info" and params.get("url"):
            url = params["url"][0]
            try:
                r = sp.run(["yt-dlp", "--skip-download", "--dump-json", url],
                           capture_output=True, text=True, timeout=30)
                if r.returncode != 0:
                    raise Exception(r.stderr[:500])
                data = json.loads(r.stdout)
            except Exception as e:
                self._respond(500, {"error": str(e)})
                return

            info = {
                "id":     data.get("id"),
                "title":  data.get("title"),
                "channel": data.get("channel") or data.get("uploader"),
                "duration_seconds": data.get("duration"),
                "upload_date":      data.get("upload_date"),
                "url":              data.get("webpage_url", url),
            }
            self._respond(200, info)
            return

        if path.startswith("/task/"):
            task_id = path[6:]
            with _lock:
                task = dict(_tasks_.get(task_id, {"status": "not found"}))
            self._respond(200, task)
            return

        if path.startswith("/download/file/"):
            task_id = path[len("/download/file/"):]
            with _lock:
                task = dict(_tasks_.get(task_id, {}))
            file_path = task.get("path")
            if task.get("status") != "done" or not file_path:
                self._respond(404, {"error": "Not found"})
                return
            file_path = Path(file_path)
            if not file_path.is_file():
                self._respond(404, {"error": "File no longer exists on disk"})
                return

            ascii_name = file_path.name.encode("ascii", "ignore").decode("ascii") or "download"
            quoted_name = quote(file_path.name)
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(file_path.stat().st_size))
            self.send_header(
                "Content-Disposition",
                "attachment; filename=\"%s\"; filename*=UTF-8''%s" % (ascii_name, quoted_name),
            )
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            with open(file_path, "rb") as f:
                shutil.copyfileobj(f, self.wfile)
            return

        self._respond(404, {"error": "Not found"})

    def do_POST(self):
        parsed = urlparse(self.path)
        path   = parsed.path

        if path == "/fetch":
            length = int(self.headers.get("Content-Length", 0))
            body   = json.loads(self.rfile.read(length))
            url    = body.get("url")
            lang   = body.get("lang", ["en"])

            if not url:
                self._respond(400, {"error": "Missing 'url'"})
                return

            task_id = str(uuid.uuid4())[:8]
            with _lock:
                _tasks_[task_id] = {"status": "pending", "progress": "Queued..."}

            t = threading.Thread(target=_fetch_task, args=(task_id, url, lang))
            t.daemon = True
            t.start()

            self._respond(202, {"id": task_id, "status": "queued"})
            return

        if path == "/download":
            length = int(self.headers.get("Content-Length", 0))
            body   = json.loads(self.rfile.read(length))
            url    = body.get("url")
            kind   = body.get("kind")

            if not url:
                self._respond(400, {"error": "Missing 'url'"})
                return
            if kind not in DOWNLOAD_KINDS:
                self._respond(400, {"error": "'kind' must be one of: " + ", ".join(sorted(DOWNLOAD_KINDS))})
                return

            task_id = str(uuid.uuid4())[:8]
            with _lock:
                _tasks_[task_id] = {"status": "pending", "progress": "Queued..."}

            t = threading.Thread(target=_download_task, args=(task_id, url, kind))
            t.daemon = True
            t.start()

            self._respond(202, {"id": task_id, "status": "queued"})
            return

        if path == "/summarize":
            length = int(self.headers.get("Content-Length", 0))
            body   = json.loads(self.rfile.read(length))
            title      = body.get("title")
            transcript = body.get("transcript")
            lang       = body.get("lang")

            if not transcript:
                self._respond(400, {"error": "Missing 'transcript'"})
                return

            try:
                content = _summarize(title, transcript, lang)
            except urllib.error.URLError as e:
                self._respond(502, {"error": "Could not reach Ollama on localhost:11434 (" + str(e) + ")"})
                return
            except Exception as e:
                self._respond(502, {"error": str(e)})
                return

            self._respond(200, {"content": content})
            return

        self._respond(404, {"error": "Not found"})


class Server(ThreadingMixIn, HTTPServer):
    daemon_threads = True


if __name__ == "__main__":
    srv = Server((IP, PORT), H)
    print("ai-youtube-summary API on http://%s:%d" % (IP, PORT))
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        srv.shutdown()
