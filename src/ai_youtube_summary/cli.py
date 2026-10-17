from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from ai_youtube_summary import core
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


def main() -> None:
    parser = argparse.ArgumentParser(prog="ai-youtube-summary",
                                     description="Get a clean transcript of a YouTube video, so an agent can summarise it.")
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

    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
