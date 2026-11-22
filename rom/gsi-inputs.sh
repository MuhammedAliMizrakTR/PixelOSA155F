#!/usr/bin/env bash
# Stages the ROM inputs for the PixelOS-GSI line, from a local folder (Drive mount):
#   <*-MysticGSI.zip>           GSI, MD5-gated against inputs/inputs.lock.json
#   <kernel>.tar                owner kernel artifact (default: bakasu), boot.img only
#   <*_fac.zip> or AP_*.tar*    stock firmware for the vendor/odm bytes + member order
#
# Produces:
#   work/gsi/gsi.img   raw (unsparse) system image, ready for lpmake --image
#   work/gsi/TAG       short build tag used in the AP filename
#   work/kernel/boot.img
#   work/fw/*.zip  or  work/ap/AP_*.tar*
set -euo pipefail
cd "$(dirname "$0")/.."

: "${INPUTS_DIR:?FATAL: set INPUTS_DIR to the folder holding the GSI zip, kernel tar and firmware zip}"
KERNEL_VARIANT="${KERNEL_VARIANT:-bakasu}"
FW_VERSION="${FW_VERSION:-A155FXXS7CYG4}"
mkdir -p work/gsi work/kernel work/fw work/ap

DF() { df -h . | tail -1; }
say() { printf '\n=== %s\n' "$*"; }

# Google Drive appends a localized suffix when a file is copied into a folder:
#   "bakasu_..._GKI.tar adlı dosyanın kopyası", "... (1)", "... - copy"
# so an exact-name lookup is not enough. resolve_input() takes the expected base
# name and returns the matching file (exact name first, then "<name>*"), picking
# the largest match when there are several, because every candidate is the same
# artifact. Prints nothing and returns 1 when nothing matches.
resolve_input() {
  local want="$1" f
  local matches=()
  if [ -f "$INPUTS_DIR/$want" ]; then printf '%s\n' "$INPUTS_DIR/$want"; return 0; fi
  for f in "$INPUTS_DIR/$want"*; do [ -f "$f" ] && matches+=("$f"); done
  [ "${#matches[@]}" -gt 0 ] || return 1
  if [ "${#matches[@]}" -gt 1 ]; then
    echo "note: ${#matches[@]} files match '$want*'; using the largest:" >&2
    printf '  %s\n' "${matches[@]}" >&2
  fi
  for f in "${matches[@]}"; do printf '%s\t%s\n' "$(stat -c%s "$f")" "$f"; done \
    | sort -rn | head -1 | cut -f2-
}

say "inputs: $INPUTS_DIR"
[ -d "$INPUTS_DIR" ] || { echo "FATAL: $INPUTS_DIR is not a directory"; exit 1; }
DF

# ---------------------------------------------------------------- GSI (MD5 gate)
GSI_ZIP="${GSI_ZIP:-}"
if [ -z "$GSI_ZIP" ]; then
  # Every Mystic GSI Updates build ends with "-MysticGSI.zip"; that token works
  # for Pixel-*, Nothing-* and Generic builds alike. Google's own GSIs
  # (gsi_gms_arm64-exp-*.zip), PixelOS (treble_pixelos-*.zip) and the other
  # TrebleDroid builders do not follow that name, so the second pass accepts any
  # zip that really carries a system image member - never a name guess.
  mapfile -t CANDS < <(find "$INPUTS_DIR" -maxdepth 1 -type f -name '*-MysticGSI.zip*' ! -name '*src*' | sort)
  if [ "${#CANDS[@]}" -eq 0 ]; then
    while IFS= read -r f; do
      LIST=$(unzip -Z1 "$f" 2>/dev/null || true)     # capture: `unzip | grep` dies by SIGPIPE
      case "$LIST" in
        *system.img*) CANDS+=("$f") ;;
      esac
    done < <(find "$INPUTS_DIR" -maxdepth 1 -type f -name '*.zip' \
               ! -name '*_fac.zip*' ! -name 'SAMFW*' ! -name '*src*' | sort)
  fi
  if [ "${#CANDS[@]}" -eq 0 ]; then
    # Several builders (Doze-off/Infinity X, BestGSI, Aizner, AndyYan) publish one
    # .img.xz instead of a zip. Accept that too, but never a boot/vbmeta/recovery/
    # super image that merely happens to sit in the same folder.
    while IFS= read -r f; do
      case "$(basename "$f")" in
        boot*|vbmeta*|recovery*|super*|dtbo*|userdata*) continue ;;
      esac
      CANDS+=("$f")
    done < <(find "$INPUTS_DIR" -maxdepth 1 -type f \
               \( -name '*.img.xz' -o -name '*.img.gz' -o -name '*.img' \) | sort)
  fi
  [ "${#CANDS[@]}" -gt 0 ] || {
    echo "FATAL: no GSI in $INPUTS_DIR"
    echo "  looked for: *-MysticGSI.zip*, any .zip containing system.img*, then *.img.xz/.img.gz/.img"
    ls -1 "$INPUTS_DIR" | sed 's/^/    /' || true
    exit 1
  }
  GSI_ZIP="${CANDS[0]}"
  [ "${#CANDS[@]}" -gt 1 ] && echo "note: multiple GSI zips found, using $(basename "$GSI_ZIP") (set GSI_ZIP to override)"
