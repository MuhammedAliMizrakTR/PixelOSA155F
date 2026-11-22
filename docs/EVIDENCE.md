# Evidence log — measured facts only

Rule of this file: a number is either backed by a command whose output is quoted,
or it is marked **unmeasured**. Nothing here is inferred from "should work".

## Device

| Item | Value | How it is known |
|---|---|---|
| Model | SM-A155F, Galaxy A15 4G | owner |
| SoC | MediaTek MT6789 / Helio G99 | owner |
| Kernel | GKI Linux 5.10.226 | kernel tars + stock firmware |
| Firmware | `A155FXXS7CYG4`, region XSG, build `MQB99305356`, OS15, `REV00` | stock AP member name |
| Binary / fused revision | owner reports `Binary 7`; Odin reports `Fused 7 > Binary 8` on `super` | **unresolved contradiction — no flash advice** |

## Stock image geometry (owner's `lpdumps`, stored in Drive)

```
super device size : 11,744,051,200 B
super used size   :  9,354,960,896 B   (prompt quotes the raw super as 9,352,091,512 B)
group main max    : 11,739,856,896 B
partitions        : system 5,769,207,808 · product 1,837,219,840 · vendor 1,184,497,664
                    system_ext 525,639,680 · vendor_dlkm 36,745,216 · odm 1,650,688
```

`rom/lp_plan.py` reads the *real* super at stage 5/8 and fails loudly if the GSI
does not fit; the numbers above are documentation, not build input.

## Stock AP member order (the Odin contract)

```
boot.img.lz4        21,020,551
vendor_boot.img.lz4  8,580,297
dtbo.img.lz4            98,045
super.img.lz4    5,865,008,566
vbmeta.img.lz4           3,515
vbmeta_system.img.lz4    2,819
```

The real stock AP additionally carries `recovery` / `userdata` / `misc` /
`meta-data/` (a literal directory entry, which `odin_audit.py` reports as a NOTE,
not a warning) / `fota.zip` and `*-verified.img` members. Their position is
preserved because `pack-ap.sh` walks `work/ap/members.txt` in order.

The firmware zip itself (`a155f-contents.txt` in Drive) contains:

```
8,341,575,802  AP_A155FXXS7CYG4_A155FXXS7CYG4_MQB99305356_REV00_user_low_ship_MULTI_CERT_meta_OS15.tar.md5
    6,062,192  BL_A155FXXS7CYG4_..._MULTI_CERT.tar.md5
   33,546,349  CP_A155FXXS7CYG4_CP31150071_..._MULTI_CERT.tar.md5
  120,996,024  CSC_OJM_A155FOJM7CYG4_..._MULTI_CERT.tar.md5
  120,975,549  HOME_CSC_OJM_...MULTI_CERT.tar.md5
          719  _FirmwareInfo_Samfw.com.txt
```

## Real PixelOS run (2026-11-22, owner's Colab, one-file runner)

First real artifact of this line. Every gate ran on the real bytes.

```
AP_SM-A155F_PixelOS-cheetah-A17_bakasu_A155FXXS7CYG4.tar
  size      12,222,085,120 B
  sha256    f0cc78c9ae26a4066ffd0bd0888e1d2be63673ca44828d658beeaedaedbe3662
  build     1348 s, rc=0, VERDICT: clean
  members   19 files + the stock `meta-data/` directory entry, stock order
  donor     Pixel-cheetah-CinnamonBun-… (A17), G0 MD5 verified in-run
  firmware  SAMFW.COM_SM-A155F_XSG_A155FXXS7CYG4_fac.zip, G0 MD5 verified in-run
  kernel    bakasu_35262_… (boot.img 67,108,864 B)
```

Gate evidence from the run itself:

| Gate | Observed |
|---|---|
| G0 | GSI `81f41e26…a61a` (3,148,371,077 B), kernel `39800312…8054`, firmware `bea1131d…9b57` — all `G0 gate: ok` |
| G1 | 20 stock AP entries captured, including `recovery`, `userdata`, `misc.bin`, the `*-verified.img` set, `meta-data/` and `meta-data/fota.zip` |
| G2 | stock super 11,744,051,200 B → 6 partitions unpacked; new super 9,434,177,656 B sparse (11,744,051,200 B expanded), `main` group cap 11,739,856,896 B |
| G3 | plain TAR, `md5 footer: False`, no `.lz4` member, `vbmeta*` 256 B each (`--flags 3`) |
| G4 | `VERDICT: clean`, rc=0 |

Super layout, stock vs rebuilt (bytes):

```
              stock            rebuilt (GSI as system)
system        5,769,207,808    6,233,522,176   (+464,314,368 from the donor)
product       1,837,219,840    1,837,219,840   unchanged
vendor        1,184,497,664    1,184,497,664   unchanged
system_ext      525,639,680      525,639,680   unchanged
vendor_dlkm      36,745,216       36,745,216   unchanged
odm               1,650,688        1,650,688   unchanged
```

The rebuilt system is 464 MB larger than stock. It still fits inside the stock
`main` group, so no partition geometry beyond `system` changed.

### Where the artifact lives, and how it was verified twice

| | |
|---|---|
| Drive | `PixelOSA155F/out/AP_SM-A155F_PixelOS-cheetah-A17_bakasu_A155FXXS7CYG4.tar` (file id `1CGzMSnBOnIfj3xTVpR1uwxz0pndE4aJT`) |
| Size | 12,222,085,120 B (matches the local file byte for byte) |
| sha256 (local) | `f0cc78c9ae26a4066ffd0bd0888e1d2be63673ca44828d658beeaedaedbe3662` |
| sha256 (re-read from the Drive mount) | `f0cc78c9ae26a4066ffd0bd0888e1d2be63673ca44828d658beeaedaedbe3662` → **match** |
| MD5 (computed by Google Drive itself) | `246716fc6e2a4b3b3d3bfc316d2b99dd` — a second, independent fingerprint |
| Audit copy | `.audit.txt`, 1,944 B, re-read from Drive: `VERDICT: clean` |

