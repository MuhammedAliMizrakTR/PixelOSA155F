#!/usr/bin/env bash
# ============================================================================
# Build the ONE-FILE Colab deliverable  (PixelOSA155F-colab.sh)
#
#   bash tools/make_single_file.sh [output path]
#
# The single file is literally  colab_build.sh  +  marker line  +  base64(zip):
#   * header   = colab_build.sh  (unchanged, so both modes stay byte-identical
#                in behaviour: payload mode and in-repo mode)
#   * payload  = deterministic zip of the sources the build needs
#                (rom/ tools/*.py docs/ tests/ inputs/ + a few root files)
#                WITHOUT .git, toolchains (tools/lptools, tools/avb, tools/lz4,
#                tools/e2fsprogs), work/, out/, __pycache__ and this artifact.
#
# Run the self-test after a rebuild:
#   rm -rf /tmp/e2e && INPUTS_DIR=<fake> WORKDIR=/tmp/e2e bash PixelOSA155F-colab.sh
# ============================================================================
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")/.."
OUT="${1:-PixelOSA155F-colab.sh}"
MARKER="#__B64_PAYLOAD_BELOW__"

[ -f colab_build.sh ] || { echo "colab_build.sh yok — repo kökü değil: $(pwd)" >&2; exit 1; }
# The header must never contain a bare marker line, or payload detection breaks.
if grep -qx -- "$MARKER" colab_build.sh; then
  echo "HATA: colab_build.sh içinde çıplak '$MARKER' satırı var" >&2; exit 1
fi

tmpzip=$(mktemp /tmp/nothingos-src.XXXXXX.zip)
trap 'rm -f "$tmpzip"' EXIT

python3 - "$tmpzip" <<'PY'
import os, sys, zipfile

out = sys.argv[1]
EXCLUDE_DIRS = {
    ".git", ".arena", "work", "out", "dist", "build", "__pycache__", ".cache",
    "rom/work",
    "tools/lptools", "tools/avb", "tools/lz4", "tools/e2fsprogs",
    "tools/__pycache__",
}
EXCLUDE_NAMES = {"PixelOSA155F-colab.sh", "PixelOSA155F-src.zip"}
ROOT_DIRS = ["rom", "tools", "docs", "tests", "inputs"]
ROOT_FILES = ["README.md", "CHANGELOG.md", ".gitignore", "colab_build.sh"]

def excluded(rel):
    parts = rel.split("/")
    if parts[0] in EXCLUDE_DIRS or rel in EXCLUDE_DIRS:
        return True
    if rel.rsplit("/", 1)[-1] in EXCLUDE_NAMES:
        return True
    if rel.endswith((".pyc", ".pyo")):
        return True
    return False

paths = []
for d in ROOT_DIRS:
    for dirpath, dirnames, filenames in os.walk(d):
        dirnames[:] = sorted(n for n in dirnames if not excluded(os.path.join(dirpath, n)))
        for f in sorted(filenames):
            rel = os.path.join(dirpath, f)
            if not excluded(rel):
                paths.append(rel)
paths += [f for f in ROOT_FILES if os.path.isfile(f) and not excluded(f)]
paths = sorted(set(paths))

with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
    for rel in paths:
        info = zipfile.ZipInfo(rel, date_time=(2026, 1, 1, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o644 << 16
        with open(rel, "rb") as fh:
            zf.writestr(info, fh.read())
print("payload: %d files" % len(paths))
PY

tmpout=$(mktemp "${OUT}.XXXXXX")
{
  cat colab_build.sh
  printf '\n%s\n' "$MARKER"
  base64 -w 76 "$tmpzip"
} > "$tmpout"
chmod 755 "$tmpout"
mv -f "$tmpout" "$OUT"

echo "yazıldı: $OUT ($(stat -c%s "$OUT") bayt, $(sha256sum "$OUT" | cut -d' ' -f1))"
