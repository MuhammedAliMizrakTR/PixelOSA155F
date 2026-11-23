#!/usr/bin/env bash
# Provisions the sandbox/CI toolchain with NO apt dependency:
#   lptools (lpmake/lpunpack/lpdumps static, Rprop android-15.0.0_r25)
#   lz4 (built from source), e2fsprogs (mke2fs/debugfs/e2fsck/resize2fs),
#   avbtool (LineageOS AOSP mirror)
# Installs into ./tools/. Idempotent. Usage: rom/tools.sh
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p tools
export PATH="$(pwd)/tools/lptools/linux_glibc_x86_64:$(pwd)/tools/lz4:$(pwd)/tools/e2fsprogs/b/misc:$(pwd)/tools/e2fsprogs/b/debugfs:$(pwd)/tools/e2fsprogs/b/e2fsck:$(pwd)/tools/e2fsprogs/b/resize:$PATH"

if [ ! -x tools/lptools/linux_glibc_x86_64/lpmake ]; then
  echo "[tools] lptools (static, android-15.0.0_r25)"
  rm -rf tools/lptools
  git clone --depth 1 https://github.com/Rprop/aosp15_partition_tools.git tools/lptools
  chmod +x tools/lptools/linux_glibc_x86_64/*
fi

if [ ! -x tools/lz4/lz4 ]; then
  echo "[tools] building lz4"
  rm -rf tools/lz4
  git clone --depth 1 https://github.com/lz4/lz4.git tools/lz4
  make -C tools/lz4 -j"$(nproc)" lz4 >/dev/null
fi

if [ ! -x tools/e2fsprogs/b/debugfs/debugfs ]; then
  echo "[tools] building e2fsprogs (debugfs/e2fsck/resize2fs/mke2fs) — a few minutes"
  rm -rf tools/e2fsprogs
  git clone --depth 1 https://github.com/tytso/e2fsprogs.git tools/e2fsprogs
  ( cd tools/e2fsprogs && mkdir -p b && cd b && ../configure --disable-nls --disable-defrag >/dev/null && make -j"$(nproc)" >/dev/null )
fi

if [ ! -f tools/avb/avbtool.py ]; then
  echo "[tools] avbtool"
  rm -rf tools/avb
  git clone --depth 1 https://github.com/LineageOS/android_external_avb tools/avb
fi

echo "[tools] verifying"
# No `echo | grep -q` here: grep exits at the first match, echo then takes SIGPIPE,
# and `set -o pipefail` turns a *successful* check into a failure (observed as a
# random "lpdumps FAIL" on an otherwise fine toolchain).
out=$(lpmake 2>&1 || true)
case "$out" in *"command-line tool"*) ;; *) echo "lpmake FAIL"; echo "$out" | sed -n '1,5p'; exit 1 ;; esac
out=$(lpdumps 2>&1 || true)
case "$out" in *"dumping Android Logical Partition"*) ;; *) echo "lpdumps FAIL"; echo "$out" | sed -n '1,5p'; exit 1 ;; esac
lz4 --version
debugfs -V 2>&1 | sed -n '1p'   # sed, not head: `head` can SIGPIPE debugfs and pipefail would abort the build
test -f tools/avb/avbtool.py && echo "avbtool OK"
test -f rom/simg2img.py && echo "simg2img.py OK"
echo "[tools] READY"
echo "export PATH=$(pwd)/tools/lptools/linux_glibc_x86_64:$(pwd)/tools/lz4:$(pwd)/tools/e2fsprogs/b/misc:$(pwd)/tools/e2fsprogs/b/debugfs:$(pwd)/tools/e2fsprogs/b/e2fsck:$(pwd)/tools/e2fsprogs/b/resize:\$PATH"
