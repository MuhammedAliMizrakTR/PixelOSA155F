# Build reference — stage by stage

Entry point: `rom/gsi-build.sh` runs 1/8 … 8/8 in order and stops at the first
failure (`set -euo pipefail`). Every stage is also runnable on its own against
`work/`, so a failed step is retried alone instead of restarting a 15 GB job.

| # | Script | Reads | Writes | Fails when |
|---|---|---|---|---|
| 1 | `rom/tools.sh` | GitHub (lptools A15 r25, lz4, e2fsprogs, LineageOS avbtool) | `tools/…` | a tool does not answer its probe; no apt is used |
| 2 | `rom/gsi-inputs.sh` | `INPUTS_DIR` (Drive mount) + `inputs.lock.json` | `work/gsi/gsi.img`, `work/gsi/TAG`, `work/gsi/ANDROID_LEVEL`, `work/kernel/boot.img`, `work/fw/*.zip`, `work/build.env` | G0: unpinned / size / MD5 mismatch for the GSI, the kernel tar or the firmware |
| 3 | `rom/extract-ap.sh` | firmware zip → `AP_*.tar.md5` | `work/ap/members.txt` (order), `work/ap/small/`, `work/ap/super.img.lz4` | AP member missing after extraction; no `super.img[.lz4]` |
| 4 | *optional* `build-rilfix-module.sh` + `modify-gsi.sh` | GSI image | `/system/etc/a155f-extras/` inside the image | unsupported filesystem; needs `SKIP_GSI_EXTRAS=0` (default: skipped) |
| 5 | `rom/repack-super.sh` + `lp_plan.py` | `work/ap/super.img`, `work/gsi/gsi.img` | `work/super_new.img`, `work/lpmake_cmd.sh`, `work/ap/super.json/txt` | layout unparsable; a group cannot fit inside the real `super` |
| 6 | `rom/make-vbmeta.sh` | member list | `work/vbmeta/vbmeta*.img` (`--flags 3`) | stock AP has no `vbmeta.img` |
| 7 | `rom/pack-ap.sh` | member list + staged images | `out/AP_*.tar`, `out/dist/*` | a `.lz4` name survives; member list ≠ TAR list |
| 8 | `rom/odin_audit.py` | the produced TAR | `out/*.audit.txt` | verdict `critical` → `gsi-build.sh` exits 2 |

## Why each stage looks the way it does (do not "clean this up")

1. **Drive copy suffixes.** `resolve_input()` (kernel/firmware by name) and
   `tools/pin_gate.py` (pin by longest name prefix) both tolerate
   `… adlı dosyanın kopyası` / `… (1)`. Renaming the Drive files is optional.
2. **`bash rom/tools.sh` is a subshell.** Its `export PATH` never reaches later
   stages, so `pack-ap.sh`, `make-vbmeta.sh` and `gsi-build.sh` bootstrap the
   same PATH themselves. Without it: `lz4: command not found` at 7/8 (rc=127).
3. **`pipefail` + an early-exiting reader = SIGPIPE.** Checks use
   `sed -n '1p'` / `case`, never `| head -1` / `| grep -q`. Symptom of getting
   this wrong: `lpdumps FAIL` with rc=141 on a perfectly good toolchain.
4. **Two stages are destructive by design.** `extract-ap.sh` deletes the staged
   firmware zip; `repack-super.sh` deletes `work/parts/` and `work/ap/super.raw`.
   A partial re-run must re-stage first — or just re-run the whole
   `gsi-build.sh`, which does that.
5. **The GSI `system.img` may be sparse.** `rom/simg2img.py` (pure Python)
   converts it because `lpmake --image` needs raw bytes.
6. **liblp offsets.** Header at 12288, backup geometry at 8192; in v1.x
   `tables_size@44`, `checksum@48`, descriptor offsets relative to `header_size`.
   `tools/super_inspect.py` understands both text and JSON `lpdump` output.
7. **`system.img` > 4 GiB is normal** → NOTE, not an error.
8. **Stock APs carry a `meta-data/` directory entry.** `odin_audit.py` reports it
   as a NOTE; only symlinks/devices are warnings.
9. **`mtime/uid/gid` are normalised when packing** (`--mtime=@0 --owner=0
   --group=0 --numeric-owner`) but the member list is *never* sorted: the stock
   order is the Odin contract. Without the normalisation every run produced a
   different SHA-256.

## Environment

| Variable | Default | Meaning |
|---|---|---|
| `INPUTS_DIR` | *(required)* | folder holding GSI zip, kernel tar(s), firmware zip |
| `INPUTS_LOCK` | `inputs/inputs.lock.json` | pin file used by G0 |
| `KERNEL_VARIANT` | `bakasu` | `bakasu` \| `kernelsunext` \| `stock` |
| `FW_VERSION` | `A155FXXS7CYG4` | also the kernel tar name component |
| `ROM_NAME` | `PixelOS` | AP file-name prefix |
| `GSI_ZIP` | auto (`*-MysticGSI.zip*`) | explicit donor |
| `SKIP_GSI_EXTRAS` | `1` | `0` embeds the RIL-fix module into the image |
| `KERNEL_SHA` | unset | extra SHA-256 check for the kernel tar (G0 already pins MD5) |

## Re-running one stage

```bash
# 7/8 failed after everything else succeeded
bash rom/pack-ap.sh
python3 tools/odin_audit.py out/AP_*.tar | tee out/AP_audit.txt
```

`work/build.env` carries `KERNEL_VARIANT` / `FW_VERSION` / `ROM_NAME`, so a lone
`pack-ap.sh` reproduces exactly the same AP name.

## Outputs and transport

```
out/AP_SM-A155F_PixelOS-<TAG>_<kernel>_<FW_VERSION>.tar   plain TAR — flashed as-is
out/<APBASE>.audit.txt                                    audit verdict
out/dist/<APBASE>.SHA256SUMS.txt                          TAR + per-part SHA-256
out/dist/<APBASE>.tar.00 …                                transport parts (GitHub's 2 GB asset cap)
out/dist/<APBASE>.JOIN.txt                                `cat … .tar.[0-9][0-9] > …tar`
```

The `.tar.NN` parts are byte ranges, not flashable members. The AP is one file.
