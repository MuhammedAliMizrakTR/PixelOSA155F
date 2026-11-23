#!/usr/bin/env bash
# Generates verification-disabled vbmeta images (flags=3 = disable verification
# + disable verity) — the standard "vbmeta_disabled" the A15 GSI guides flash.
# One per vbmeta* member present in the stock AP tar.
set -euo pipefail
cd "$(dirname "$0")/.."
R=$(pwd)
# The owner's repack-super.sh bootstraps its own PATH; pack-ap.sh (and the other
# stages) did not, so `lz4` was "command not found" at 7/8 even though tools.sh had
# just built it — `bash rom/tools.sh` runs in a subshell, its export never reaches
# this script.
for d in tools/lptools/linux_glibc_x86_64 tools/lz4 tools/e2fsprogs/b/misc \
         tools/e2fsprogs/b/debugfs tools/e2fsprogs/b/e2fsck tools/e2fsprogs/b/resize; do
  [ -d "$R/$d" ] && export PATH="$R/$d:$PATH"
done
mkdir -p work/vbmeta
grep -E '^vbmeta[^/]*\.img(\.lz4)?$' work/ap/members.txt | while read -r m; do
  base="${m%.lz4}"
  python3 tools/avb/avbtool.py make_vbmeta_image --flags 3 --output "work/vbmeta/$base"
  echo "$m -> disabled ($base, $(stat -c%s "work/vbmeta/$base") bytes)"
done
ls -la work/vbmeta/
[ -f work/vbmeta/vbmeta.img ] || { echo "FATAL: stock AP has no vbmeta.img member?!"; exit 1; }
