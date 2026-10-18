from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from ai_youtube_summary import core, download as download_mod
from ai_youtube_summary.errors import SummaryError


def _slug(title: str, video_id: str) -> str:
    slug = re.sub(r"[^\w\-]+", "-", title or video_id).strip("-")[:60]
    return slug or video_id


def cmd_fetch(args: argparse.Namespace) -> int:
    langs = tuple(args.lang.split(",")) if args.lang else core.DEFAULT_LANGS
    try:
        info = core.video_info(args.url)
        outdir = Path(args.output) if args.output else Path(_slug(info["title"], info["id"]))
        manifest = core.fetch(args.url, outdir, langs=langs, model_size=args.whisper_model,
                              use_captions=not args.force_whisper, keep_audio=args.keep_audio)
    except SummaryError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    mins = (manifest["duration_seconds"] or 0) / 60
    print(f"{manifest['title']}  ({mins:.1f} min, {manifest['channel']})")
    print(f"source: {manifest['source']}  ({manifest['cue_count']} cues, language {manifest['language']})")
    print(f"wrote {outdir}/transcript.md, transcript.timestamped.txt, info.json, manifest.json")
    return 0


def cmd_info(args: argparse.Namespace) -> int:
    try:
        info = core.video_info(args.url)
    except SummaryError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    for key, value in info.items():
        print(f"{key}: {value}")
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    query = " ".join(args.query)
    if download_mod.is_url(query):
        print("[info] search 是关键词搜索;有链接请直接用 song/lofi/video 下载")
        return 0
    download_mod.search(query)
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    query = " ".join(args.query)
    if download_mod.is_url(query):
        print("[info] check 查的是歌名;有链接直接用 song/lofi 下载")
        return 0
    download_mod.check(query)
    return 0


def _cmd_download(kind: str, args: argparse.Namespace) -> int:
    query = " ".join(args.query)
    try:
        download_mod.download(kind, query)
    except SummaryError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


def cmd_song(args: argparse.Namespace) -> int:
    return _cmd_download("song", args)


def cmd_lofi(args: argparse.Namespace) -> int:
    return _cmd_download("lofi", args)


def cmd_video(args: argparse.Namespace) -> int:
    return _cmd_download("video", args)


def main() -> None:
    parser = argparse.ArgumentParser(prog="ai-youtube-summary",
                                     description="Get a YouTube video's transcript/summary, or download it, from one tool.")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("fetch", help="get the transcript (captions if they exist, local Whisper if not)")
    p.add_argument("url")
    p.add_argument("-o", "--output", help="folder to write into (default: a folder named after the video)")
    p.add_argument("--lang", help="comma-separated caption languages to try, in order (default: en)")
    p.add_argument("--force-whisper", action="store_true", help="skip captions and transcribe with Whisper directly")
    p.add_argument("--whisper-model", default="small", help="Whisper model size if captions are unavailable (default: small)")
    p.add_argument("--keep-audio", action="store_true", help="keep the downloaded audio file instead of deleting it")
    p.set_defaults(func=cmd_fetch)

    p = sub.add_parser("info", help="print a video's title, channel, duration and which caption languages exist")
    p.add_argument("url")
    p.set_defaults(func=cmd_info)

    p = sub.add_parser("search", help="search YouTube, print the top 5 results (no download)")
    p.add_argument("query", nargs="+", help="keywords (no quotes needed)")
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("check", help="check whether something is already in the local media library")
    p.add_argument("query", nargs="+", help="a title/keywords to check (no quotes needed)")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("song", help="download audio (best quality mp3) to the Songs library")
    p.add_argument("query", nargs="+", help="a URL, or keywords to search+download the first hit")
    p.set_defaults(func=cmd_song)

    p = sub.add_parser("lofi", help="download audio (192kbps mp3) to the Lofi library")
    p.add_argument("query", nargs="+", help="a URL, or keywords to search+download the first hit")
    p.set_defaults(func=cmd_lofi)

    p = sub.add_parser("video", help="download video (mp4, with subtitles) to the Videos library")
    p.add_argument("query", nargs="+", help="a URL, or keywords to search+download the first hit")
    p.set_defaults(func=cmd_video)

    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
