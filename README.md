# PixelOSA155F — PixelOS GSI → plain Odin AP TAR for SM-A155F

Evidence-gated build line for the **Samsung Galaxy A15 4G, `SM-A155F` only**
(MediaTek MT6789 / Helio G99, GKI Linux 5.10.226).

The recipe is the one already proven on this device by the owner's
GrapheneOS/RestlessOS and NothingOS lines:

```
stock vendor + odm + product  (byte-identical, from the stock AP)
+ PixelOS GSI as the 'system' logical partition
+ raw boot.img from the owner's kernel tar
+ verification-disabled vbmeta*.img
= one plain Odin AP TAR   (no .tar.md5, no LZ4 members)
```

No firmware port. No proprietary blob/APK/key redistribution. **The agent never
flashes anything.** A `clean` verdict from `tools/odin_audit.py` means the
*packaging* is right; it is not a boot guarantee.

## Status (2026-11-22)

| Gate | What it proves | State |
|---|---|---|
| G0 hash/size pins | every input pinned in `inputs/inputs.lock.json` by Drive id + size + MD5; `tools/pin_gate.py` re-hashes before use | **PASS** — GSI MD5 cross-checked Drive ↔ SourceForge RSS (`81f41e26…a61a`, 3,148,371,077 B) |
| G1 stock AP member order | order recorded from the stock AP and replayed verbatim | **PASS on the real stock AP** (20 entries, `meta-data/` included) and on the fixture |
| G2 rebuilt super | real liblp, `vendor`+`odm`+`product` kept, fits `super` | **PASS on the real super** — 9,434,177,656 B sparse / 11,744,051,200 B expanded, all 6 logical partitions present |
| G3 packaging | plain TAR, no MD5 footer, no LZ4 member, stock order, `vbmeta* --flags 3` | **PASS on the real artifact**: 12,222,085,120 B plain TAR, 0 `.lz4` members, byte-reproducible |
| G4 audit | `tools/odin_audit.py` verdict | **`VERDICT: clean`** on the real artifact (rc=0) |

### The real build — done by the owner in Colab (2026-11-22)

```
AP_SM-A155F_PixelOS-cheetah-A17_bakasu_A155FXXS7CYG4.tar
  size    12,222,085,120 B
  sha256  f0cc78c9ae26a4066ffd0bd0888e1d2be63673ca44828d658beeaedaedbe3662
  build   1348 s · rc=0 · VERDICT: clean · 20 stock members in stock order
```

Built from the one-file Colab runner against the pinned A17 donor
(`Pixel-cheetah-CinnamonBun-…`, G0 verified in-run) and the real
`A155FXXS7CYG4` firmware. Boot is **unmeasured** — nothing was flashed.

The agent's own sandbox cannot pull the 3.1 GB GSI or the 6.9 GB firmware (Drive
connector caps at 100 MB per file; shell egress is limited to a few hosts), so the
agent-side proof is the synthetic fixture below. Both paths exercise the same
code; the real run is the one that produced the artifact above.

## Latest measured run — synthetic fixture, real toolchain (agent side)

```
$ bash tools/mk_synthetic_inputs.sh /tmp/pixelinputs
$ INPUTS_DIR=/tmp/pixelinputs INPUTS_LOCK=/tmp/pixelinputs/inputs.lock.json \
    bash rom/gsi-build.sh                     # rc=0
...
AP TAR   : out/AP_SM-A155F_PixelOS-Demo-A17_bakasu_A155FXXS7CYG4.tar
size     : 138,690,560 bytes
sha256   : b49dbc0f4d96844c8dc66ea2ce011fdfdec5b8c0bab04e09fb2a37ecda799e44
members  : boot.img · super.img · vbmeta.img · vbmeta_system.img   (stock order)
audit    : VERDICT: clean
```

Two consecutive runs over the same fixture produce the **same** SHA-256
(`rom/pack-ap.sh` normalises mtime/uid/gid but never re-sorts the member list).
The fixture's contents are synthetic (`boot.img` is random bytes), so this hash
identifies *this* fixture only — it is a pipeline proof, not a ROM.

`python3 -m unittest discover -s tests` → **40 tests OK** (the 28 original
synthetic tests plus 12 for the G0 gate, the TAG parser and the AVB0/VNDRBOOT
classifiers).

## Quick start

```bash
bash rom/tools.sh                        # lpmake/lpunpack/lpdumps, lz4, e2fsprogs, avbtool (no apt)
python3 -m unittest discover -s tests    # 40 OK
```

Synthetic end-to-end (never touches the real GSI/firmware, ~10 s):

```bash
bash tools/mk_synthetic_inputs.sh /tmp/pixelinputs
INPUTS_DIR=/tmp/pixelinputs INPUTS_LOCK=/tmp/pixelinputs/inputs.lock.json \
  bash rom/gsi-build.sh
```

Real build, in Colab with Drive mounted:

```bash
from google.colab import drive; drive.mount('/content/drive')
```
```bash
INPUTS_DIR=/content/drive/MyDrive/PixelOSA155F KERNEL_VARIANT=bakasu ROM_NAME=PixelOS \
  bash rom/gsi-build.sh 2>&1 | tee build.log
```

or the single file (unpacks its own sources, runs the tests, builds, audits):

```bash
bash /content/drive/MyDrive/PixelOSA155F/PixelOSA155F-colab.sh
```

The single file is `colab_build.sh` + a base64 zip of the sources; regenerate it
after any repo change and upload just that one file to Drive:

