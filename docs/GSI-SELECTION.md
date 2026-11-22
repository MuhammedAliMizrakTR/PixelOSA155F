# Which GSI to put in `system` — and why the phone looked "cursed"

Status: research document. It answers the owner's two questions after the first
successful boot (2026-11-22):

1. *"The system says CinnamonBun but the easter egg is Android 16, and there is
   no PHH TrebleDroid app at all — what did I actually flash?"*
2. *"Then find me a proper Google Pixel OS / proper Android 17 GSI."*

No claim in here is a bootability claim for SM-A155F. Only the build that is
already on the phone has boot evidence (the owner's own report). Everything
else is *unmeasured* on this device.

---

## 1. What is actually on the phone

The flashed donor zip is a **Mystic GSI port of a Google Pixel 7 Pro (cheetah)
factory image**, not a Google GSI release and not a TrebleDroid/PHH build.
Upstream identifiers, as published by the porter:

| Field | Value |
|---|---|
| Zip | `Pixel-cheetah-CinnamonBun-14911996-AB-20260227-MysticGSI.zip` (~3.1 GB) |
| Build fingerprint | `google/cheetah_beta/cheetah:CinnamonBun/CP21.260206.011.A1/14911996:user/release-keys` |
| Build id | `CP21.260206.011.A1` |
| Release codename | `CinnamonBun` (the Android 17 codename) |
| `ro.build.version.sdk` | **36** |
| Security patch | 2025-12-05 |
| Raw `system` size | 5.80 GiB |

Two consequences, both expected and neither a defect of our packaging:

* **"CinnamonBun" with an Android 16 easter egg.** `CP21.*` is Google's *Android
  17 Beta 2* build id, and Beta 2 still advertises **SDK 36** — the SDK number
  ("36" = the Android 16 API level) is what the framework, the Easter egg asset
  and most apps key off. So the release *codename* reads CinnamonBun while the
  *platform level* is 36. That is exactly the state a beta is in; `CinnamonBun`
  only becomes SDK 37 in later builds. The leak of that mismatch into the UI is
  the porter's repack, not something `rom/` did.
* **No PHH TrebleDroid app.** The TrebleDroid settings app
  (`me.phh.treble.app`) ships only in builds made from **phhusson's /
  TrebleDroid's device trees** — i.e. AOSP + phh patches. A ported Pixel factory
  dump is a different lineage: it has no treble app, no `phh` props, and no
  TrebleDroid hook points. Its absence says nothing about the flash.

Verify on the device (read-only):

```bash
adb shell getprop ro.build.fingerprint
adb shell getprop ro.build.version.sdk          # expect 36
adb shell getprop ro.build.version.codename     # expect REL (beta reports REL)
adb shell getprop ro.build.id                   # expect CP21.260206.011.A1
adb shell pm list packages | grep -i phh        # empty == no TrebleDroid build
bash tools/device_state.sh                      # our own baseline collector
```

---

## 2. What "proper" means — three different things

| Lineage | Who makes it | What you get | Builds the TrebleDroid app? |
|---|---|---|---|
| **Google GSI** (`gsi_gms_arm64-*` / `aosp_arm64-*`) | Google, per-quarter, on `dl.google.com` | The reference GSI; the `_gms_` variant is a stock-Pixel-like image with GMS | No |
| **PixelOS GSI** | mytja, Doze-off | PixelOS (Pixel launcher/fonts/features) rebuilt for Treble | No (Doze-off builds carry phh patches, the mytja tree is PixelOS) |
| **AOSP + phh patches** | phhusson → TrebleDroid; ponces; Doze-off, cawilliamson | AOSP with the compatibility shims **and** `me.phh.treble.app` | **Yes** — this is the only lineage that ships it |
| *Porter repacks* | Mystic, Erfan, Nippon-style | Somebody's phone factory image re-cut as a GSI | No, and OEM leftovers included |

So: "PixelOS" ≠ "has the TrebleDroid app", and "has a Pixel fingerprint" ≠
"Google GSI". The three are independent.

---

## 3. Candidates, ranked for SM-A155F (stock A15 vendor, GKI 5.10.226)

All links are from the TrebleDroid GSI list (wiki last edited 2026-11-21).

### Android 17

| Image | Build | Updated | Level | Notes |
|---|---|---|---|---|
| **Google GSI (GMS), QPR3 Beta** | `gsi_gms_arm64-exp-DP11.260918.006-16451184` | 2026-09-02 | A17 beta | Closest thing to a *stock Pixel* GSI; `_gms_` = GMS included (`aosp_arm64-exp-DP11.260918.006` = no GMS). Beta = expect rough edges |
| Google GSI (GMS), QPR1 | `gsi_gms_arm64-exp-CP3A.260905.010` | 2026-09-17 | A17 | More conservative than the DP |
| **BestGSI** | `17QPR0` (`amintum/BestGSI`) | 2026-11-21 | A17 | Freshest, Oct 2026 security |
| **Infinity X** | `2026-11-20` (`Doze-off/ProjectInfinity-X_gsi`) | 2026-11-20 | A17 | Nov 2026 security; Doze-off = phh patches |
| RestlessOS QPR0 | `cawilliamson/treble_restlessos` | 2026-11-02 | A17 | Mirror `build.chrisaw.io` |
| LineageOS 24.0 (unofficial) | `lineage-24.0-20261107-UNOFFICIAL-gsi_arm64` (AndyYan, SourceForge `andyyan-gsi`) | 2026-11-07 | A17 | Plain Lineage |
| LineageOS 24.0 / Veliqen OS (Aizner) | `eyzner/LineageOS-GSI`, `eyzner/VELIQEN-OS` | 2026-11-04 / 17 | A17 | Mirrors are Yandex — slow from TR |

### Android 16 (the *safe* rung: matches the vendor's own level)

| Image | Build | Updated | Notes |
|---|---|---|---|
| **Google GSI, QPR3** | `gsi_gms_arm64-exp-CP11.251209.007.A1` / `aosp_…` | 2026-01-14 | Stable-quarter Google image, SDK 36 like the current donor but a *finished* build |
| **PixelOS by mytja** | `mytja/treble_pixelos` tag `20250806` | 2026-08-06 | Real PixelOS for Treble, ARM64 |
| **PixelOS (Doze-off)** | `Doze-off/PixelOS_GSI_treble` | 2026-05-02 | PixelOS + phh patch layer |
| **ponces AOSP** | `ponces/treble_aosp` tag `v2025.06.25` | 2026-06-26 | AOSP+phh: **this one has the TrebleDroid app** |
| TrebleDroid AOSP | `TrebleDroid/treble_experimentations` `ci-20250617` | 2025-06-17 | Upstream reference build |
| MindOS / BestGSI 20261024 / Infinity X 20260920 / DerpFest / AxionOS / crDroid / Evolution X / Lunaris / WitAqua / MistOS | see wiki | 2026 | Alternatives if the above misbehave |

### What is *not* available
There is **no PixelOS A17 GSI** (neither mytja nor Doze-off) as of 2026-11-22,
and no PHH-lineage A17 from phhusson himself (his tree is archived; ponces and
Doze-off carry it). An "Android 17 PixelOS" on Telegram is a repack until it is
listed with sources.

---

## 4. Compatibility rules that actually decide success

From the same wiki, plus what we already measured on this device:

1. **GSI API ≥ the device's shipped API.** A155F shipped Android 15 (API 35);
   every A16/A17 image above satisfies it. Going *up* is allowed, going down is not.
2. **System-as-root / dynamic partitions, arm64.** SM-A155F takes `arm64_bvN`
   (A/B, GApps variant); our pipeline only consumes `system` and rebuilds the
   rest from stock, so `bvN` naming is fine.
3. **VNDKLite only if the device says so.** Check the "Required Image" line in
   Treble Info; do not guess. Nothing in our build assumes VNDKLite.
4. **Samsung AVB.** Already handled: `rom/make-vbmeta.sh` writes the 256-byte
   `vbmeta.img` with `--flags 3` (disable verification + verity). No BL unlock
   beyond what the owner already did, no attestation bypass.
5. **Donor hygiene.** Prefer a release with a source tree and a build id that
   matches the upstream project; prefer a *finished* quarter over a beta when
   the previous attempt left confusion.

---

## 5. Building with a different donor (no code changes needed)

`rom/gsi-inputs.sh` accepts any donor now:

* auto-detect falls back from `*-MysticGSI.zip*` to any zip that really contains a
  `system.img*` member (name guesses are never trusted);
* `system.img.gz` / `.xz` / `.lz4` members are decompressed once automatically;
* level/TAG can be stated explicitly when the file name carries no codename.

Colab cell (one paste, then edit these three lines at the top):

```python
ROM_NAME = "PixelGSI"       # appears in the AP name
# and in the cell's os.environ before the build:
import os
os.environ["GSI_ZIP"]  = "/content/drive/MyDrive/PixelOSA155F/gsi_gms_arm64-exp-DP11.260918.006-16451184-8f0c1d2e.zip"
os.environ["GSI_TAG"]  = "google-A17"   # no codename in the file name -> say it
os.environ["GSI_LEVEL"]= "17"
```

Resulting name: `AP_SM-A155F_PixelGSI-google-A17_bakasu_<PDA>.tar` — Gate G0 still
pins the donor by size+MD5, so a truncated Drive download stops at stage 2.

Synthetic proof of this path (Google-style name + `system.img.gz`, nothing else
changed):

```
=== GSI: gsi_gms_arm64-exp-DP11.260918.006-16451184-028aa375.zip
system.img.gz found -> decompressing
TAG: google-A17 (Android level: 17)
Plain AP TAR: out/AP_SM-A155F_PixelGSI-google-A17_bakasu_A155FXXS7CYG4.tar (138690560 bytes)
VERDICT: clean
```

---

## 6. Recommendation, stated honestly

* **If the goal is "this looks like a real Pixel" with the least drama:**
  Google GSI **A16 QPR3 GMS** (`CP11.251209.007.A1`). It is a finished quarter,
  same API level as the vendor, and it is Google's own image — the identity
  strings then match the level, so no "CinnamonBun/16" confusion can reappear.
* **If the goal is specifically Android 17:** Google GSI **A17 QPR1**
  (`CP3A.260905.010`) or **BestGSI 17QPR0**; the DP3 beta is the riskiest of the
  three because it is a developer preview.
* **If the goal is PixelOS:** `mytja/treble_pixelos` (A16, Aug 2026) or
  `Doze-off/PixelOS_GSI_treble` (A16, May 2026). A17 PixelOS does not exist yet.
* **If the goal is the TrebleDroid app back:** `ponces/treble_aosp`
  `v2025.06.25` — AOSP+phh, A16.

Each of these is **one unmeasured attempt** on A155F. Keep the stock AP and the
CSC from `SAMFW.COM_SM-A155F_XSG_A155FXXS7CYG4_fac.zip` at hand, because the
recovery path that already worked once is the stock AP alone (no BL, no CSC).