fi
[ -f "$GSI_ZIP" ] || { echo "FATAL: GSI file not found: $GSI_ZIP"; exit 1; }
say "GSI: $(basename "$GSI_ZIP")"
LOCK="${INPUTS_LOCK:-inputs/inputs.lock.json}"
# Gate G0 (hard): no pin, no build. tools/pin_gate.py matches the longest pinned
# name that is a prefix of the real file, so a Drive copy suffix is harmless, and
# it re-hashes the bytes instead of trusting the file name.
python3 tools/pin_gate.py --lock "$LOCK" --file "$GSI_ZIP" --role donor-gsi-primary \
  || { echo "FATAL: GSI failed the G0 pin gate - re-download; build stops here"; exit 1; }

say "extracting system.img"
rm -rf work/gsi/zip
mkdir -p work/gsi/zip
case "$GSI_ZIP" in
  *.img.xz|*.img.gz|*.img.lz4|*.img)
    # Single-file donor (Infinity X, BestGSI, Aizner, AndyYan ...): the whole file
    # is the system image, optionally compressed. No zip, no members.
    echo "single-image donor: $(basename "$GSI_ZIP")"
    case "$GSI_ZIP" in
      *.img.xz)  command -v xz >/dev/null || { echo "FATAL: xz not found (apt install xz-utils)"; exit 1; }
                 xz -dc "$GSI_ZIP" > work/gsi/zip/system.img ;;
      *.img.gz)  gzip -dc "$GSI_ZIP" > work/gsi/zip/system.img ;;
      *.img.lz4) lz4 -d -f "$GSI_ZIP" work/gsi/zip/system.img >/dev/null 2>&1 \
                   || { echo "FATAL: lz4 failed on $(basename "$GSI_ZIP") (run: bash rom/tools.sh)"; exit 1; } ;;
      *)         cp "$GSI_ZIP" work/gsi/zip/system.img ;;
    esac
    ;;
esac
if [ ! -f work/gsi/zip/system.img ] && ! python3 tools/gsi_inspect.py "$GSI_ZIP" --extract work/gsi/zip --only system.img >/dev/null 2>&1; then
  echo "note: gsi_inspect refused (see below); falling back to plain unzip"
  python3 tools/gsi_inspect.py "$GSI_ZIP" || true
  unzip -o -j "$GSI_ZIP" system.img -d work/gsi/zip >/dev/null 2>&1 || true
fi
# Some donors ship system.img.xz / .gz / .lz4 instead of a raw member (Google's
# own GSI zips are raw, several TrebleDroid builders are not). Decompress once,
# keep the original zip untouched.
if [ ! -f work/gsi/zip/system.img ]; then
  for ext in xz gz lz4; do
    if unzip -o -j "$GSI_ZIP" "system.img.$ext" -d work/gsi/zip >/dev/null 2>&1; then
      echo "system.img.$ext found -> decompressing"
      case "$ext" in
        xz)  command -v xz  >/dev/null || { echo "FATAL: xz not found (apt install xz-utils on the runner)"; exit 1; }
             xz -dc "work/gsi/zip/system.img.xz" > work/gsi/zip/system.img ;;
        gz)  gzip -dc "work/gsi/zip/system.img.gz" > work/gsi/zip/system.img ;;
        lz4) lz4 -d -f "work/gsi/zip/system.img.lz4" work/gsi/zip/system.img >/dev/null 2>&1 \
               || { echo "FATAL: lz4 failed on system.img.lz4 (run: bash rom/tools.sh)"; exit 1; } ;;
      esac
      rm -f "work/gsi/zip/system.img.$ext"
      break
    fi
  done