```bash
bash tools/make_single_file.sh                 # -> PixelOSA155F-colab.sh
```

It is validated end-to-end the same way as the pipeline: unpack into an empty
`WORKDIR`, run the 39 tests, build the synthetic fixture, audit it. Measured:
`rc=0`, `VERDICT: clean`, sha256
`b49dbc0f4d96844c8dc66ea2ce011fdfdec5b8c0bab04e09fb2a37ecda799e44` — the same
hash the in-repo run produced, from a different working directory. Pass
`INPUTS_LOCK` alongside `INPUTS_DIR` when pointing it at a fixture folder.

## Pinned inputs (G0)

`inputs/inputs.lock.json` is the single source of truth. The donor that is
actually in the owner's Drive folder today:

| Input | Size (B) | MD5 | Note |
|---|---|---|---|
| `Pixel-cheetah-CinnamonBun-14911996-AB-20260227-MysticGSI.zip` | 3,148,371,077 | `81f41e26c9991743674455520db0a61a` | **Android 17**, arm64 AB, Pixel (cheetah) family |
| `bakasu_35262_susfs_v2.4.0_A155FXXS7CYG4_A15_GKI.tar` | 67,112,960 | `39800312d85035ff2c8f94bdf5f38054` | default kernel, `boot.img` only |
| `kernelsunext_33548_susfs_v2.4.0_A155FXXS7CYG4_A15_GKI.tar` | 67,112,960 | `472a59d49fcc94c4a66ff4186210cd65` | alternative |
| `stock_optimized_5.10.226_A155FXXS7CYG4_A15_GKI.tar` | 67,112,960 | `161fe2dbb5cfc5420727fd7f89ed9342` | vanilla, no root |
| `SAMFW.COM_SM-A155F_XSG_A155FXXS7CYG4_fac.zip` | 6,904,157,493 | `bea1131d9bddabc5630411a982059b57` | vendor/odm/product + AP member order |

A pin is mandatory: unpinned, resized or re-hashed inputs abort the build
(`FATAL: … G0 gate not met`). Google Drive copy suffixes
(`… adlı dosyanın kopyası`, `… (1)`) are handled by matching the longest pinned
name that is a prefix of the real file name, so the Drive copy need not be
renamed.

### The version-ladder problem (read before flashing)

The donor in Drive is **Android 17** (`CinnamonBun`). The measured lesson from
2026-11-22 is the opposite direction: the NothingOS **A16** AP was accepted by
the bootloader and got past the Samsung logo, but the system UI never came up in
~15 minutes. The project rule is therefore *A15 (vendor-compatible) first, A16/A17
only with logcat evidence*.

`rom/gsi-inputs.sh` prints a loud `VERSION LADDER WARNING` and records the level
in `work/gsi/ANDROID_LEVEL` when the donor is above A15 instead of silently
pretending the risk is gone. A Pixel-family **A15** build was not present in the
RSS window inspected (Mar 2026 → Sep 2025 listed `Pixel-cheetah-CANARY` from Jul
2025 and the A17 `Pixel-raven`/`Pixel-cheetah` builds only; the generic A15
entries are LineageOS/ZenUI/FoxOS/VollaOS, not Pixel-family). Decision needed
from the owner — see `docs/GATES.md`.

## Layout

```
rom/      numbered build stages (tools, gsi-inputs, extract-ap, repack-super,
          make-vbmeta, pack-ap, gsi-build) + simfix/ + this line's README
tools/    gsi_inspect, super_inspect, odin_audit, odin_pack, tar_inspect,
          verify_inputs, pin_gate, gsi_tag, make_single_file, mk_synthetic_inputs
tests/    39 synthetic tests
docs/     GATES.md (gate status + decisions), EVIDENCE.md (measured facts),
          ROM_BUILD.md (stage reference), 20-FIRST-BUILD.md (runbook)
inputs/   inputs.lock.json (pins) + inputs.lock.example.json (template)
colab_build.sh / PixelOSA155F-colab.sh   one-file Colab runner
```

## Outputs

```
out/AP_SM-A155F_PixelOS-<TAG>_<kernel>_<FW_VERSION>.tar     plain TAR, flashed as-is
out/<same>.audit.txt                                         odin_audit verdict
out/dist/<APBASE>.SHA256SUMS.txt                             TAR + per-part hashes
out/dist/<APBASE>.tar.00/.01/…                               transport parts only (2 GB cap)
out/dist/<APBASE>.JOIN.txt                                   how to rejoin the parts
```

`<TAG>` comes from `tools/gsi_tag.py`: a plain integer token in 9..25 wins
(`Pixel-raven-17-…` → `raven-A17`), otherwise a codename is mapped
(`Pixel-cheetah-CinnamonBun-…` → `cheetah-A17`).

## Hard rules

* **No flashing by the agent.** The `SW REV CHECK FAIL [super] Fused 7 > Binary 8`
  contradiction (owner: binary 7 / `A155FXXS7CYG4`) is unresolved, so no flash
  advice either.
* No distribution of proprietary code, blobs, apps or keys; no attestation bypass.
* No unverified compatibility claims for NoMount/HybridMount, YukiZygisk,
  ZygiskNext or VectorLSP; camera/flash behaviour is the owner's single report.
* Artifacts are additive: nothing is deleted, overwritten or renamed in place.
* No evidence ⇒ no "it boots". Until a device logcat exists, boot is **unmeasured**.
