#!/usr/bin/env bash
set -euo pipefail

VENDOR_DIR="calibra/web/static/vendor"

TAILWIND_VERSION="4.3.3"
PLOTLY_VERSION="4.1.0"
HTMX_VERSION="2.0.10"
LUCIDE_VERSION="1.45.0"

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
  "03e18091beef5647aaf9e15f526981f325d760bb6b784fe0672a1e20585272cf"

download "htmx-${HTMX_VERSION}.min.js" \
  "https://unpkg.com/htmx.org@${HTMX_VERSION}/dist/htmx.min.js" \
  "71ea67185bfa8c98c39d31717c6fce5d852370fcdfd129db4543774d3145c0de"

download "lucide-${LUCIDE_VERSION}.min.js" \
  "https://unpkg.com/lucide@${LUCIDE_VERSION}/dist/umd/lucide.min.js" \
  "1876a30f8dd16a23af5ee36d503460202b35af298973e28e194014b79c51fb13"

echo "All downloads verified. Files in $VENDOR_DIR:"
ls -lh "$VENDOR_DIR"
