"""Download songs / lofi / videos from YouTube (merged in from the former ai-youtube
project), plus the search/check helpers used to decide what's worth downloading.

Unlike `core.fetch`, these functions do real downloads via yt-dlp and write into the
shared Media library — `search`/`check` only ever read/print, `download` writes files.
"""

from __future__ import annotations

import difflib
import os
import re
import subprocess
import sys
import unicodedata

from ai_youtube_summary.errors import SummaryError

HIT_THRESHOLD = 0.60

VALID_EXTS = ('.mp3', '.mp4', '.m4a', '.mkv', '.webm')

SONG_NOISE_WORDS = frozenset([
    "official", "audio", "video", "mv", "feat", "ft", "hd", "hq", "lyrics",
])

_BRACKET_RE = re.compile(r"[\(\[\{（【].*?[\)\]\}）】]")
_SEQUENCE_PREFIX_RE = re.compile(r"^\d+\s*[.\-]\s+")
_HASHTAG_PREFIX_RE = re.compile(r"^#[^\s]+\s+")
_SEPARATORS_RE = re.compile(r"[｜|/⧸／]")
_PUNCT_RE = re.compile(r"[^\w一-鿿\s]")


def _fuzzy_normalize(s: str, noise_words=()) -> str:
    """Normalize a title/filename for fuzzy comparison."""
    s = unicodedata.normalize("NFKC", s)
    s = _BRACKET_RE.sub(" ", s)
    s = _SEQUENCE_PREFIX_RE.sub(" ", s)
    s = _HASHTAG_PREFIX_RE.sub(" ", s)
    s = _SEPARATORS_RE.sub(" ", s)
    s = _PUNCT_RE.sub(" ", s)
    s = s.lower()

    noise = set(noise_words)
    tokens = [t for t in s.split() if t not in noise]
    return " ".join(tokens)


def normalize(s: str) -> str:
    """Normalize a filename/title for fuzzy comparison, binding song-specific noise words."""
    return _fuzzy_normalize(s, noise_words=SONG_NOISE_WORDS)


def score(query_norm: str, file_norm: str) -> float:
    """Similarity in [0, 1] between two already-normalized strings."""
    if not query_norm or not file_norm:
        return 0.0

    if query_norm in file_norm:
        return 1.0

    query_tokens = set(query_norm.split())
    file_tokens = set(file_norm.split())
    if not query_tokens or not file_tokens:
        return 0.0

    if query_tokens <= file_tokens:
        return 0.9 * (len(query_tokens) / len(file_tokens))

    overlap = query_tokens & file_tokens
    token_overlap_ratio = len(overlap) / len(query_tokens | file_tokens)
    seq_ratio = difflib.SequenceMatcher(None, query_norm, file_norm).ratio()
    return max(token_overlap_ratio, seq_ratio * 0.8)


# ── Non-UTF-8 locale protection ───────────────
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Node.js is used as yt-dlp's JavaScript runtime; without it yt-dlp warns and may skip formats.
YTDLP_OPTS = ["--js-runtimes", "node"]

# Downloads go to a folder on the local drive (not Dropbox). Set AI_YOUTUBE_LIBRARY to change it.
_LIBRARY = os.environ.get("AI_YOUTUBE_LIBRARY") or os.path.expanduser("~/Media/Master-Media-Collection")
_DIRS = {
    "song":  os.path.join(_LIBRARY, "Songs"),
    "lofi":  os.path.join(_LIBRARY, "Lofi"),
    "video": os.path.join(_LIBRARY, "Videos"),
}

# Older downloads still live in the Dropbox library; duplicate checks should see them too.
_LEGACY_SONGS = os.path.expanduser("~/Dropbox/Master/Master-Media-Collection/Songs")

VALID_KINDS = frozenset(_DIRS) | {"search", "check"}


def is_url(s: str) -> bool:
    return s.startswith("http://") or s.startswith("https://")


def build_search_prefix(kind: str, query: str) -> str:
    """Wrap query in yt-dlp search prefix when it's not already a URL."""
    if is_url(query):
        return query
    return f"ytsearch1:{query}"


# ── deduplication helpers ───────────────────────


