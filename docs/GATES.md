# Gates — what must be true before an artifact counts

Every gate is mechanical. A gate either passes on bytes that are on disk, or the
build stops. "Looks fine" is not a gate result.

| # | Gate | Mechanism | Where it runs | Last measured result |
|---|---|---|---|---|
| G0 | every input is pinned by Drive id + exact size + MD5, and re-hashed | `tools/pin_gate.py` (per file), `tools/verify_inputs.py` (whole folder) | 2/8 | **PASS** — GSI Drive↔RSS MD5 match; kernel + firmware pins verified on the fixtures; negative controls refuse a 1 KiB impostor and an unpinned file |
| G1 | the stock AP member list **and order** are recorded and replayed | `rom/extract-ap.sh` → `work/ap/members.txt`; `rom/pack-ap.sh` re-uses it; `diff` against the produced TAR | 3/8, 7/8 | **real stock AP: 20 entries** (incl. `meta-data/`, `meta-data/fota.zip`, `userdata`, `recovery`, `*-verified.img`) replayed in order, `diff` clean |
| G2 | the new `super` is real liblp, still contains `vendor` + `odm` + `product`, and fits | `lpdump` → `lpunpack` → `rom/lp_plan.py` (per-group capacity check) → `lpmake`; `tools/super_inspect.py` re-parses the result | 5/8, 8/8 | **real super**: 9,434,177,656 B sparse / 11,744,051,200 B expanded; 6 partitions, `system` 6,233,522,176 from the GSI, stock `vendor`/`odm`/`product`/`system_ext`/`vendor_dlkm` unchanged |
| G3 | plain TAR, no MD5 footer, no LZ4 member, stock order, `vbmeta*` built with `--flags 3` | `rom/pack-ap.sh` checks; `tar -tf` diff; `tools/odin_audit.py` | 6/8, 7/8, 8/8 | **real artifact**: 12,222,085,120 B plain TAR, `md5 footer: False`, zero `.lz4` members, 19 files + 1 stock dir entry |
| G4 | `odin_audit.py` verdict | exit 0 clean / 1 warnings / 2 critical; `rom/gsi-build.sh` exits 2 on critical | 8/8 | **real artifact: `VERDICT: clean`, rc=0** — sha256 `f0cc78c9…3662` |

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

## Where each gate was measured

The real run happened in Colab on 2026-11-22 (one-file runner, 1348 s, real GSI +
real firmware) and produced
`AP_SM-A155F_PixelOS-cheetah-A17_bakasu_A155FXXS7CYG4.tar`
(12,222,085,120 B, sha256 `f0cc78c9ae26a4066ffd0bd0888e1d2be63673ca44828d658beeaedaedbe3662`,
`VERDICT: clean`). The synthetic fixture remains the agent-side proof, because the
agent's sandbox cannot move those bytes:

* the Google Drive connector caps a download at 100 MB,
* shell egress is limited to `github.com`, `api.github.com`, `pypi.org`,
  `registry.npmjs.org`,
* `drive.google.com` and `sourceforge.net` TLS-connect fails from the shell
  (`SSL_ERROR_SYSCALL`), which is why the RSS MD5 was read through the page
  fetch path.

Both paths run the same code; the gates above are quoted from the real run where
it exists.

## Open decisions (owner)

1. **Version ladder.** The only donor in Drive is Android **17**. The measured
   rule for this device is A15 first (the A16 NothingOS AP passed the bootloader
   and the Samsung logo, then never brought up the system UI). Options:
   (a) accept the A17 risk deliberately, (b) provide a Pixel-family **A15** GSI
   and pin it, (c) supply a device logcat from an A16/A17 attempt so the ladder
   has evidence.
2. **userdata.** The real artifact contains the stock `userdata.img`
   (1,418,011,288 B sparse / 17,179,869,184 B expanded), so flashing it wipes
   user data. Keep it (clean install) or drop it from the AP (keep data)? The
   pipeline currently preserves the stock member; excluding it is a one-line
   change in `rom/pack-ap.sh` if the owner chooses "keep data".
3. **Repository target.** This branch (`arena/802af16c-pixelosa155f`) is the
   working branch; confirm `PixelOSA155F` `main` is where it should land.
