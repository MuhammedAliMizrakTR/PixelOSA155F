# AP_SM-A155F_PixelOS-${RTAG} — Odin AP package

Build date: ${BUILD_DATE}
Device: Samsung Galaxy A15 4G (**SM-A155F only**), MediaTek MT6789, GKI 5.10.226
Stock base: ${FW_VERSION} (${FW_REGION})
Kernel variant: ${KERNEL_VARIANT}
Artifact: `${APBASE}.tar`

## What is inside

| Member | Source |
|---|---|
| `boot.img` | owner kernel tar (`${KERNEL_VARIANT}`), raw/uncompressed |
| `super.img` | rebuilt liblp: PixelOS GSI as `system`, stock `vendor` / `odm` / `product` kept byte-identical |
| `vbmeta.img`, `vbmeta_system.img` | rebuilt with `avbtool make_vbmeta_image --flags 3` (verification + verity disabled) |
| remaining members | stock AP members, decompressed and unchanged, in the stock order |

Plain `.tar` — no `.tar.md5` fingerprint, no LZ4 members.

## SIM fix

${SIMFIX_LINE}

## Measured status

* Packaging: `tools/odin_audit.py` verdict is recorded in the accompanying
  `.audit.txt` file.
* **Boot: unmeasured.** Packaging correctness is not a boot guarantee.
* Read `VERSION LADDER` in the build log before installing: the donor Android
  level, and the A16 result from 2026-11-22 (bootloader accepted, Samsung logo
  passed, system UI never came up).

## Before flashing

* Confirm the SW REV / fused revision contradiction is resolved and keep the
  stock package for rollback.
* The agent that produced this package did not flash and does not advise
  flashing.
