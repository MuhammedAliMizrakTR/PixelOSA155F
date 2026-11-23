#!/usr/bin/env bash
# ============================================================================
# Synthetic input generator — proves the whole chain WITHOUT the real multi-GB
# GSI or firmware. Everything is fake except the *layout*: the stock super comes
# from the real `lpmake`, the GSI zip holds a real Android-sparse `system.img`,
# the kernel TAR holds a 128 MB `boot.img`, and the "firmware" zip contains a
# real plain AP TAR with the stock member order.
#
#   bash tools/mk_synthetic_inputs.sh [target-dir]        # default /tmp/synthinputs
#   INPUTS_DIR=/tmp/synthinputs INPUTS_LOCK=/tmp/synthinputs/inputs.lock.json \
#     bash rom/gsi-build.sh
#
# Names deliberately include a Google Drive copy suffix ("… adlı dosyanın
# kopyası") so the name-resolution path is exercised too. The GSI name is a
# parameter (`GSI_NAME=...`) so the same fixture serves the NothingOS and PixelOS
# lines.
# ============================================================================
set -euo pipefail
T="${1:-/tmp/synthinputs}"
ROOT=$(cd "$(dirname "$0")/.." && pwd)
export PATH="$ROOT/tools/lptools/linux_glibc_x86_64:$PATH"
command -v lpmake >/dev/null || { echo "run 'bash rom/tools.sh' first (needs lpmake)"; exit 1; }

GSI_NAME="${GSI_NAME:-Pixel-Demo-17-1234567-AB-20260111-MysticGSI.zip}"
KTAR_NAME="bakasu_35262_susfs_v2.4.0_A155FXXS7CYG4_A15_GKI.tar adlı dosyanın kopyası"
FWZ_NAME="SAMFW.COM_SM-A155F_XSG_A155FXXS7CYG4_fac.zip adlı dosyanın kopyası adlı dosyanın kopyası"

rm -rf "$T"; mkdir -p "$T"; cd "$T"

# --- stock super: real lpmake, sparse, system/vendor/odm/product -------------
head -c 4194304 /dev/zero > system.bin
head -c 3145728 /dev/zero > vendor.bin
head -c 2097152 /dev/zero > odm.bin
head -c 2097152 /dev/zero > product.bin
lpmake --metadata-size 65536 --metadata-slots 2 --device-size 100663296 --sparse \
  --group main:67108864 \
  --partition system:readonly:4194304:main --image system=system.bin \
  --partition vendor:readonly:3145728:main --image vendor=vendor.bin \
  --partition odm:readonly:2097152:main --image odm=odm.bin \
  --partition product:readonly:2097152:main --image product=product.bin \
  --output super.img >/dev/null
touch vbmeta.img.lz4 vbmeta_system.img.lz4 boot.img.lz4
tar --no-recursion -cf AP_SM-A155F_SYNTH.tar boot.img.lz4 super.img vbmeta.img.lz4 vbmeta_system.img.lz4

# --- GSI zip: real Android-sparse system.img --------------------------------
python3 - "$GSI_NAME" <<'PY'
import struct, sys, zipfile
blocks, bs = 1024, 4096
payload = (b"GSI!!" * (blocks * bs // 5 + 1))[: blocks * bs]
hdr = struct.pack("<IHHHHIIII", 0xED26FF3A, 1, 0, 28, 12, bs, blocks, 1, 0)
chunk = struct.pack("<HHII", 0xCAC1, 0, blocks, 12 + len(payload))
with zipfile.ZipFile(sys.argv[1], "w") as zf:
    zf.writestr("system.img", hdr + chunk + payload)
PY

# --- kernel TAR: 128 MB boot.img --------------------------------------------
head -c 134217728 /dev/urandom > boot.bin
printf 'ANDROID!' | dd of=boot.bin bs=1 seek=0 conv=notrunc status=none
mkdir -p ktar && cp boot.bin ktar/boot.img
tar -cf "$KTAR_NAME" -C ktar boot.img

# --- firmware zip: plain AP TAR, stock member order -------------------------
python3 - "$FWZ_NAME" <<'PY'
import sys, zipfile
with zipfile.ZipFile(sys.argv[1], "w") as zf:
    zf.write("AP_SM-A155F_SYNTH.tar", "AP_SM-A155F_SYNTH.tar.md5")
PY
rm -f AP_SM-A155F_SYNTH.tar

# --- lock file (G0 gate) ----------------------------------------------------
python3 - "$GSI_NAME" "$KTAR_NAME" "$FWZ_NAME" <<'PY'
import hashlib, json, sys

def pin(role, name):
    h = hashlib.md5()
    size = 0
    with open(name, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
            size += len(block)
    return {"role": role, "name": name, "size": size, "md5": h.hexdigest(),
            "use": "synthetic fixture; proves the chain, not bootability"}

gsi, ktar, fwz = sys.argv[1:4]
lock = {"schema": "pixelosa155f.inputs/1", "subject": "synthetic", "inputs": [
    pin("donor-gsi-primary", gsi),
    pin("kernel-boot", ktar),
    pin("stock-firmware", fwz)]}
json.dump(lock, open("inputs.lock.json", "w"), indent=2)
PY
rm -f system.bin vendor.bin odm.bin product.bin boot.bin
echo "synthetic inputs ready in $T"
ls -1
echo
echo "next:  INPUTS_DIR=$T INPUTS_LOCK=$T/inputs.lock.json bash rom/gsi-build.sh"
