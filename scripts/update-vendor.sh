#!/usr/bin/env bash
set -euo pipefail

VENDOR_DIR="calibra/web/static/vendor"

TAILWIND_VERSION="4.2.1"
PLOTLY_VERSION="3.4.0"
HTMX_VERSION="2.0.8"
LUCIDE_VERSION="0.575.0"

declare -A CHECKSUMS=(
  ["tailwindcss-browser-${TAILWIND_VERSION}.js"]="567a864730c2d83639cfc7c7d0d3d5eefdf6ba9e1611a66cb5e2807dd1febfdc"
  ["plotly-${PLOTLY_VERSION}.min.js"]="28498fa2ea4ba45c8633218088eb223436ca0ca02fc57027fd6fa841ad1901f9"
  ["htmx-${HTMX_VERSION}.min.js"]="22283ef68cb7545914f0a88a1bdedc7256a703d1d580c1d255217d0a50d31313"
  ["lucide-${LUCIDE_VERSION}.min.js"]="f01557cbefed1c14616c0b822383c74bf234c222ccf4698c8b00b49d50030e26"
)

download() {
  local file="$1" url="$2"
  echo "  Downloading $file..."
  curl -sfL --fail -o "$VENDOR_DIR/$file" "$url"
  if [ $? -ne 0 ]; then
    echo "ERROR: Failed to download $url" >&2
    exit 1
  fi
  local actual
  actual=$(shasum -a 256 "$VENDOR_DIR/$file" | awk '{print $1}')
  local expected="${CHECKSUMS[$file]}"
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
  "https://cdn.jsdelivr.net/npm/@tailwindcss/browser@${TAILWIND_VERSION}"

download "plotly-${PLOTLY_VERSION}.min.js" \
  "https://cdn.plot.ly/plotly-${PLOTLY_VERSION}.min.js"

download "htmx-${HTMX_VERSION}.min.js" \
  "https://unpkg.com/htmx.org@${HTMX_VERSION}/dist/htmx.min.js"

download "lucide-${LUCIDE_VERSION}.min.js" \
  "https://unpkg.com/lucide@${LUCIDE_VERSION}/dist/umd/lucide.min.js"

echo "All downloads verified. Files in $VENDOR_DIR:"
ls -lh "$VENDOR_DIR"
