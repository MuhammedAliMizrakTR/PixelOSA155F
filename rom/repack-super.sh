#!/usr/bin/env bash
# Rebuilds super: decompress/unsparse stock super, dump layout (JSON + text),
# unpack logical partitions, then lpmake a new sparse super with the GSI as
# system. Requires rom/tools.sh to have provisioned ./tools (or system lptools).
set -euo pipefail
cd "$(dirname "$0")/.."
R=$(pwd)
for d in tools/lptools/linux_glibc_x86_64 tools/lz4; do [ -d "$d" ] && export PATH="$R/$d:$PATH"; done

SUPER_MEMBER=$(cat work/ap/super_member.txt)
echo "stock super member: $SUPER_MEMBER"

if [ "$SUPER_MEMBER" = "super.img.lz4" ]; then
  lz4 -d -f work/ap/super.img.lz4 work/ap/super.img 2>/dev/null \
    || lz4 -l -d -f work/ap/super.img.lz4 work/ap/super.img
  rm -f work/ap/super.img.lz4
fi

# sparse? -> unsparse with the pure-python converter (no libc++ dependency)
if python3 -c "import sys; sys.exit(0 if open('work/ap/super.img','rb').read(4)==b'\x3a\xff\x26\xed' else 1)"; then
  echo "stock super is Android-sparse -> rom/simg2img.py"
  python3 rom/simg2img.py work/ap/super.img work/ap/super.raw
  rm -f work/ap/super.img
else
  mv work/ap/super.img work/ap/super.raw
fi
df -h . | tail -1

LPDUMP=$(command -v lpdump || command -v lpdumps)
"$LPDUMP" -j work/ap/super.raw > work/ap/super.json 2>/dev/null || true
"$LPDUMP" work/ap/super.raw > work/ap/super.txt
head -40 work/ap/super.txt

mkdir -p work/parts
lpunpack work/ap/super.raw work/parts/
ls -la work/parts/
rm -f work/ap/super.raw          # free the biggest blob
df -h . | tail -1

python3 rom/lp_plan.py work/ap/super.json work/ap/super.txt work/parts work/gsi/gsi.img work/lpmake_cmd.sh work/super_new.img
bash work/lpmake_cmd.sh
ls -la work/super_new.img

rm -rf work/parts work/gsi/gsi.img
df -h . | tail -1
echo "=== super rebuilt ==="
