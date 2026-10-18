#!/usr/bin/env bash
# One-shot setup for a fresh clone of ai-youtube-summary.
#
# Checks the external dependencies (yt-dlp, ffmpeg), installs the
# `ai-youtube-summary` command itself, sets up the separate venv the local
# Whisper fallback needs, and — if you have a GPU and Ollama installed —
# helps you pull a summarization model. Safe to re-run; every step is
# idempotent and nothing here touches system package managers for you.
set -euo pipefail
cd "$(dirname "$0")"

bold() { printf '\033[1m%s\033[0m\n' "$1"; }
ok()   { printf '  [ok] %s\n' "$1"; }
warn() { printf '  [!!] %s\n' "$1"; }

bold "1. Checking yt-dlp and ffmpeg (required, on PATH)"
missing=0
for bin in yt-dlp ffmpeg; do
  if command -v "$bin" >/dev/null 2>&1; then
    ok "$bin found: $(command -v "$bin")"
  else
    warn "$bin not found on PATH."
    missing=1
  fi
done
if [ "$missing" = 1 ]; then
  cat <<'EOF'

  Install them first, then re-run this script:
    macOS:          brew install yt-dlp ffmpeg
    Debian/Ubuntu:  sudo apt install ffmpeg && sudo pip install -U yt-dlp
    Windows:        winget install yt-dlp.yt-dlp ; winget install Gyan.FFmpeg
EOF
  exit 1
fi

bold "2. Installing the ai-youtube-summary command"
PY=python3
if ! command -v "$PY" >/dev/null 2>&1; then
  warn "python3 not found on PATH."
  exit 1
fi
# The CLI itself has zero pip dependencies (pure stdlib), so rather than fight
# PEP 668's "externally-managed-environment" pip refusal (or require pipx),
# this just writes a tiny launcher that puts src/ on PYTHONPATH — no install
# step needed at all.
REPO_DIR="$(pwd)"
LAUNCHER_DIR="$HOME/.local/bin"
mkdir -p "$LAUNCHER_DIR"
cat > "$LAUNCHER_DIR/ai-youtube-summary" <<EOF
#!/usr/bin/env bash
export PYTHONPATH="$REPO_DIR/src\${PYTHONPATH:+:\$PYTHONPATH}"
exec python3 -m ai_youtube_summary "\$@"
EOF
chmod +x "$LAUNCHER_DIR/ai-youtube-summary"
ok "wrote $LAUNCHER_DIR/ai-youtube-summary"
case ":$PATH:" in
  *":$LAUNCHER_DIR:"*) ok "$LAUNCHER_DIR is already on PATH" ;;
  *) warn "$LAUNCHER_DIR is not on your PATH — add this to your shell profile:"
     echo "       export PATH=\"$LAUNCHER_DIR:\$PATH\"" ;;
esac

bold "3. Setting up the local Whisper fallback venv (for videos with no captions)"
WHISPER_VENV="${WHISPER_VENV:-$HOME/.venvs/ai-youtube-summary}"
if [ -x "$WHISPER_VENV/bin/python3" ]; then
  ok "venv already exists at $WHISPER_VENV"
else
  "$PY" -m venv "$WHISPER_VENV"
  ok "created venv at $WHISPER_VENV"
fi
# av 19+ breaks faster-whisper 1.2.1's call into PyAV (TypeError: metadata_errors); pin 18.0.0.
"$WHISPER_VENV/bin/pip" install --quiet faster-whisper av==18.0.0
ok "faster-whisper + av==18.0.0 installed"

bold "4. Local-model summarization (needs a GPU to be usable — see EXTENSION.md)"
if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi >/dev/null 2>&1; then
  ok "NVIDIA GPU detected"
else
  warn "No NVIDIA GPU detected (nvidia-smi missing or failed) — summarization will be slow/impractical on CPU."
  warn "You can still use 'fetch'/'info'/download commands; just skip the extension's Summary tab."
fi
if command -v ollama >/dev/null 2>&1; then
  ok "ollama found: $(command -v ollama)"
  MODEL="${OLLAMA_MODEL:-qwen3.6:35b-a3b}"
  if ollama list 2>/dev/null | awk '{print $1}' | grep -qx "$MODEL"; then
    ok "model '$MODEL' already pulled"
  else
    warn "model '$MODEL' not pulled yet. Pick one that fits your GPU's VRAM, then:"
    echo "       ollama pull $MODEL"
    echo "       export OLLAMA_MODEL=$MODEL   # before starting server/api.py, if not the default above"
  fi
else
  warn "ollama not found — install it from https://ollama.com if you want the extension's local-model summary tab."
fi

cat <<'EOF'

Done. Next steps:
  ai-youtube-summary fetch <youtube-url>      # transcript, for you to summarise
  ai-youtube-summary song  <youtube-url>      # download audio

Browser extension (transcript + summary + manual download in a side panel):
  1. python3 -m server.api                    # starts the local bridge on :9877
  2. Load extension/ as an unpacked extension in edge://extensions or chrome://extensions
  See EXTENSION.md for details.
EOF
