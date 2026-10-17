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
import uuid
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from socketserver import ThreadingMixIn
from urllib.parse import parse_qs, urlparse

# Config
BASE_DIR   = Path(__file__).resolve().parent.parent
TMP_DIR    = BASE_DIR / "tmp" / "browser"
IP         = "127.0.0.1"
PORT       = 9877
LAUNCHER   = str(Path.home() / ".local/bin/ai-youtube-summary")

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

    cmd = ["python3", "-m", "ai_youtube_summary", "fetch", url]
    if langs:
        for lang in langs:
            cmd += ["--lang", lang]

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
