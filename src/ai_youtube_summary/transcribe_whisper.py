"""Runs under the ai-youtube-summary venv (faster-whisper installed there, not in the main tool).

usage: python transcribe_whisper.py <audio path> <out json path> [model size]
Writes {"language": "en", "cues": [[start_seconds, text], ...]} to out json path.
"""

import json
import sys

from faster_whisper import WhisperModel


def main() -> None:
    audio_path, out_path = sys.argv[1], sys.argv[2]
    model_size = sys.argv[3] if len(sys.argv) > 3 else "small"
    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    segments, info = model.transcribe(audio_path, vad_filter=True)
    cues = [[round(seg.start, 2), seg.text.strip()] for seg in segments if seg.text.strip()]
    with open(out_path, "w", encoding="utf-8") as handle:
        json.dump({"language": info.language, "cues": cues}, handle, ensure_ascii=False)
    print(f"transcribed {len(cues)} segments, language={info.language}")


if __name__ == "__main__":
    main()