def check(query: str):
    """Scan local media library for a duplicate of `query`. Prints the result (CLI-facing)."""
    dirs_to_scan = [
        ("Songs", _DIRS["song"]),
        ("Lofi", _DIRS["lofi"]),
        ("Videos", _DIRS["video"]),  # .vtt 等字幕文件由下方白名单过滤
        ("Songs (old Dropbox)", _LEGACY_SONGS),
    ]
    best_score = -1.0
    best_file = None
    best_label = None
    scan_summary = []

    query_norm = normalize(query)

    for label, directory in dirs_to_scan:
        if not os.path.isdir(directory):
            continue
        try:
            entries = os.listdir(directory)
        except OSError:
            continue
        files = [
            e for e in entries
            if os.path.isfile(os.path.join(directory, e))
            and e.lower().endswith(VALID_EXTS)
        ]
        count = len(files)
        if count:
            scan_summary.append(f"{label} {count}")
        for filename in files:
            stem, _ = os.path.splitext(filename)
            file_norm = normalize(stem)
            s = score(query_norm, file_norm)
            if s > best_score:
                best_score = s
                best_file = filename
                best_label = label

    if not scan_summary:
        print("[info] 媒体库为空,无法查重")
        return

    scan_desc = " + ".join(scan_summary)
    print(f'[check] 查重 "{query}"(扫描 {scan_desc} 个文件)\n')
    print(f"  最相似: {best_file}   [{best_label}]")
    print(f"          相似度 {best_score:.2f}\n")

    if best_score >= HIT_THRESHOLD:
        print("[命中] 本地已经有这首歌了,不用再推荐/下载。")
    else:
        print("[未命中] 本地没有这首歌的重复记录。")


def _format_duration(seconds_text: str) -> str:
    """Convert yt-dlp duration seconds to m:ss; treat NA as --:--."""
    if seconds_text == "NA":
        return "--:--"
    try:
        total = int(seconds_text)
    except ValueError:
        return "--:--"
    minutes, secs = divmod(total, 60)
    return f"{minutes}:{secs:02d}"


def search(query: str, count: int = 5):
    """Search YouTube and print top `count` results without downloading. Prints (CLI-facing)."""
    target = f"ytsearch{count}:{query}"
    args = [
        "yt-dlp",
        *YTDLP_OPTS,
        "--flat-playlist",
        "--no-warnings",
        "--print", "%(title)s\t%(url)s\t%(duration)s",
        target,
    ]

    print(f'[search] 关键词:"{query}"  返回 {count} 条结果:\n')

    result = subprocess.run(args, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"[error] yt-dlp exited with code {result.returncode}", file=sys.stderr)
        if result.stderr:
            print(result.stderr.strip(), file=sys.stderr)
        sys.exit(result.returncode)

    lines = [line for line in result.stdout.splitlines() if line.strip()]
    if not lines:
        print(f'[info] 没有搜到 "{query}" 的结果')
        return

    for idx, line in enumerate(lines, start=1):
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        title, url, duration_text = parts[0], parts[1], parts[2]
        duration = _format_duration(duration_text)
        print(f"  {idx}. {title}")
        print(f"     {url}  ({duration})")
        print()

    print("[ok] 想下载哪首,告诉 Michael 对应编号或标题,用 ai-youtube-summary song 下载。")


def yt_dlp_args(kind: str, target: str) -> list[str]:
    """Build yt-dlp argument list for the given download kind."""

    out_dir = _DIRS[kind]
    base = [
        "yt-dlp",
        *YTDLP_OPTS,
        "--no-playlist",
        "--no-warnings",
        "--progress",
        "-o", f"{out_dir}/%(title)s.%(ext)s",
        "--windows-filenames",
    ]

    if kind in ("song", "lofi"):
        quality = "0" if kind == "song" else "5"  # 0=best, 5≈192k
        return [
            "yt-dlp",
            *YTDLP_OPTS,
            "--no-playlist",
            "--no-warnings",
            "--progress",
            "-o", f"{out_dir}/%(title)s.%(ext)s",
            "--windows-filenames",
            "-x",
            "--audio-format", "mp3",
            "--audio-quality", quality,
            "--embed-thumbnail",
            "--embed-metadata",
            "--add-metadata",
            target,
        ]

    # video — short films, documentaries, etc.
    return base + [
        "-f", "bestvideo[vcodec^=avc1][ext=mp4]+bestaudio[ext=m4a]/bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "--merge-output-format", "mp4",
        "--write-auto-sub",
        "--sub-lang", "en,zh",
        "--embed-subs",
        "--print", "after_move:filepath",
        target,
    ]


def _extract_downloaded_path(output: str | None, directory: str) -> str | None:
    """Parse yt-dlp --print after_move:filepath output to find the actual downloaded file."""
    if not output:
        return None
    directory = os.path.abspath(directory)
    for line in reversed(output.splitlines()):
        line = line.strip()
        if line.startswith(directory) and line.lower().endswith(VALID_EXTS):
            return line
    return None