fi
[ -f work/gsi/zip/system.img ] || {
  echo "FATAL: no system image found in $GSI_ZIP"
  echo "  accepted: zip member system.img[.xz|.gz|.lz4], or a bare *.img[.xz|.gz|.lz4] donor"
  exit 1
}

if python3 -c "import sys; sys.exit(0 if open('work/gsi/zip/system.img','rb').read(4)==b'\x3a\xff\x26\xed' else 1)"; then
  echo "system.img is Android-sparse -> rom/simg2img.py (lpmake needs raw)"
  python3 rom/simg2img.py work/gsi/zip/system.img work/gsi/gsi.img
else
  mv work/gsi/zip/system.img work/gsi/gsi.img
fi
rm -rf work/gsi/zip
GSI_SIZE=$(stat -c%s work/gsi/gsi.img)
echo "raw system image: $GSI_SIZE bytes"

# ------------------------------------------------------------------------ TAG
# tools/gsi_tag.py resolves the Android level from the name tokens: a plain
# integer in 9..25 first ("Pixel-raven-17-..."), then a codename
# ("Pixel-cheetah-CinnamonBun-..." -> 17). Field 3 alone produced
# "cheetah-ACinnamonBun" for the codename shape.
TAG="${GSI_TAG:-$(python3 tools/gsi_tag.py "$GSI_ZIP")}"
ANDROID_LEVEL="${GSI_LEVEL:-$(python3 tools/gsi_tag.py --version "$GSI_ZIP" 2>/dev/null || echo unknown)}"
printf '%s\n' "$TAG" > work/gsi/TAG
printf '%s\n' "$ANDROID_LEVEL" > work/gsi/ANDROID_LEVEL
echo "TAG: $TAG (Android level: $ANDROID_LEVEL)"

# Version ladder (evidence, not a guess): the 2026-11-22 NothingOS A16 attempt was
# accepted by the bootloader and got past the Samsung logo, but never brought up
# the system UI. The rule that came out of it is "A15 (vendor-compatible) first,
# A16/A17 only with logcat evidence". This is a loud warning, not a hard stop, so
# the owner can still stage an A17 donor deliberately - but it is recorded.
case "$ANDROID_LEVEL" in
  ''|unknown|9|10|11|12|13|14|15) ;;
  *)
    {
      echo
      echo "  ############################################################"
      echo "  # VERSION LADDER WARNING: donor is Android $ANDROID_LEVEL        "
      echo "  # The measured rule for this device is A15 first; the A16       "
      echo "  # NothingOS build booted past the logo but never reached the    "
      echo "  # system UI. Boot success here is UNMEASURED.                   "
      echo "  # Evidence wanted before going up the ladder: a logcat from     "
      echo "  # this device with this donor.                                   "
      echo "  ############################################################"
      echo
    }
    ;;
esac
DF

# ---------------------------------------------------------------------- kernel
case "$KERNEL_VARIANT" in
  bakasu)       KTAR="bakasu_35262_susfs_v2.4.0_${FW_VERSION}_A15_GKI.tar" ;;
  kernelsunext) KTAR="kernelsunext_33548_susfs_v2.4.0_${FW_VERSION}_A15_GKI.tar" ;;
  stock|vanilla) KTAR="stock_optimized_5.10.226_${FW_VERSION}_A15_GKI.tar" ;;
  *) echo "FATAL: unknown KERNEL_VARIANT=$KERNEL_VARIANT (bakasu|kernelsunext|stock)"; exit 1 ;;
esac
say "kernel: $KTAR"
KTARPATH=$(resolve_input "$KTAR" || true)
if [ -z "${KTARPATH:-}" ]; then
  echo "FATAL: kernel tar not found in $INPUTS_DIR"
  echo "  wanted: $KTAR   (or a copy whose name starts with it)"
  echo "  files present:"
  ls -1 "$INPUTS_DIR" | sed 's/^/    /' || true
  echo "  fix: rename the file to exactly '$KTAR', or pick KERNEL_VARIANT=bakasu|kernelsunext|stock"
  exit 1
