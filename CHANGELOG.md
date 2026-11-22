# Changelog

All notable changes to the PixelOSA155F build line. English, newest first.
Dates are UTC. This project only ever *adds* — an existing artifact is never
deleted, overwritten or renamed by a build.

## 2026-11-22 — first PixelOS session

### Added — build line

* `rom/` pipeline ported from the owner's proven NothingOS/GrapheneOS line
  (same stages, same local patches): `tools.sh`, `gsi-inputs.sh`,
  `extract-ap.sh`, `repack-super.sh`, `lp_plan.py`, `simg2img.py`,
  `make-vbmeta.sh`, `pack-ap.sh`, `gsi-build.sh`, optional `modify-gsi.sh` +
  `build-rilfix-module.sh` + `simfix/`, `render-notes.sh`.
* `rom/release-notes-template.md` so `render-notes.sh` is runnable again.
* `tools/`, `tests/`, `colab_build.sh`, `inputs/` and `docs/` in the repo root;
  `ROM_NAME` defaults to `PixelOS`, GSI auto-detect matches `*-MysticGSI.zip*`.

### Added — gate G0 made real for *every* input

* `tools/pin_gate.py`: re-hashes one file against `inputs/inputs.lock.json`
  (size **and** MD5), matching the longest pinned name that is a prefix of the
  real file name so Drive copy suffixes (`… adlı dosyanın kopyası`, `… (1)`) do
  not break the pin. Exit 1 on missing pin, size mismatch or MD5 mismatch.
* `rom/gsi-inputs.sh` now gates the **kernel tar** and the **stock firmware**,
  not just the GSI. The old behaviour (`KERNEL_SHA` unset → "record the hash
  instead of enforcing it", firmware not checked at all) is gone: no pin, no
  build.
* `tools/mk_synthetic_inputs.sh` pins all three synthetic inputs, so the
  end-to-end fixture exercises all three gates.

### Added — naming and version ladder

* `tools/gsi_tag.py`: resolves the AP `<TAG>` from the name tokens. A plain
  integer in 9..25 wins (`Pixel-raven-17-15063635-…` → `raven-A17`), otherwise a
  codename is mapped (`Pixel-cheetah-CinnamonBun-…` → `cheetah-A17`). The old
  `cut -d- -f3` produced `cheetah-ACinnamonBun`.
* `rom/gsi-inputs.sh` prints a `VERSION LADDER WARNING` and writes
  `work/gsi/ANDROID_LEVEL` when the donor is newer than A15, citing the measured
  A16 NothingOS result (bootloader accepted, system UI never came up). Warning,
  not a hard stop, so an A17 donor can be staged deliberately.

### Fixed — reproducibility

* `rom/pack-ap.sh` packs with `--mtime=@0 --owner=0 --group=0 --numeric-owner`
  (member order still comes from the stock-order list, never sorted). Two runs
  over the same inputs now produce the same SHA-256; previously the TAR embedded
  the staging mtimes and every run hashed differently.

### Evidence recorded this session

* Pinned the donor actually present in Drive:
  `Pixel-cheetah-CinnamonBun-14911996-AB-20260227-MysticGSI.zip`,
  3,148,371,077 B, MD5 `81f41e26c9991743674455520db0a61a`.
  Cross-checked against the SourceForge *Mystic GSI Updates* `/Generic` RSS:
  **match**.
* Pinned the three 67,112,960 B kernel tars and the 6,904,157,493 B stock
  firmware by Drive id + MD5 (`inputs/inputs.lock.json`).
* Stock `super` geometry recorded from the owner's `lpdumps`
  (`--device-size` 11,744,051,200; used 9,354,960,896; `main` group max
  11,739,856,896) — the pipeline still re-reads the real super at stage 5/8.
* Synthetic end-to-end: rc=0,
  `AP_SM-A155F_PixelOS-Demo-A17_bakasu_A155FXXS7CYG4.tar` (138,690,560 B,
  sha256 `b49dbc0f4d96844c8dc66ea2ce011fdfdec5b8c0bab04e09fb2a37ecda799e44`),
  `VERDICT: clean`, members `boot.img · super.img · vbmeta.img · vbmeta_system.img`.
* Negative controls for G0: a 1,024 B file with the pinned name is refused on
  size; an unpinned GSI is refused outright.
* `python3 -m unittest discover -s tests` → 39 OK (28 original + 11 new).

### Not done (and why)

* **No real AP TAR.** The donor GSI (3.1 GB) and the stock firmware (6.9 GB)
  cannot leave Drive into this sandbox: the Drive connector caps at 100 MB per
  file and shell egress is limited to a few hosts. The real build is ready to
  run on Colab; see `README.md` and `docs/GATES.md`.
* **No build/boot claim.** Nothing here has run on the device. Boot is
  **unmeasured** until the owner supplies a logcat.
