#!/usr/bin/env bash
# One-shot build: PixelOS GSI -> plain Odin AP TAR, in exactly the shape the
# owner's GrapheneOS/RestlessOS port already proved on SM-A155F.
#
#   INPUTS_DIR=/content/drive/MyDrive/PixelOSA155F bash rom/gsi-build.sh
#
# Stages: GSI (MD5-gated) + kernel boot.img + stock firmware, then
# extract-ap -> [optional extras] -> repack-super -> make-vbmeta -> pack-ap,
# and finishes with tools/odin_audit.py as a hard gate.
set -euo pipefail
cd "$(dirname "$0")/.."

export KERNEL_VARIANT="${KERNEL_VARIANT:-bakasu}"
export FW_VERSION="${FW_VERSION:-A155FXXS7CYG4}"
export ROM_NAME="${ROM_NAME:-PixelOS}"
SKIP_GSI_EXTRAS="${SKIP_GSI_EXTRAS:-1}"
# 1 = leave the stock userdata.img out of the AP (keep the phone's data)
EXCLUDE_USERDATA="${EXCLUDE_USERDATA:-0}"
export EXCLUDE_USERDATA

say() { printf '\n########## %s\n' "$*"; }
t0=$(date +%s)

say "1/8 toolchain (lptools, lz4, e2fsprogs, avbtool)"
bash rom/tools.sh
R=$(pwd)
# The owner's repack-super.sh bootstraps its own PATH; pack-ap.sh (and the other
# stages) did not, so `lz4` was "command not found" at 7/8 even though tools.sh had
# just built it — `bash rom/tools.sh` runs in a subshell, its export never reaches
# this script.
for d in tools/lptools/linux_glibc_x86_64 tools/lz4 tools/e2fsprogs/b/misc \
         tools/e2fsprogs/b/debugfs tools/e2fsprogs/b/e2fsck tools/e2fsprogs/b/resize; do
  [ -d "$R/$d" ] && export PATH="$R/$d:$PATH"
done
export PATH
for b in lpmake lpdumps lz4 debugfs; do
  command -v "$b" >/dev/null || { echo "FATAL: $b still not on PATH after rom/tools.sh"; exit 1; }
done

say "2/8 stage inputs (GSI, kernel, firmware)"
bash rom/gsi-inputs.sh

say "3/8 extract stock AP (member order = Odin contract)"
bash rom/extract-ap.sh

if [ "$SKIP_GSI_EXTRAS" = "0" ]; then
  say "4/8 embed a155f extras into the GSI (RILFix module + presets)"
  bash rom/build-rilfix-module.sh
  bash rom/modify-gsi.sh
else
  say "4/8 GSI extras skipped (SKIP_GSI_EXTRAS=1); GSI used as-is"
fi

say "5/8 rebuild super: GSI system + stock vendor/product/odm"
bash rom/repack-super.sh

say "6/8 verification-disabled vbmeta images"
bash rom/make-vbmeta.sh

say "7/8 pack plain AP TAR (+ SHA-256 manifest, transport parts)"
bash rom/pack-ap.sh

say "8/8 audit the produced AP TAR"
AP=$(ls -t out/AP_*.tar 2>/dev/null | head -1 || true)
[ -n "$AP" ] || { echo "FATAL: pack-ap.sh produced no out/AP_*.tar"; exit 1; }
set +e
python3 tools/odin_audit.py "$AP" | tee "out/$(basename "$AP" .tar).audit.txt"
AUDIT_RC=${PIPESTATUS[0]}
set -e

printf '\n########## done in %ss\n' "$(( $(date +%s) - t0 ))"
echo "AP TAR   : $AP ($(stat -c%s "$AP") bytes)"
echo "sha256   : $(sha256sum "$AP" | cut -d' ' -f1)"
echo "manifest : out/dist/*.SHA256SUMS.txt"
echo "audit    : out/$(basename "$AP" .tar).audit.txt (rc=$AUDIT_RC)"
if [ "$AUDIT_RC" -ge 2 ]; then
  echo
  echo "AUDIT CRITICAL: do NOT flash this artifact. Read the findings above."
  exit 2
fi
echo
echo "Artifact is built, unflashed and unvalidated. Flashing needs owner approval,"
echo "a reconciled SW REV / fused revision, and the stock package on hand."
