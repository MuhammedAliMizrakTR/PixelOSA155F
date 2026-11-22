#!/usr/bin/env bash
# ============================================================================
# PixelOSA155F — ONE-FILE Colab runner
#
# Kolay yol (Colab, tek hücre):
#   from google.colab import drive; drive.mount('/content/drive')
#   !bash "/content/drive/MyDrive/PixelOSA155F/PixelOSA155F-colab.sh"
#
# Bu dosya iki türlü çalışır:
#   1) içine gömülü kaynak arşiviyle  (PixelOSA155F-colab.sh)
#   2) repo içinden                   (bash colab_build.sh)
#
# Ayarlar (env ile):
#   INPUTS_DIR        GSI/kernel/firmware klasörü  (varsayılan: Drive PixelOSA155F)
#   WORKDIR           repo açılacağı yer           (varsayılan: /content/PixelOSA155F)
#   KERNEL_VARIANT    bakasu|kernelsunext|stock    (varsayılan: bakasu)
#   ROM_NAME          AP dosya adı öneki           (varsayılan: PixelOS)
#   SKIP_GSI_EXTRAS   1 = GSI'ı olduğu gibi kullan (varsayılan 1)
#   INPUTS_LOCK       G0 pin dosyası              (varsayılan repo inputs/inputs.lock.json)
#   SINGLE_FILE       1 = taşıma parçalarını sil, tek .tar bırak (varsayılan 1)
#   SKIP_BUILD        1 = sadece hazırlık+testler  (varsayılan 0)
# ============================================================================
set -euo pipefail

INPUTS_DIR="${INPUTS_DIR:-/content/drive/MyDrive/PixelOSA155F}"
WORKDIR="${WORKDIR:-/content/PixelOSA155F}"
KERNEL_VARIANT="${KERNEL_VARIANT:-bakasu}"
ROM_NAME="${ROM_NAME:-PixelOS}"
SKIP_GSI_EXTRAS="${SKIP_GSI_EXTRAS:-1}"
SINGLE_FILE="${SINGLE_FILE:-1}"
SKIP_BUILD="${SKIP_BUILD:-0}"
MARKER="#__B64_PAYLOAD_BELOW__"

say() { printf '\n\033[1m=== %s\033[0m\n' "$*"; }
die() { printf '\n\033[31mFATAL: %s\033[0m\n' "$*" >&2; exit 1; }

script_path="$(readlink -f "$0")"

# ------------------------------------------------------------------ payload
payload_line=$(awk -v m="$MARKER" '$0 == m { print NR + 1; exit }' "$script_path" || true)
if [ -n "${payload_line:-}" ]; then
  say "gömülü kaynak arşivi açılıyor -> $WORKDIR"
  mkdir -p "$WORKDIR"
  tmpzip="$(mktemp /tmp/nothingos-src.XXXXXX.zip)"
  tail -n +"$payload_line" "$script_path" | base64 -d > "$tmpzip" \
    || die "gömülü payload çözülemedi (dosya kesik/bozuk olabilir)"
  unzip -oq "$tmpzip" -d "$WORKDIR"
  rm -f "$tmpzip"
  cd "$WORKDIR"
else
  cd "$(dirname "$script_path")"
fi
[ -f rom/gsi-build.sh ] || die "rom/gsi-build.sh yok — yanlış klasördeyim: $(pwd)"
say "repo hazır: $(pwd)"

# ------------------------------------------------------------------ ön kontroller
command -v python3 >/dev/null || die "python3 yok"
command -v tar >/dev/null || die "tar yok"
command -v unzip >/dev/null || die "unzip yok"
say "disk"; df -h . | tail -1
avail_gb=$(df -BG --output=avail . | tail -1 | tr -dc '0-9')
[ "${avail_gb:-0}" -ge 25 ] || echo "UYARI: ${avail_gb}GB boş alan var; build için ~25-40GB gerekiyor"

say "araç testleri (sentetik)"
python3 -m unittest discover -s tests 2>&1 | tail -3

if [ ! -d "$INPUTS_DIR" ]; then
  die "INPUTS_DIR bulunamadı: $INPUTS_DIR
Drive bağlı mı?  from google.colab import drive; drive.mount('/content/drive')
Farklı klasörse:  INPUTS_DIR=/yol bash $script_path"
fi
say "girdiler: $INPUTS_DIR"
ls -lh "$INPUTS_DIR" 2>/dev/null | sed -n '2,20p' || true

if [ "$SKIP_BUILD" = "1" ]; then
  say "SKIP_BUILD=1 -> build atlandı"
  exit 0
fi

# ------------------------------------------------------------------ build
export INPUTS_DIR KERNEL_VARIANT ROM_NAME SKIP_GSI_EXTRAS
# The pin file travels with the environment: without this, a synthetic fixture
# directory could never exercise its own lock through the one-file runner.
INPUTS_LOCK="${INPUTS_LOCK:-inputs/inputs.lock.json}"
export INPUTS_LOCK
say "build: KERNEL_VARIANT=$KERNEL_VARIANT ROM_NAME=$ROM_NAME SKIP_GSI_EXTRAS=$SKIP_GSI_EXTRAS"
say "G0 lock: $INPUTS_LOCK"
set +e
bash rom/gsi-build.sh 2>&1 | tee build.log
build_rc=${PIPESTATUS[0]}
set -e
[ "$build_rc" -eq 0 ] || die "gsi-build.sh başarısız (rc=$build_rc) — ayrıntı: $(pwd)/build.log"

# ------------------------------------------------------------------ sonuç
AP=$(ls -t out/AP_*.tar 2>/dev/null | head -1 || true)
[ -n "$AP" ] || die "out/AP_*.tar üretilmedi — build.log'a bak"

if [ "$SINGLE_FILE" = "1" ]; then
  say "tek dosya modu: taşıma parçaları siliniyor (out/dist/*.tar.NN)"
  rm -f out/dist/*.tar.[0-9][0-9] || true
fi

say "SONUÇ"
printf 'AP TAR  : %s\n' "$AP"
printf 'boyut   : %s bayt\n' "$(stat -c%s "$AP")"
printf 'sha256  : %s\n' "$(sha256sum "$AP" | cut -d' ' -f1)"
printf 'manifest: %s\n' "$(ls out/dist/*SHA256SUMS* 2>/dev/null | head -1 || echo '-')"
audit_file=$(ls out/*.audit.txt 2>/dev/null | head -1 || true)
if [ -n "${audit_file:-}" ]; then
  printf 'audit   : %s\n' "$audit_file"
  grep -E '^(VERDICT|plain tar|members|  - )' "$audit_file" | sed 's/^/          /' || true
else
  printf 'audit   : -\n'
fi

say "BİTTİ"
echo "Flash kararı sende: SW REV/fused çelişkisi çözülmeden ve stok paket elinde olmadan flash yok."
echo "Paketleme 'clean' olsa bile bu 'boot eder' demek değildir."

exit 0
