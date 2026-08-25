#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Install the K70 brand faces.
#
# The pipeline renders correctly WITHOUT this — config/brand/k70.yaml lists font
# families best-first and the resolver falls back to the bundled Ubuntu/DejaVu
# faces. Running this just upgrades the typography from "generic system font" to
# the intended finance-documentary look.
#
# All three families are SIL Open Font License — free for commercial use,
# including monetised YouTube content. Installed per-user (no sudo).
#
#   ./scripts/fetch_brand_fonts.sh
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

DEST="${HOME}/.local/share/fonts/k70"
mkdir -p "$DEST"
cd "$(mktemp -d)"

# family|github repo path to the STATIC bold/black face we actually want
FONTS=(
  "Archivo Black|https://github.com/google/fonts/raw/main/ofl/archivoblack/ArchivoBlack-Regular.ttf"
  "Anton|https://github.com/google/fonts/raw/main/ofl/anton/Anton-Regular.ttf"
  "Oswald|https://github.com/google/fonts/raw/main/ofl/oswald/static/Oswald-Bold.ttf"
  "Barlow Condensed|https://github.com/google/fonts/raw/main/ofl/barlowcondensed/BarlowCondensed-Bold.ttf"
  "Inter|https://github.com/google/fonts/raw/main/ofl/inter/static/Inter-Bold.ttf"
  "Inter|https://github.com/google/fonts/raw/main/ofl/inter/static/Inter-Regular.ttf"
  "JetBrains Mono|https://github.com/google/fonts/raw/main/ofl/jetbrainsmono/static/JetBrainsMono-Bold.ttf"
  "IBM Plex Mono|https://github.com/google/fonts/raw/main/ofl/ibmplexmono/IBMPlexMono-Bold.ttf"
)

ok=0; fail=0
for entry in "${FONTS[@]}"; do
  family="${entry%%|*}"
  url="${entry#*|}"
  name="$(basename "$url")"
  if curl -fsSL --retry 2 -o "$DEST/$name" "$url"; then
    echo "  ✓ ${family}: ${name}"
    ok=$((ok+1))
  else
    rm -f "$DEST/$name"
    echo "  ✗ ${family}: ${name} (skipped — the fallback face will be used)"
    fail=$((fail+1))
  fi
done

if command -v fc-cache >/dev/null 2>&1; then
  fc-cache -f "$DEST" >/dev/null 2>&1 || true
fi

echo
echo "Installed ${ok} face(s) to ${DEST} (${fail} unavailable)."
echo "Verify what the brand resolved to:"
echo "  PYTHONPATH=apps/api .venv/bin/python -c \\"
echo "    'from app.brand import load_theme; t=load_theme(); print(t.display.path, t.mono.path)'"
