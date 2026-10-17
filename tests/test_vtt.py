import unittest

from tests import helpers  # noqa: F401
from ai_youtube_summary import vtt

# Real YouTube auto-caption output (rolling: each cue repeats the settled line, adds a new one
# word-by-word with <c> tags, plus near-zero-duration "freeze" cues that just repeat the last line).
# The blank "previous line" before the very first word is a real single space (" "), which is how
# the file tells "blank content" apart from the block separator (a genuinely empty line) — built
# with an explicit space marker here rather than literal trailing whitespace in this source file,
# which editors and formatters routinely strip on save.
SP = " "  # a single space: a real (if blank) VTT content line, not a blank separator line
AUTO_ROLLING = "\n".join([
    "WEBVTT", "Kind: captions", "Language: en", "",
    "00:00:19.560 --> 00:00:21.950 align:start position:0%",
    SP, "Hear<00:00:19.720><c> that?</c>", "",
    "00:00:21.950 --> 00:00:21.960 align:start position:0%",
    "Hear that?", SP, "",
    "00:00:21.960 --> 00:00:24.830 align:start position:0%",
    "Hear that?", "That's<00:00:22.960><c> nothing.</c>", "",
    "00:00:24.830 --> 00:00:24.840 align:start position:0%",
    "That's nothing.", SP, "",
    "00:00:24.840 --> 00:00:27.310 align:start position:0%",
    "That's nothing.", "Which<00:00:25.040><c> is</c><00:00:25.240><c> what</c> I, as a speaker", "",
])

# Real manual (TED/Amara-style) captions: a credits cue that was never spoken, and utterances
# wrapped over two lines with no repetition between cues.
MANUAL_WRAPPED = """WEBVTT
Kind: captions
Language: en

00:00:00.000 --> 00:00:07.000
Translator: Gustavo Rocha
Reviewer: Ariana Bleau Lugo

00:00:19.514 --> 00:00:21.226
Hear that?

00:00:21.762 --> 00:00:24.027
That's nothing.

00:00:24.736 --> 00:00:28.381
Which is what I, as a speaker
at today's conference,

00:00:28.381 --> 00:00:29.816
have for you all.
"""


class ParseAutoRollingTests(unittest.TestCase):
    def test_repeated_lines_are_dropped_not_doubled(self):
        cues = vtt.parse(AUTO_ROLLING)
        texts = [c.text for c in cues]
        self.assertEqual(texts, ["Hear that?", "That's nothing.", "Which is what I, as a speaker"])

    def test_freeze_cues_produce_nothing(self):
        cues = vtt.parse(AUTO_ROLLING)
        # 5 real cue blocks in the fixture, only 3 carry new content; the other 2 are pure repeats.
        self.assertEqual(len(cues), 3)

    def test_tags_are_stripped(self):
        cues = vtt.parse(AUTO_ROLLING)
        self.assertNotIn("<", "".join(c.text for c in cues))

    def test_start_times_are_seconds(self):
        cues = vtt.parse(AUTO_ROLLING)
        self.assertAlmostEqual(cues[0].start, 19.56, places=2)
        self.assertAlmostEqual(cues[1].start, 21.96, places=2)


class ParseManualWrappedTests(unittest.TestCase):
    def test_credits_cue_is_dropped(self):
        cues = vtt.parse(MANUAL_WRAPPED)
        joined = " ".join(c.text for c in cues)
        self.assertNotIn("Translator", joined)
        self.assertNotIn("Reviewer", joined)

    def test_wrapped_lines_are_joined_not_truncated(self):
        cues = vtt.parse(MANUAL_WRAPPED)
        texts = [c.text for c in cues]
        self.assertIn("Which is what I, as a speaker at today's conference,", texts)

    def test_no_repetition_between_unrelated_cues(self):
        cues = vtt.parse(MANUAL_WRAPPED)
        texts = [c.text for c in cues]
        self.assertEqual(texts, ["Hear that?", "That's nothing.",
                                 "Which is what I, as a speaker at today's conference,", "have for you all."])


class OutputFormattingTests(unittest.TestCase):
    def test_to_text_reads_as_one_continuous_passage(self):
        cues = vtt.parse(MANUAL_WRAPPED)
        text = vtt.to_text(cues)
        self.assertIn("Hear that? That's nothing.", text)

    def test_to_timestamped_has_a_marker_per_cue(self):
        cues = vtt.parse(MANUAL_WRAPPED)
        out = vtt.to_timestamped(cues)
        self.assertEqual(out.count("["), len(cues))
        self.assertIn("[00:19]", out)

    def test_empty_input_is_handled(self):
        self.assertEqual(vtt.parse("WEBVTT\n"), [])
        self.assertEqual(vtt.to_text([]), "")
        self.assertEqual(vtt.to_timestamped([]), "")


if __name__ == "__main__":
    unittest.main()
