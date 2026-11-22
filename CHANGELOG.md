# Changelog

All notable changes to the PixelOSA155F build line. English, newest first.
Dates are UTC. This project only ever *adds* — an existing artifact is never
deleted, overwritten or renamed by a build.

## 2026-11-22 — artifact archived + "keep my data" switch

### Result

* The 12,222,085,120 B AP was copied to Drive
  (`PixelOSA155F/out/…tar`, 60.99 GiB free, ~120-180 MiB/s) and
  re-hashed **from the Drive mount**: sha256 `f0cc78c9…3662` → match. Google's own
  MD5 for the object: `246716fc6e2a4b3b3d3bfc316d2b99dd`. The audit report was
  re-read from Drive: `VERDICT: clean`, 1,944 B.

### Added

* `EXCLUDE_USERDATA=1` (read by `rom/gsi-build.sh` and `rom/pack-ap.sh`, recorded
  in `work/build.env`): leaves the stock `userdata.img` out of the AP so flashing
  does not overwrite user data. Default `0` = stock member preserved.
  Verified both ways on a members-list fixture: default AP carries
  `userdata.img`, flagged AP does not, `odin_audit` clean in both cases.
* `colab_rescue_to_drive.py`: post-build cell (verify sha256 → archive audit +
  manifest to Drive → copy the TAR when Drive has room, else split into 1,900 MB
  transport parts with per-part download lines). Uploaded to the Drive folder.

### Fixed

* Progress lines in the Colab cells could print a garbled percentage when the
  wall-clock delta was tiny; the percentage/ETA are now clamped to 0..100 and the
  division is guarded.

## 2026-11-22 — first real PixelOS AP (owner's Colab)

### Result

* `AP_SM-A155F_PixelOS-cheetah-A17_bakasu_A155FXXS7CYG4.tar` —
  12,222,085,120 B, sha256
  `f0cc78c9ae26a4066ffd0bd0888e1d2be63673ca44828d658beeaedaedbe3662`,
  built in 1348 s from the one-file Colab runner with the real A17 donor GSI and
  the real `A155FXXS7CYG4` firmware; `odin_audit` **`VERDICT: clean`** (rc=0).
* G0 verified in-run for all three inputs (GSI `81f41e26…a61a`, kernel
  `39800312…8054`, firmware `bea1131d…9b57`).
* Rebuilt super: 9,434,177,656 B sparse / 11,744,051,200 B expanded, six logical
  partitions, `system` 6,233,522,176 from the GSI (+464,314,368 vs stock), the
  other five byte-identical to stock.
* 20 stock AP entries replayed in stock order, including `meta-data/`,
  `meta-data/fota.zip`, `userdata.img`, `recovery.img` and the `*-verified.img`
  set; zero `.lz4` members, no MD5 footer.

### Fixed

* `tools/gsi_inspect.py` now classifies `AVB0` (`avb-vbmeta`) and `VNDRBOOT`
  (`android-vendor-boot`). The real audit printed `container=unknown` for
  `vendor_boot.img` and both `vbmeta*.img`; the members were fine, the label was
  blind. Tests: 40 OK.

### Notes for the owner

* The AP carries the stock `userdata.img` (16 GiB expanded): flashing it wipes
  user data. Excluding that member is a deliberate option, not a default.
* The artifact is ~3.9 GB larger than the stock AP because `super.img` is raw
  sparse instead of LZ4 — that is the "no LZ4 members" rule.
* Boot remains **unmeasured**; nothing was flashed.

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
