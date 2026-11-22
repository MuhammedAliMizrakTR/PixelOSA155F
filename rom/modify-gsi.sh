#!/usr/bin/env bash
# Embeds /system/etc/a155f-extras/ into the GSI (RIL-fix module zip and README;
# manager APKs are separate release assets to avoid mismatched versions). No loop mounts needed: ext4 images are edited
# with debugfs (built by rom/tools.sh); erofs images need fsck.erofs/mkfs.erofs
# (CI runner apt: erofs-utils).
set -euo pipefail
cd "$(dirname "$0")/.."
R=$(pwd)
for d in tools/e2fsprogs/b/debugfs tools/e2fsprogs/b/e2fsck tools/e2fsprogs/b/resize tools/e2fsprogs/b/misc; do
  [ -d "$d" ] && export PATH="$R/$d:$PATH"
done
IMG=work/gsi/gsi.img

cat > /tmp/a155f-extras-readme.txt <<'EOF'
A155F EXTRAS (embedded by the ROM build)
========================================
RILFix_A15.zip      - KernelSU-Next / BakaSU / Magisk module. Fixes the
                      unlocked-bootloader SIM/network drop (~7h25m ril-daemon
                      hang) with a 6-hourly ril-daemon restart, AND applies
                      the researched A155F Treble presets (fingerprint,
                      brightness, sensors, camera, MTK GPU, jack).
                      Install from your root manager: Modules -> Install
                      from storage -> this file. Also attached to the release.
Manager APK         - download the exact version from the matching release asset;
                      manager APKs are not embedded in the system image.
Vanilla builds: no root, so no module — SIM bug NOT fixed there.
EOF

FS=$(blkid -o value -s TYPE "$IMG" 2>/dev/null || echo unknown)
echo "GSI filesystem: $FS"
case "$FS" in
  ext4)
    SZ=$(stat -c%s "$IMG"); truncate -s $((SZ + 67108864)) "$IMG"
    e2fsck -fy "$IMG" || true
    resize2fs "$IMG"
    # locate build.prop: image root (SAR) vs nested /system
    ROOT=""
    debugfs -R "stat /build.prop" "$IMG" >/dev/null 2>&1 && ROOT="" || ROOT="/system"
    debugfs -w -R "mkdir /$ROOT/etc/a155f-extras" "$IMG" 2>/dev/null || true
    debugfs -w -R "write out/dist/RILFix_A15.zip /$ROOT/etc/a155f-extras/RILFix_A15.zip" "$IMG"
    for f in work/manager/*.apk; do
      [ -f "$f" ] && debugfs -w -R "write $f /$ROOT/etc/a155f-extras/$(basename "$f")" "$IMG"
    done
    debugfs -w -R "write /tmp/a155f-extras-readme.txt /$ROOT/etc/a155f-extras/README.txt" "$IMG"
    debugfs -R "ls -l /$ROOT/etc/a155f-extras" "$IMG"
    e2fsck -fy "$IMG" || true
    resize2fs -M "$IMG"
    ;;
  erofs)
    mkdir -p /tmp/gsi.x
    fsck.erofs --extract=/tmp/gsi.x "$IMG"
    rm -f "$IMG"
    B=/tmp/gsi.x; [ -d "$B/etc" ] || B="$B/system"
    mkdir -p "$B/etc/a155f-extras"
    cp out/dist/RILFix_A15.zip "$B/etc/a155f-extras/"
    for f in work/manager/*.apk; do [ -f "$f" ] && cp "$f" "$B/etc/a155f-extras/"; done
    cp /tmp/a155f-extras-readme.txt "$B/etc/a155f-extras/README.txt"
    chmod -R a=rX "$B/etc/a155f-extras"
    mkfs.erofs -zlz4hc "$IMG" /tmp/gsi.x
    rm -rf /tmp/gsi.x
    ;;
  *) echo "FATAL: unsupported GSI fs '$FS'"; exit 1;;
esac
echo "gsi.img final: $(stat -c%s "$IMG") bytes"
df -h . | tail -1
