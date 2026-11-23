#!/usr/bin/env bash
# Read-only device state collector for SM-A155F (run on the PC, phone booted).
#
#   bash tools/device_state.sh            # writes device_state-<date>.txt
#   bash tools/device_state.sh --stdout   # print instead of writing
#
# Answers the three questions that decide what may be flashed next, from the
# device itself instead of from assumptions:
#   1. what actually booted        (display id / release / fingerprint)
#   2. is the bootloader unlocked  (verifiedbootstate / flash.locked / warranty)
#   3. is adb usable right now     (so a boot that never shows a UI can still
#                                   be diagnosed with logcat)
#
# Nothing is written to the device. No root needed.
set -uo pipefail

ADB=${ADB:-adb}
OUT="device_state-$(date -u +%Y%m%dT%H%M%SZ).txt"
[ "${1:-}" = "--stdout" ] && OUT=/dev/stdout

if ! command -v "$ADB" >/dev/null 2>&1; then
  echo "FATAL: adb yok. Platform-tools kur (veya ADB=/yol/adb ile ver)." >&2
  exit 1
fi

exec > >(tee "$OUT") 2>&1

echo "=== PixelOSA155F device state ==="
echo "date (UTC) : $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "host       : $(uname -srm)"
echo
echo "--- adb devices ---"
"$ADB" devices -l || true
if ! "$ADB" shell true >/dev/null 2>&1; then
  echo
  echo "SONUÇ: cihaz adb'ye görünmüyor."
  echo "  - Telefon açıksa: Ayarlar -> Geliştirici seçenekleri -> USB hata ayıklama AÇIK,"
  echo "    USB modu 'Dosya aktarımı/MTP' olsun, RSA uyarısını kabul et."
  echo "  - Download mode'daysan adb çalışmaz; Odin görür, bu script görmez."
  exit 2
fi

props() { for p in "$@"; do printf '%-42s %s\n' "$p" "$("$ADB" shell getprop "$p" 2>/dev/null | tr -d '\r')"; done; }

echo
echo "--- what booted ---"
props ro.product.device ro.product.model ro.product.name \
      ro.build.display.id ro.build.version.release ro.build.version.sdk \
      ro.build.fingerprint ro.build.description ro.csc.sales_code \
      ro.boot.hardware ro.boot.bootloader ro.boot.baseband

echo
echo "--- bootloader / unlock state (this decides if a custom AP may boot) ---"
props ro.boot.verifiedbootstate ro.boot.flash.locked ro.boot.warranty_bit \
      ro.warranty_bit ro.boot.veritymode ro.boot.vbmeta.device_state \
      ro.boot.slot_suffix ro.boot.bootreason

echo
echo "--- adb / developer settings ---"
props ro.debuggable ro.secure ro.adb.secure service.adb.root \
      persist.sys.usb.config sys.usb.state
"$ADB" shell settings get global adb_enabled 2>/dev/null | tr -d '\r' | sed 's/^/adb_enabled = /' || true
"$ADB" shell settings get global development_settings_enabled 2>/dev/null | tr -d '\r' \
  | sed 's/^/development_settings_enabled = /' || true

echo
echo "--- kernel ---"
"$ADB" shell cat /proc/version 2>/dev/null | tr -d '\r' || true

echo
echo "--- storage ---"
"$ADB" shell df -h /data /metadata 2>/dev/null | tr -d '\r' || true

echo
echo "--- block devices (may be permission-restricted, that is fine) ---"
"$ADB" shell ls -l /dev/block/by-name 2>&1 | tr -d '\r' | sed -n '1,40p' || true

echo
echo "--- boot history (why it last rebooted / crashed) ---"
"$ADB" shell getprop ro.boot.bootreason 2>/dev/null | tr -d '\r' || true
"$ADB" shell ls /sys/fs/pstore 2>&1 | tr -d '\r' | sed -n '1,10p' || true

echo
echo "=== yorum ==="
state=$("$ADB" shell getprop ro.boot.verifiedbootstate 2>/dev/null | tr -d '\r')
locked=$("$ADB" shell getprop ro.boot.flash.locked 2>/dev/null | tr -d '\r')
case "$state" in
  orange) echo "bootloader : UNLOCKED (verifiedbootstate=orange) -> imzasız vbmeta ile açılış denenebilir" ;;
  green)  echo "bootloader : LOCKED (verifiedbootstate=green) -> bu haliyle modifiye AP AÇILMAZ; önce unlock" ;;
  *)      echo "bootloader : okunamadı (verifiedbootstate='$state', flash.locked='$locked')" ;;
esac
echo "Dosya: $OUT  (bu dosyayı olduğu gibi paylaş; içinde kişisel veri yok)"
