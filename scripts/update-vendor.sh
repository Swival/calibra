#!/usr/bin/env bash
set -euo pipefail

VENDOR_DIR="calibra/web/static/vendor"

TAILWIND_VERSION="4.3.3"
PLOTLY_VERSION="4.1.2"
HTMX_VERSION="2.0.11"
LUCIDE_VERSION="1.61.0"

download() {
  local file="$1" url="$2" expected="$3"
  echo "  Downloading $file..."
  if ! curl -sfL --fail -o "$VENDOR_DIR/$file" "$url"; then
    echo "ERROR: Failed to download $url" >&2
    exit 1
  fi
  local actual
  actual=$(shasum -a 256 "$VENDOR_DIR/$file" | awk '{print $1}')
  if [ "$actual" != "$expected" ]; then
    echo "ERROR: Checksum mismatch for $file" >&2
    echo "  Expected: $expected" >&2
    echo "  Got:      $actual" >&2
    rm -f "$VENDOR_DIR/$file"
    exit 1
  fi
}

echo "Downloading vendored frontend dependencies..."

download "tailwindcss-browser-${TAILWIND_VERSION}.js" \
  "https://cdn.jsdelivr.net/npm/@tailwindcss/browser@${TAILWIND_VERSION}" \
  "6d8c473ef2f8ad63feafc0bd76502dda31501a6c135dc4c6173f6268cde595be"

download "plotly-${PLOTLY_VERSION}.min.js" \
  "https://cdn.plot.ly/plotly-${PLOTLY_VERSION}.min.js" \
  "2f645d1bade8182fce161b7f10f89402f8b315805250ff4a94672a28d23c390a"

download "htmx-${HTMX_VERSION}.min.js" \
  "https://unpkg.com/htmx.org@${HTMX_VERSION}/dist/htmx.min.js" \
  "d6fdc75f204e6bdefa99b69bf1e6d4ac69b8a364f77929f45c13476b4000f717"

download "lucide-${LUCIDE_VERSION}.min.js" \
  "https://unpkg.com/lucide@${LUCIDE_VERSION}/dist/umd/lucide.min.js" \
  "8a83cb0b04601cf942dd30f6254d86aee388d43130acfc24278404fd83c92150"

echo "All downloads verified. Files in $VENDOR_DIR:"
ls -lh "$VENDOR_DIR"
