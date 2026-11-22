#!/usr/bin/env bash
# Extracts the AP tar from the firmware zip, lists its members (member names
# and ORDER are the Odin/PIT contract we must reproduce), extracts every member
# except super (handled by repack-super.sh) into work/ap/small/.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p work/ap/small

if ls work/ap/AP_*.tar* >/dev/null 2>&1; then
  # LOCAL mode: AP tar already staged by fetch-inputs.sh
  AP=$(ls work/ap/AP_*.tar* 2>/dev/null | head -1 || true)
else
  ZIP=$(ls work/fw/*.zip 2>/dev/null | head -1 || true)
  [ -n "$ZIP" ] || { echo "FATAL: no firmware zip in work/fw/"; exit 1; }
  head -c2 "$ZIP" | grep -q '^PK' || { echo "FATAL: $ZIP is not a ZIP file (magic: $(od -An -tx1 -N4 "$ZIP" | tr -d ' \n')) — Frija 'decrypt' adımı atlanmış olabilir"; exit 1; }
  echo "firmware zip: $(basename "$ZIP") ($(stat -c%s "$ZIP") bytes), magic OK"
  # capture the listing first: unzip|grep -m1 dies by SIGPIPE under pipefail
  unzip -Z1 "$ZIP" > work/fw/ziplist.txt
  APMEMBER=$(grep -m1 '^AP_.*\.tar\.md5$' work/fw/ziplist.txt || true)
  [ -n "$APMEMBER" ] || { echo "FATAL: no AP_*.tar.md5 member in $ZIP"; head -20 work/fw/ziplist.txt; exit 1; }
  echo "AP member: $APMEMBER"
  unzip -o "$ZIP" "$APMEMBER" -d work/ap/
  rm -f "$ZIP"   # free several GB early
  AP="work/ap/$APMEMBER"
fi
df -h . | tail -1
# NOTE: Samsung .tar.md5 has the md5 line appended AFTER the tar end-of-archive.
# GNU tar parses trailer garbage as a phantom duplicate of the last member
# (both in listing AND in -T name matching -> "Not found in archive").
# So: list (rc tolerated), dedupe, then extract EVERYTHING in one plain pass.
{ tar -tf "$AP" 2>/dev/null || true; } | awk 'NF && !seen[$0]++' > work/ap/members.txt
echo "--- stock AP members (order is significant) ---"
cat work/ap/members.txt

if grep -qE '^super\.img\.lz4$' work/ap/members.txt; then
  SUPER_MEMBER="super.img.lz4"
elif grep -qE '^super\.img$' work/ap/members.txt; then
  SUPER_MEMBER="super.img"
else
  echo "FATAL: no super.img[.lz4] member in AP tar"; exit 1
fi
echo "$SUPER_MEMBER" > work/ap/super_member.txt

mkdir -p work/ap/all
tar -xf "$AP" -C work/ap/all 2>work/ap/tar-warn.txt || { echo "tar warnings:"; cat work/ap/tar-warn.txt; }
# verify every listed member made it to disk (guards against real corruption)
MISS=""
while IFS= read -r m; do [ -e "work/ap/all/$m" ] || MISS="$MISS $m"; done < work/ap/members.txt
[ -z "$MISS" ] || { echo "FATAL: AP members missing after extraction:$MISS"; exit 1; }

# split: super aside (repack-super.sh), everything else -> small/
mv "work/ap/all/$SUPER_MEMBER" "work/ap/$SUPER_MEMBER"
( cd work/ap/all && tar -cf - . ) | ( mkdir -p work/ap/small && tar -xf - -C work/ap/small )
rm -rf work/ap/all "$AP"   # free; small members + super are extracted
ls -la work/ap/small/
df -h . | tail -1
echo "=== AP extracted ==="
