"""Clean YouTube's VTT captions into a plain, de-duplicated transcript.

YouTube's auto-captions scroll: each cue repeats the previous (already-settled) line and adds the
new line being typed out word by word with inline <00:00:01.234><c>...</c> timing tags, plus
near-zero-duration "freeze" cues that just repeat the same line again. Manual captions are usually
one clean line per cue with no tags. Both are handled by the same rule: in each cue, take the last
non-blank line, strip the tags, and drop it if it is identical to the line before it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

TIME = re.compile(r"(\d+):(\d\d):(\d\d)[.,](\d\d\d)")
CUE_LINE = re.compile(r"^\s*(\d+:\d\d:\d\d[.,]\d\d\d)\s*-->\s*(\d+:\d\d:\d\d[.,]\d\d\d)")
TAG = re.compile(r"<[^>]*>")
CREDITS = re.compile(r"^(translator|reviewer|transcri(ber|bed by)|proofreader|subtitles? by|captions? by)\s*:", re.I)


@dataclass
class Cue:
    start: float
    text: str


def _seconds(stamp: str) -> float:
    h, m, s, ms = TIME.match(stamp).groups()
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


def parse(vtt_text: str) -> list[Cue]:
    """Parse a VTT file's text into clean cues, one per new piece of spoken content.

    Two caption styles need two different rules, and a block can be either:
    - YouTube's auto-captions scroll: a block repeats the previous block's line(s) verbatim, then
      adds one new line. The repeated lines must be dropped, or every word appears twice.
    - Manual captions (TED, Amara, ...) wrap one utterance over several lines with no repetition,
      and often open with a "Translator: ... / Reviewer: ..." credits cue that was never spoken.

    Rule: compare each block's lines against the end of the previous block's lines. Drop the
    longest matching run at the start (that is the repeated part); whatever is left is new. A
    block with nothing left after that (a pure repeat) is skipped; so is a credits line.
    """
    lines = vtt_text.splitlines()
    cues: list[Cue] = []
    previous_lines: list[str] = []
    i = 0
    while i < len(lines):
        match = CUE_LINE.match(lines[i])
        if not match:
            i += 1
            continue
        start = _seconds(match.group(1))
        i += 1
        block: list[str] = []
        # A block ends at a truly empty line. Do not use .strip() here: YouTube's rolling
        # auto-captions sometimes render a cue's "previous line" as a single space " " when there
        # was nothing before it, and that is real (if blank) block content, not the separator.
        while i < len(lines) and lines[i] != "":
            block.append(lines[i])
            i += 1
        block_lines = [TAG.sub("", line).strip() for line in block]
        block_lines = [line for line in block_lines if line]
        if not block_lines:
            continue
        overlap = 0
        for k in range(min(len(block_lines), len(previous_lines)), 0, -1):
            if block_lines[:k] == previous_lines[-k:]:
                overlap = k
                break
        new_lines = block_lines[overlap:]
        if new_lines:
            text = " ".join(new_lines)
            if not CREDITS.match(text) and (not cues or text != cues[-1].text):
                cues.append(Cue(start, text))
            previous_lines = block_lines
    return cues


def to_text(cues: list[Cue]) -> str:
    """Join cues into plain paragraphs (a blank line every ~12 cues, roughly a paragraph)."""
    if not cues:
        return ""
    parts, para = [], []
    for index, cue in enumerate(cues):
        para.append(cue.text)
        if (index + 1) % 12 == 0:
            parts.append(" ".join(para))
            para = []
    if para:
        parts.append(" ".join(para))
    return "\n\n".join(parts)


def to_timestamped(cues: list[Cue]) -> str:
    """One line per cue, with an [MM:SS] marker, for a version an agent can cite precisely."""
    lines = []
    for cue in cues:
        minutes, seconds = divmod(int(cue.start), 60)
        hours, minutes = divmod(minutes, 60)
        stamp = f"{hours:02d}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes:02d}:{seconds:02d}"
        lines.append(f"[{stamp}] {cue.text}")
    return "\n".join(lines)
