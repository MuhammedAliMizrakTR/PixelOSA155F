#!/usr/bin/env bash
# Builds a plain Odin AP TAR for 1.2: no appended MD5, no LZ4 members.
# The plain TAR is retained as out/<APBASE>.tar and split only for release
# transport (GitHub's per-asset limit); joining parts reproduces that TAR.
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
# Reuse the parameters of the staged build (work/build.env) unless they are set
# explicitly in the environment - this is what makes a lone `bash rom/pack-ap.sh`
# after a failed 7/8 produce the same AP name instead of a differently named one.
if [ -f work/build.env ]; then
  while IFS='=' read -r k v; do
    [ -n "$k" ] || continue
    [ -n "${!k:-}" ] || export "$k=$v"
  done < work/build.env
fi
export KERNEL_VARIANT="${KERNEL_VARIANT:-bakasu}"
export FW_VERSION="${FW_VERSION:-A155FXXS7CYG4}"
export ROM_NAME="${ROM_NAME:-PixelOS}"

command -v lz4 >/dev/null || { echo "FATAL: lz4 not found in PATH and tools/lz4/lz4 is missing - run: bash rom/tools.sh"; exit 1; }
mkdir -p work/stage out/dist

RTAG=$(cat work/gsi/TAG)
APBASE="AP_SM-A155F_${ROM_NAME:-RestlessOS}-${RTAG}_${KERNEL_VARIANT}_${FW_VERSION}"
STAGE=work/stage
OUT_MEMBERS=work/ap/packed-members.txt
: > "$OUT_MEMBERS"

while IFS= read -r m; do
  [ -n "$m" ] || continue
  case "$m" in
    boot.img.lz4|boot.img)
      cp work/kernel/boot.img "$STAGE/boot.img"
      outname=boot.img
      echo "boot.img <- v1.0 kernel ($KERNEL_VARIANT), raw/uncompressed"
      ;;
    super.img.lz4|super.img)
      cp work/super_new.img "$STAGE/super.img"
      outname=super.img
      echo "super.img <- ${ROM_NAME:-RestlessOS} $RTAG + stock vendor/odm/product carried over, raw/uncompressed"
      ;;
    vbmeta*.img.lz4)
      outname="${m%.lz4}"
      cp "work/vbmeta/$outname" "$STAGE/$outname"
      echo "$outname <- verification-disabled, raw/uncompressed"
      ;;
    vbmeta*.img)
      outname="$m"
      cp "work/vbmeta/$outname" "$STAGE/$outname"
      echo "$outname <- verification-disabled, raw/uncompressed"
      ;;
    *.lz4)
      outname="${m%.lz4}"
      src="work/ap/small/$m"
      [ -f "$src" ] || { echo "FATAL: missing compressed member $src"; exit 1; }
      mkdir -p "$(dirname "$STAGE/$outname")"
      LZ4BIN=$(command -v lz4 || true)
      [ -n "$LZ4BIN" ] || { echo "FATAL: lz4 needed to unpack $m but not found - run: bash rom/tools.sh"; exit 1; }
      "$LZ4BIN" -d -f "$src" "$STAGE/$outname"
      echo "$outname <- stock member decompressed from $m"
      ;;
    *)
      outname="$m"
      if [ -d "work/ap/small/$m" ]; then
        mkdir -p "$STAGE/$outname"
      else
        mkdir -p "$(dirname "$STAGE/$outname")"
        cp "work/ap/small/$m" "$STAGE/$outname"
      fi
      echo "$outname (stock, uncompressed/unchanged)"
      ;;
  esac
  printf '%s\n' "$outname" >> "$OUT_MEMBERS"
done < work/ap/members.txt

if grep -q '\.lz4$' "$OUT_MEMBERS"; then
  echo "FATAL: packed member list still contains LZ4 names"; exit 1
fi
OUT_TAR="out/${APBASE}.tar"
# Reproducible bytes: the member ORDER comes from -T (stock order, never sorted);
# only the metadata that carries no information (mtime, uid/gid, user/group names)
# is normalised. Two runs over the same inputs then give the same SHA-256, so a
# published hash can actually be re-checked. --format is left at GNU so long
# member names stay legal.
( cd "$STAGE" && tar --no-recursion --mtime=@0 --owner=0 --group=0 --numeric-owner \
    -cf "$OLDPWD/$OUT_TAR" -T "$OLDPWD/$OUT_MEMBERS" )
# Structural checks: plain TAR, exact ordered member list, and no MD5 trailer.
tar -tf "$OUT_TAR" > work/ap/packed-tar-list.txt
diff -u "$OUT_MEMBERS" work/ap/packed-tar-list.txt
TAR_SHA=$(sha256sum "$OUT_TAR" | cut -d' ' -f1)
printf '%s  %s.tar\n' "$TAR_SHA" "$APBASE" > "out/dist/${APBASE}.SHA256SUMS.txt"
split -b 1900M -d -a 2 "$OUT_TAR" "out/dist/${APBASE}.tar."
( cd out/dist && sha256sum "${APBASE}.tar."[0-9][0-9] >> "${APBASE}.SHA256SUMS.txt" )
echo "Plain AP TAR: $OUT_TAR ($(stat -c%s "$OUT_TAR") bytes), sha256=$TAR_SHA"
cat > "out/dist/${APBASE}.JOIN.txt" <<JOIN
The Odin AP is ONE file: ${APBASE}.tar ($(stat -c%s "$OUT_TAR") bytes)
  sha256: ${TAR_SHA}

The ".tar.NN" files next to this note are byte ranges of that TAR, in order, made
only because GitHub release assets are capped at 2 GB. They are NOT flashable.
Restore the TAR (any shell, no extra tools):

  cd <folder with the parts>
  cat ${APBASE}.tar.[0-9][0-9] > ${APBASE}.tar
  sha256sum -c ${APBASE}.SHA256SUMS.txt     # the .tar line must say OK

Flash ${APBASE}.tar as Odin's AP slot. Nothing else in this folder is flashed.
JOIN
echo "Release transport parts (no compression/no MD5):"
ls -lh "out/dist/${APBASE}.tar."*
df -h . | tail -1
echo "=== AP packaged: ${APBASE}.tar (split for transport only; see out/dist/${APBASE}.JOIN.txt) ==="
