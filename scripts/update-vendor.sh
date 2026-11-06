#!/usr/bin/env bash
set -euo pipefail

VENDOR_DIR="calibra/web/static/vendor"

TAILWIND_VERSION="4.3.4"
PLOTLY_VERSION="4.2.0"
HTMX_VERSION="2.0.11"
LUCIDE_VERSION="1.69.0"

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
  "57bc1111c147eff83e031aae6b83aa47be5437f0c9ce348688935953753e7e12"

download "plotly-${PLOTLY_VERSION}.min.js" \
  "https://cdn.plot.ly/plotly-${PLOTLY_VERSION}.min.js" \
  "fde93964a7511bfa54c5745c49b5d0e41715cbde0cc5ebeae3f9a02de0396cae"

download "htmx-${HTMX_VERSION}.min.js" \
  "https://unpkg.com/htmx.org@${HTMX_VERSION}/dist/htmx.min.js" \
  "d6fdc75f204e6bdefa99b69bf1e6d4ac69b8a364f77929f45c13476b4000f717"

download "lucide-${LUCIDE_VERSION}.min.js" \
  "https://unpkg.com/lucide@${LUCIDE_VERSION}/dist/umd/lucide.min.js" \
  "3194a24d2cdaff8097a4c6d81f0c648c66a40759564ac3de5e12ad1255a6bd5f"

echo "All downloads verified. Files in $VENDOR_DIR:"
ls -lh "$VENDOR_DIR"
