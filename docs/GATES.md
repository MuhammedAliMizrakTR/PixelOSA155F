# Gates — what must be true before an artifact counts

Every gate is mechanical. A gate either passes on bytes that are on disk, or the
build stops. "Looks fine" is not a gate result.

| # | Gate | Mechanism | Where it runs | Last measured result |
|---|---|---|---|---|
| G0 | every input is pinned by Drive id + exact size + MD5, and re-hashed | `tools/pin_gate.py` (per file), `tools/verify_inputs.py` (whole folder) | 2/8 | **PASS** — GSI Drive↔RSS MD5 match; kernel + firmware pins verified on the fixtures; negative controls refuse a 1 KiB impostor and an unpinned file |
| G1 | the stock AP member list **and order** are recorded and replayed | `rom/extract-ap.sh` → `work/ap/members.txt`; `rom/pack-ap.sh` re-uses it; `diff` against the produced TAR | 3/8, 7/8 | synthetic fixture: order preserved exactly (`boot.img`, `super.img`, `vbmeta.img`, `vbmeta_system.img`) |
| G2 | the new `super` is real liblp, still contains `vendor` + `odm` + `product`, and fits | `lpdump` → `lpunpack` → `rom/lp_plan.py` (per-group capacity check) → `lpmake`; `tools/super_inspect.py` re-parses the result | 5/8, 8/8 | synthetic fixture: liblp with `system, vendor, odm, product`; audit re-parses the sparse super inside the TAR |
| G3 | plain TAR, no MD5 footer, no LZ4 member, stock order, `vbmeta*` built with `--flags 3` | `rom/pack-ap.sh` checks; `tar -tf` diff; `tools/odin_audit.py` | 6/8, 7/8, 8/8 | synthetic fixture: `plain tar: True`, `md5 footer: False`, zero `.lz4` members |
| G4 | `odin_audit.py` verdict | exit 0 clean / 1 warnings / 2 critical; `rom/gsi-build.sh` exits 2 on critical | 8/8 | `VERDICT: clean`, rc=0 |

Warnings are allowed only with a written reason in the release notes. A critical
verdict means the artifact is not flashed and the finding is reported instead.

## G0 evidence (2026-11-22)

```
Pixel-cheetah-CinnamonBun-14911996-AB-20260227-MysticGSI.zip
  Drive : 3,148,371,077 B   81f41e26c9991743674455520db0a61a
  RSS   :                    81f41e26c9991743674455520db0a61a   -> MATCH
SAMFW.COM_SM-A155F_XSG_A155FXXS7CYG4_fac.zip
  Drive : 6,904,157,493 B   bea1131d9bddabc5630411a982059b57   (3 independent copies, same hash)
bakasu_35262_susfs_v2.4.0_A155FXXS7CYG4_A15_GKI.tar
  Drive : 67,112,960 B      39800312d85035ff2c8f94bdf5f38054
```

Negative controls actually executed:

```
$ python3 tools/pin_gate.py --lock inputs/inputs.lock.json --role donor-gsi-primary \
    --file '/tmp/g0neg/Pixel-cheetah-CinnamonBun-...-MysticGSI.zip'   # 1 KiB of zeros
FATAL: size mismatch ...: file 1024 != pinned 3148371077              rc=1
$ python3 tools/pin_gate.py --lock inputs/inputs.lock.json --role donor-gsi-primary \
    --file /tmp/g0neg/other.zip
FATAL: 'other.zip' is not pinned in the lock ...                      rc=1
```

## G4 output of the last measured run

```
archive  : out/AP_SM-A155F_PixelOS-Demo-A17_bakasu_A155FXXS7CYG4.tar (138690560 bytes)
sha256   : b49dbc0f4d96844c8dc66ea2ce011fdfdec5b8c0bab04e09fb2a37ecda799e44
plain tar: True   md5 footer: False
members  :
  - boot.img             raw=    134217728 expanded=134217728 container=android-boot
  - super.img            raw=      4464748 expanded=100663296 container=android-sparse
      liblp=liblp partitions: system(4194304), vendor(3145728), odm(2097152), product(2097152)
  - vbmeta.img           raw=          256 expanded=256 container=unknown
  - vbmeta_system.img    raw=          256 expanded=256 container=unknown
VERDICT: clean
```

Fixture contents are synthetic, so the hash identifies that fixture, not a ROM.

## Blocked here, not blocked in Colab

The real run needs 3.1 GB (GSI) + 6.9 GB (firmware) + 3×64 MB (kernels) of Drive
traffic. In this sandbox:

* the Google Drive connector caps a download at 100 MB,
* shell egress is limited to `github.com`, `api.github.com`, `pypi.org`,
  `registry.npmjs.org`,
* `drive.google.com` and `sourceforge.net` TLS-connect fails from the shell
  (`SSL_ERROR_SYSCALL`), which is why the RSS MD5 was read through the page
  fetch path.

So G1–G4 are proven on the synthetic fixture with the *real* lpmake/avbtool/tar
toolchain, and the real run is a one-command Colab job. Not a shortcut: the
gates are the same code.

## Open decisions (owner)

1. **Version ladder.** The only donor in Drive is Android **17**. The measured
   rule for this device is A15 first (the A16 NothingOS AP passed the bootloader
   and the Samsung logo, then never brought up the system UI). Options:
   (a) accept the A17 risk deliberately, (b) provide a Pixel-family **A15** GSI
   and pin it, (c) supply a device logcat from an A16/A17 attempt so the ladder
   has evidence.
2. **userdata.** Keep the stock `userdata.img` member in the AP (preserved, no
   wipe) or drop it from the package? The pipeline currently preserves it.
3. **Repository target.** This branch (`arena/802af16c-pixelosa155f`) is the
   working branch; confirm `PixelOSA155F` `main` is where it should land.