Copy took ~92 s at ~120-180 MiB/s; Drive had 60.99 GiB free, so the 12.2 GB TAR
fits without splitting. If Drive ever runs short, the rescue cell splits it into
1,900 MB transport parts instead and prints per-part download lines.

### Three things this run proved that matter for flashing

1. **`userdata.img` is in the package** — stock member, 1,418,011,288 B sparse
   (17,179,869,184 B = 16 GiB expanded). Flashing this AP as-is overwrites the
   userdata partition: **data loss**. `EXCLUDE_USERDATA=1` now drops that member
   (verified: default AP carries `userdata.img`, flagged AP does not, audit still
   `clean`, super untouched).
2. **The artifact is ~3.9 GB larger than the stock AP** (12.22 GB vs 8.34 GB)
   because `super.img` is raw sparse (9.43 GB) instead of LZ4 (5.87 GB) and
   `userdata.img`/`recovery.img` are decompressed. That is the cost of the
   "no LZ4 members" rule, not a mistake.
3. **Two audit labels were wrong, not the members**: `vendor_boot.img` and
   `vbmeta*.img` printed `container=unknown`. Both magics (`VNDRBOOT`, `AVB0`)
   are now classified by `tools/gsi_inspect.py`, so later audits say
   `android-vendor-boot` / `avb-vbmeta` instead of looking suspicious.

## Prior build on this device (NothingOS line, 2026-11-22)

```
AP_SM-A155F_NothingOS-Asteroids-A16_bakasu_A155FXXS7CYG4.tar
  size   10,904,903,680 B
  sha256 a141847c93d9b144f78012983f4bcd195241bb4451fd4fa6b36471f9f2329b34
  parts  .tar.00 … .tar.05 (1,900 MiB transport chunks)
```

Result: the bootloader **accepted** the package and the device passed the
Samsung logo, but the system UI never appeared within ~15 minutes. Packaging is
accepted by the hardware; that ROM did not work. This is the only real flash
evidence in the project, and it is a *negative* result.

## Donor selection — what is actually listed

SourceForge project *Mystic GSI Updates*, `/Generic`, RSS read 2026-11-22
(6 chunks; the Mar-2026 → Sep-2025 window was inspected):

| Candidate | Kind | MD5 (RSS) |
|---|---|---|
| `Pixel-cheetah-CinnamonBun-14911996-AB-20260227-MysticGSI.zip` | Pixel family, **A17**, in owner's Drive | `81f41e26c9991743674455520db0a61a` |
| `Pixel-raven-CinnamonBun-14876943-AB-20260213-MysticGSI.zip` | Pixel family, A17 | `4272ac5353962a1dcac3861909c962cd` |
| `Pixel-raven-17-15063635-AB-20260327-MysticGSI.zip` | Pixel family, A17 (newest) | `86b3617df4ebae5ae42041659ebc19c0` |
| `Pixel-cheetah-CANARY-13734781-AB-20250710-MysticGSI.zip` | Pixel family, pre-A16 canary | `4e8dfbfd9ee6fa16c7ab2a42ba6cddb1` |
| `Lineageos-nx-15-…`, `Zenui-ASUS_AI2302-15-…`, `Foxos-…-15-…`, `Vollaos-algiz-15-…`, `Aosp-zahedan-15-…` | **A15**, not Pixel-family | various |

No Pixel-family **A15 or A16** build appeared in the inspected window, so the
"A15 first" rule cannot be satisfied from the listing without an owner decision.
No file named `*PixelOS*` exists in that project; "Pixel family / PixelOS-look" is
the closest available donor class.

## What the pipeline itself proved (synthetic fixture, real tools)

```
$ bash tools/mk_synthetic_inputs.sh /tmp/pixelinputs
$ INPUTS_DIR=/tmp/pixelinputs INPUTS_LOCK=/tmp/pixelinputs/inputs.lock.json bash rom/gsi-build.sh
1/8 toolchain OK (lpmake 15.0.0_r25, lz4 1.11.2, e2fsprogs 1.47.4, avbtool)
2/8 G0 gates OK for GSI + kernel + firmware
3/8 stock AP members parsed in order
5/8 sparse super → raw → lpdump → lpunpack → lpmake (GSI as system)
6/8 vbmeta.img + vbmeta_system.img (--flags 3, 256 B each)
7/8 plain TAR, 138,690,560 B
8/8 VERDICT: clean                       rc=0
```

Reproducibility: two consecutive runs, same fixture, same
`sha256 b49dbc0f4d96844c8dc66ea2ce011fdfdec5b8c0bab04e09fb2a37ecda799e44`.
Before the `--mtime/--owner/--group` normalisation in `pack-ap.sh`, each run
hashed differently (observed: `d512b17c…`, then `c9aaead5…`).

## Unmeasured

* Boot of the real PixelOS artifact on this device — **nothing has been flashed**;
  the package exists and audits clean, that is all.
* Whether an A17 system works with the A15 (A155FXXS7CYG4) vendor/odm — unknown;
  the A16 attempt suggests it does not.
* Camera/flash/RIL behaviour with the PixelOS donor — unknown (the RIL-fix module
  addresses the ~7h25m ril-daemon hang reported for the unlocked bootloader on
  this device; that is the owner's single report, not a measurement here).
* NoMount/HybridMount, YukiZygisk, ZygiskNext, VectorLSP compatibility — not
  tested, not claimed.
