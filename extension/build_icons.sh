#!/usr/bin/env bash
# Regenerates icons/icon{16,32,48,128}.png from icon.svg.
# Chrome/Edge extension manifests need raster icons, not SVG, so icon.svg is
# the source of truth and this script is how you turn an edit to it back into
# the PNGs the manifest actually references.
set -euo pipefail
cd "$(dirname "$0")"

TMP_PNG="$(mktemp --suffix=.png)"
trap 'rm -f "$TMP_PNG"' EXIT

google-chrome --headless --disable-gpu --disable-software-rasterizer \
  --default-background-color=00000000 \
  --screenshot="$TMP_PNG" \
  --window-size=512,512 \
  --force-device-scale-factor=1 \
  "file://$(pwd)/icon.svg" >/dev/null 2>&1

mkdir -p icons
python3 -c "
from PIL import Image
img = Image.open('$TMP_PNG').convert('RGBA')
for size in (16, 32, 48, 128):
    img.resize((size, size), Image.LANCZOS).save(f'icons/icon{size}.png')
    print(f'wrote icons/icon{size}.png')
"
