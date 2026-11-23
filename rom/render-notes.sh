#!/usr/bin/env bash
# Renders the English release notes for the ROM package.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p out
export RTAG=${RTAG:-$(cat work/gsi/TAG 2>/dev/null || echo "${RESTLESS_REF:-unknown}")}
export KERNEL_VARIANT=${KERNEL_VARIANT:-bakasu}
export FW_VERSION=${FW_VERSION:-A155FXXS7CYG4}
export FW_REGION=${FW_REGION:-TUR}
export ROM_NAME=${ROM_NAME:-PixelOS}
export APBASE="AP_SM-A155F_${ROM_NAME}-${RTAG}_${KERNEL_VARIANT}_${FW_VERSION}"
export BUILD_DATE=$(date -u +%Y-%m-%d)
export SIMFIX_LINE
if [ "$KERNEL_VARIANT" = "vanilla" ]; then
  SIMFIX_LINE="**NOT AVAILABLE** — the vanilla kernel has no root, so the SIM-fix module cannot be installed. The network drops roughly every 7 hours; a reboot is needed. Use the kernelsunext/bakasu package for the SIM fix."
else
  SIMFIX_LINE="**INCLUDED** — \`/system/etc/a155f-extras/RILFix_A15.zip\` is embedded in the ROM. After installation, install and open the matching manager APK from this release's separate asset, then Modules → Install from storage → \`/system/etc/a155f-extras/RILFix_A15.zip\`. The module restarts ril-daemon every 6 hours (the XDA-proven workaround for the ~7h25m modem hang)."
fi
envsubst '$RTAG $APBASE $KERNEL_VARIANT $FW_VERSION $FW_REGION $BUILD_DATE $SIMFIX_LINE' \
  < rom/release-notes-template.md > out/RELEASE_NOTES.md
cp out/RELEASE_NOTES.md out/dist/RELEASE_NOTES.md
echo "--- notes ---"; head -30 out/RELEASE_NOTES.md
