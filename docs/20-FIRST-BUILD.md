# First build — runbook (Colab, in this order)

Do not skip to step 4. Step 2 is the reason the pipeline can be trusted at all.

## 1. Toolchain, tests

```bash
bash rom/tools.sh
python3 -m unittest discover -s tests      # 39 OK
```

`tools.sh` needs no apt: it clones lptools (static A15 r25 binaries), builds lz4
and e2fsprogs, and clones LineageOS avbtool into `tools/`.

## 2. Synthetic end-to-end (must be green before any real input)

```bash
bash tools/mk_synthetic_inputs.sh /tmp/pixelinputs
INPUTS_DIR=/tmp/pixelinputs INPUTS_LOCK=/tmp/pixelinputs/inputs.lock.json \
  bash rom/gsi-build.sh
```

Expected: `rc=0`, `AP_SM-A155F_PixelOS-Demo-A17_bakasu_A155FXXS7CYG4.tar`,
`VERDICT: clean`. The fixture is fake data with real layout (real `lpmake`
super, real Android-sparse `system.img`, real plain AP TAR, Drive copy suffixes
in the file names).

## 3. Verify the pins against the Drive folder (G0)

```bash
FOLDER=/content/drive/MyDrive/PixelOSA155F
python3 tools/verify_inputs.py --dir "$FOLDER" --quick      # sizes first
python3 tools/verify_inputs.py --dir "$FOLDER"              # full MD5 (multi-GB, slow)
```

`--quick` is sizes only; the build itself re-hashes every file it reads, so a
full manual pass is optional.

## 4. Real build

```bash
INPUTS_DIR=/content/drive/MyDrive/PixelOSA155F \
KERNEL_VARIANT=bakasu ROM_NAME=PixelOS \
bash rom/gsi-build.sh 2>&1 | tee build.log
```

Watch for the `VERSION LADDER WARNING` at 2/8: the donor currently in Drive is
Android 17, while the measured rule for this device is A15 first.

## 5. Deliver

| What | Where | Note |
|---|---|---|
| code + docs | git (`rom/`, `tools/`, `tests/`, `docs/`, `inputs/`) | text only |
| `out/AP_*.tar` (≥ 5.8 GB) | GitHub Release asset | not committed; use `out/dist/*.tar.NN` parts + the SHA-256 manifest |
| single-file runner | Drive folder | `bash tools/make_single_file.sh`, regenerate after every change |

## 6. If a stage fails

Read the stage number in `build.log`, fix that stage, re-run **only** it (see
`docs/ROM_BUILD.md`). Re-stage after `extract-ap.sh` / `repack-super.sh`
because those two free disk space by deleting their inputs.

## 7. Before flashing anything

The `SW REV CHECK FAIL [super] Fused 7 > Binary 8` contradiction is unresolved
and the stock package must be on hand for rollback. The agent does not flash and
does not recommend flashing. Boot stays **unmeasured** until a device logcat
exists.