def _video_codec_name(path: str) -> tuple[str | None, str | None]:
    """Ask ffprobe for the first video stream's codec_name. Returns (codec_name, error_message)."""
    args = [
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=codec_name",
        "-of", "csv=p=0",
        path,
    ]
    try:
        result = subprocess.run(args, capture_output=True, text=True, check=False, timeout=30)
    except FileNotFoundError:
        return None, "ffprobe 未安装"
    except OSError as exc:
        return None, f"无法调用 ffprobe: {exc}"
    except subprocess.TimeoutExpired:
        return None, "ffprobe 调用超时"
    if result.returncode != 0:
        err = result.stderr.strip() or f"ffprobe 退出码 {result.returncode}"
        return None, err
    stdout = result.stdout.strip()
    if not stdout:
        return None, "ffprobe 未返回视频流信息"
    return stdout.splitlines()[0], None


def _has_audio_stream(path: str) -> tuple[bool | None, str | None]:
    """Ask ffprobe whether the file has at least one audio stream. Returns (has_audio, error_message)."""
    args = [
        "ffprobe", "-v", "error",
        "-select_streams", "a",
        "-show_entries", "stream=codec_type",
        "-of", "csv=p=0",
        path,
    ]
    try:
        result = subprocess.run(args, capture_output=True, text=True, check=False, timeout=30)
    except FileNotFoundError:
        return None, "ffprobe 未安装"
    except OSError as exc:
        return None, f"无法调用 ffprobe: {exc}"
    except subprocess.TimeoutExpired:
        return None, "ffprobe 调用超时"
    if result.returncode != 0:
        err = result.stderr.strip() or f"ffprobe 退出码 {result.returncode}"
        return None, err
    return bool(result.stdout.strip()), None


def _check_downloaded_video_codec(path: str):
    """Warn (print) if the downloaded video's codec is not H.264 or if validation failed."""
    codec, error = _video_codec_name(path)
    if error:
        print(f"\n[warn] 视频编码校验失败: {error}")
        print("       建议自行用 ffprobe 检查该文件。")
        return
    if codec != "h264":
        print(f"\n[warn] 视频流为 {codec},不是 h264。建议转码:")
        import shlex
        print(f"       ffmpeg -i {shlex.quote(path)} -c:v libx264 -crf 18 -c:a copy output.mp4")


def _ensure_downloaded_video_has_audio(path: str) -> None:
    """Raise SummaryError (and delete the file) if a downloaded video has no audio track.

    yt-dlp's format selector occasionally falls back to a video-only DASH stream for
    certain videos without erroring — it reports success and merges into a normal-looking
    .mp4 that has no audio stream at all. Treat this as a failed download.
    """
    has_audio, error = _has_audio_stream(path)
    if error:
        print(f"\n[warn] 音轨校验失败: {error}")
        print("       建议自行用 ffprobe 检查该文件。")
        return
    if has_audio:
        return
    try:
        os.remove(path)
    except OSError:
        pass
    raise SummaryError(
        f"下载结果没有音轨(视频流正常,但音频流缺失),已删除残缺文件: {path}"
    )


def download(kind: str, query: str) -> str:
    """Download a song/lofi/video from YouTube using yt-dlp.

    Returns the downloaded file's path when yt-dlp reports one (always true for
    "video"; "song"/"lofi" fall back to the output directory since yt-dlp's audio
    path isn't printed the same way). Raises SummaryError on failure — callers that
    want CLI-style exit codes should catch it themselves.
    """
    target = build_search_prefix(kind, query)
    args = yt_dlp_args(kind, target)

    os.makedirs(_DIRS[kind], exist_ok=True)
    print(f"[info] type={kind}  target={target}")
    print(f"[info] output dir: {_DIRS[kind]}\n")

    result = subprocess.run(args, capture_output=True, text=True)

    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)

    if result.returncode != 0:
        raise SummaryError(f"yt-dlp exited with code {result.returncode}")

    downloaded_path = _extract_downloaded_path(result.stdout, _DIRS[kind])

    if kind == "video":
        if downloaded_path:
            _check_downloaded_video_codec(downloaded_path)
            _ensure_downloaded_video_has_audio(downloaded_path)
        else:
            print("\n[warn] 无法确定本次下载的视频路径,跳过编码校验。")

    final_path = downloaded_path or _DIRS[kind]
    print(f"\n[ok] Download complete -> {final_path}")
    return final_path
