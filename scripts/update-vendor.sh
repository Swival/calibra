#!/usr/bin/env bash
set -euo pipefail

VENDOR_DIR="calibra/web/static/vendor"

TAILWIND_VERSION="4.3.3"
PLOTLY_VERSION="4.0.0"
HTMX_VERSION="2.0.10"
LUCIDE_VERSION="1.34.0"

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
  "14461f3b4c91c8bb590a99d6d03c3fd031ca40eec07ebab79a5e3eac107cd7ca"

download "htmx-${HTMX_VERSION}.min.js" \
  "https://unpkg.com/htmx.org@${HTMX_VERSION}/dist/htmx.min.js" \
  "71ea67185bfa8c98c39d31717c6fce5d852370fcdfd129db4543774d3145c0de"

download "lucide-${LUCIDE_VERSION}.min.js" \
  "https://unpkg.com/lucide@${LUCIDE_VERSION}/dist/umd/lucide.min.js" \
  "381de5c07d1fa81c3430b04d66a3d710b622c1d702fadd0a0448470d9493b6f1"

echo "All downloads verified. Files in $VENDOR_DIR:"
ls -lh "$VENDOR_DIR"
