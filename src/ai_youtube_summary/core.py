"""Get a clean transcript of a YouTube video: captions when they exist (fast, free, no download),
local Whisper transcription when they don't (downloads audio only, never the video).

Summarising the transcript is deliberately not this module's job. Once the text is in an agent's
context, writing the summary is ordinary conversation; baking an LLM call into this tool would only
add an API dependency and a cost for something a reader can already do. See SKILL.md.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from ai_youtube_summary import vtt
from ai_youtube_summary.errors import SummaryError

WHISPER_PYTHON = os.environ.get("WHISPER_PYTHON", str(Path.home() / ".venvs" / "ai-youtube-summary" / "bin" / "python"))
WHISPER_SCRIPT = Path(__file__).resolve().parent / "transcribe_whisper.py"
DEFAULT_LANGS = ("en",)


@dataclass
class Transcript:
    cues: list[vtt.Cue]
    source: str  # "captions:manual:en" | "captions:auto:en" | "whisper:small"
    language: str

    @property
    def text(self) -> str:
        return vtt.to_text(self.cues)

    @property
    def timestamped(self) -> str:
        return vtt.to_timestamped(self.cues)


def require_yt_dlp() -> str:
    found = shutil.which("yt-dlp")
    if not found:
        raise SummaryError("yt-dlp is not installed or not on PATH")
    return found


def _run_json(args: list[str]) -> dict:
    result = subprocess.run(args, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        raise SummaryError(f"yt-dlp failed: {result.stderr.strip()[-500:]}")
    return json.loads(result.stdout)


def video_info(url: str) -> dict:
    """Title, channel, duration, upload date, and which caption languages are available."""
    require_yt_dlp()
    data = _run_json(["yt-dlp", "--skip-download", "--dump-json", url])
    return {
        "id": data.get("id"),
        "title": data.get("title"),
        "channel": data.get("channel") or data.get("uploader"),
        "duration_seconds": data.get("duration"),
        "upload_date": data.get("upload_date"),
        "url": data.get("webpage_url", url),
        "manual_caption_langs": sorted((data.get("subtitles") or {}).keys()),
        "auto_caption_langs": sorted((data.get("automatic_captions") or {}).keys()),
    }


def fetch_captions(url: str, workdir: Path, langs: tuple[str, ...] = DEFAULT_LANGS) -> tuple[Path, str, bool] | None:
    """Download only a caption file, no video or audio. Tries each language in `langs`, manual
    captions before auto-generated ones. Returns (vtt_path, lang, is_auto) or None if nothing matched."""
    require_yt_dlp()
    workdir.mkdir(parents=True, exist_ok=True)
    for auto in (False, True):
        for lang in langs:
            args = ["yt-dlp", "--skip-download", "--sub-lang", lang, "--sub-format", "vtt",
                    "--write-auto-sub" if auto else "--write-sub", "-o", str(workdir / "%(id)s"), url]
            result = subprocess.run(args, capture_output=True, text=True, timeout=120)
            match = next(workdir.glob(f"*.{lang}.vtt"), None)
            if result.returncode == 0 and match:
                return match, lang, auto
    return None


def fetch_audio(url: str, workdir: Path) -> Path:
    """Download audio only (no video track) to workdir/audio.*, return its path."""
    require_yt_dlp()
    workdir.mkdir(parents=True, exist_ok=True)
    target = workdir / "audio.%(ext)s"
    result = subprocess.run(
        ["yt-dlp", "-f", "bestaudio/best", "-x", "--audio-format", "mp3", "-o", str(target), url],
        capture_output=True, text=True, timeout=600,
    )
    if result.returncode != 0:
        raise SummaryError(f"audio download failed: {result.stderr.strip()[-500:]}")
    found = next(workdir.glob("audio.*"), None)
    if not found:
        raise SummaryError("yt-dlp reported success but no audio file was written")
    return found


def transcribe_audio(audio_path: Path, model_size: str = "small") -> tuple[list[vtt.Cue], str]:
    """Local Whisper transcription, run in ai-youtube-summary's own venv."""
    if not Path(WHISPER_PYTHON).exists():
        raise SummaryError(f"Whisper is not installed at {WHISPER_PYTHON}; set WHISPER_PYTHON or install it there")
    out = audio_path.with_suffix(".whisper.json")
    result = subprocess.run(
        [WHISPER_PYTHON, str(WHISPER_SCRIPT), str(audio_path), str(out), model_size],
        capture_output=True, text=True, timeout=3600,
    )
    if result.returncode != 0 or not out.exists():
        raise SummaryError(f"Whisper transcription failed: {(result.stderr or result.stdout).strip()[-500:]}")
    data = json.loads(out.read_text(encoding="utf-8"))
    cues = [vtt.Cue(start, text) for start, text in data["cues"]]
    return cues, data["language"]


def fetch(url: str, outdir: Path, langs: tuple[str, ...] = DEFAULT_LANGS, model_size: str = "small",
          use_captions: bool = True, keep_audio: bool = False) -> dict:
    """The whole pipeline: captions first, Whisper only if there are none. Writes info.json,
    transcript.md, transcript.timestamped.txt and manifest.json into `outdir`; returns the manifest."""
    outdir.mkdir(parents=True, exist_ok=True)
    info = video_info(url)
    transcript: Transcript | None = None

    if use_captions:
        found = fetch_captions(url, outdir, langs)
        if found:
            path, lang, auto = found
            cues = vtt.parse(path.read_text(encoding="utf-8"))
            transcript = Transcript(cues, f"captions:{'auto' if auto else 'manual'}:{lang}", lang)
            if path.exists():
                path.unlink()

    if transcript is None:
        audio_dir = outdir / "audio-work"
        audio_path = fetch_audio(url, audio_dir)
        cues, language = transcribe_audio(audio_path, model_size)
        transcript = Transcript(cues, f"whisper:{model_size}", language)
        if not keep_audio:
            shutil.rmtree(audio_dir, ignore_errors=True)

    (outdir / "info.json").write_text(json.dumps(info, indent=2, ensure_ascii=False), encoding="utf-8")
    (outdir / "transcript.md").write_text(transcript.text, encoding="utf-8")
    (outdir / "transcript.timestamped.txt").write_text(transcript.timestamped, encoding="utf-8")
    manifest = {**info, "source": transcript.source, "language": transcript.language, "cue_count": len(transcript.cues)}
    (outdir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return manifest