fi
[ "$KTARPATH" = "$INPUTS_DIR/$KTAR" ] || echo "  using: $(basename "$KTARPATH")"
KSHA="${KERNEL_SHA:-}"
if [ -n "$KSHA" ]; then
  echo "$KSHA  $KTARPATH" | sha256sum -c - \
    || { echo "FATAL: kernel SHA-256 mismatch"; exit 1; }
else
  echo "note: KERNEL_SHA not set - recording the hash instead of enforcing it"
  sha256sum "$KTARPATH"
fi
# Gate G0 for the kernel tar: size + MD5 against the pin (bakasu is the default
# variant, but every pinned variant is gated the same way).
python3 tools/pin_gate.py --lock "$LOCK" --file "$KTARPATH" --name "$KTAR" \
  || { echo "FATAL: kernel tar failed the G0 pin gate - build stops here"; exit 1; }
tar -tf "$KTARPATH" > work/kernel/members.txt
grep -qx 'boot.img' work/kernel/members.txt \
  || { echo "FATAL: $(basename "$KTARPATH") has no boot.img member"; sed -n '1,20p' work/kernel/members.txt; exit 1; }
tar -xf "$KTARPATH" -C work/kernel boot.img
echo "boot.img: $(stat -c%s work/kernel/boot.img) bytes, sha256=$(sha256sum work/kernel/boot.img | cut -d' ' -f1)"

# -------------------------------------------------------------------- firmware
say "stock firmware"
FWZ=""
for f in "$INPUTS_DIR"/AP_*.tar "$INPUTS_DIR"/AP_*.tar.md5 "$INPUTS_DIR"/AP_*.tar*; do
  [ -f "$f" ] && { FWZ="$f"; break; }
done
if [ -n "$FWZ" ]; then
  cp "$FWZ" "work/ap/$(basename "$FWZ")" && echo "AP tar staged (LOCAL mode): $(basename "$FWZ")"
else
  # a Drive copy suffix ("...zip adlı dosyanın kopyası", "... (1)") is tolerated
  for pat in '*_fac.zip*' 'SAMFW*.zip*'; do
    for f in "$INPUTS_DIR"/$pat; do
      [ -f "$f" ] && { FWZ="$f"; break 2; }
    done
  done
  if [ -z "$FWZ" ]; then
    echo "FATAL: need AP_*.tar or *_fac.zip in $INPUTS_DIR"
    ls -1 "$INPUTS_DIR" | sed 's/^/    /' || true
    exit 1
  fi
  # Gate G0 for the stock firmware: this is the file whose AP member order and
  # vendor/odm bytes the whole package depends on.
  python3 tools/pin_gate.py --lock "$LOCK" --file "$FWZ" --role stock-firmware \
    || { echo "FATAL: firmware zip failed the G0 pin gate - build stops here"; exit 1; }
  cp "$FWZ" "work/fw/${FW_VERSION}_fac.zip"
  echo "firmware zip staged: $(basename "$FWZ") ($(stat -c%s "$FWZ") bytes)"
  echo "  as: work/fw/${FW_VERSION}_fac.zip (canonical name, keeps spaces out of later steps)"
  echo "  md5: $(md5sum "$FWZ" | cut -d' ' -f1)"
fi
DF

# Record the exact parameters of this staged build so a later single stage
# (e.g. `bash rom/pack-ap.sh` after a failure) reproduces the same file names
# without the operator having to remember the env vars.
{
  echo "KERNEL_VARIANT=$KERNEL_VARIANT"
  echo "FW_VERSION=$FW_VERSION"
  echo "ROM_NAME=${ROM_NAME:-PixelOS}"
  echo "EXCLUDE_USERDATA=${EXCLUDE_USERDATA:-0}"
} > work/build.env
say "build parameters -> work/build.env"
cat work/build.env

say "inputs ready"
echo "  gsi   : work/gsi/gsi.img ($GSI_SIZE bytes, TAG=$(cat work/gsi/TAG))"
echo "  kernel: work/kernel/boot.img ($KERNEL_VARIANT)"
ls work/fw work/ap 2>/dev/null || true
echo "next: bash rom/extract-ap.sh"
