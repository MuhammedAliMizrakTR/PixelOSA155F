# =============================================================================
#  Infinity X 4.2  (Android 17, GAPPS)  ->  3 x Odin AP TAR for SM-A155F
#  kernels:  bakasu | kernelsunext | stock (vanilla)
#
#  TEK HÜCRE. Yaptığı her şey, sırayla:
#    1. Google Drive'ı bağlar (zaten bağlıysa dokunmaz)
#    2. Infinity X GAPPS imajını GitHub release'inden /content'e indirir
#       (yarıda kalırsa kaldığı yerden devam eder) ve sha256'sını doğrular
#    3. Aynı dosyayı Drive'daki PixelOSA155F klasörüne kopyalar, kopyayı
#       yeniden hash'leyerek doğrular
#    4. Repoyu çeker, araç zincirini kurar, testleri koşar
#    5. Her kernel için ayrı pin dosyası (G0) yazıp build'i başlatır
#    6. Her AP'yi + audit'i + manifestleri Drive'a bırakır, Drive kopyasını
#       yeniden hash'leyerek doğrular, yerel kopyayı siler
#    7. En son SUMMARY-infinityx-<UTC>.md yazar (tek tek sonuç + hash + süre)
#
#  Bir build patlarsa diğerleri devam eder; hata da özete yazılır.
#  Sekmeyi kapatma: Colab serbest katmanda sekme kapanınca oturum ölür.
# =============================================================================
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone

# ------------------------------------------------------------------ ayarlar --
REPO = "https://github.com/MuhammedAliMizrakTR/PixelOSA155F.git"
BRANCH = "arena/802af16c-pixelosa155f"

WORK = os.environ.get("WORK", "/content/PixelOSA155F")
DRIVE = os.environ.get("DRIVE", "/content/drive/MyDrive/PixelOSA155F")
DL_DIR = os.environ.get("DL_DIR", "/content/dl")

# Infinity X 4.2 | A17 QPR0 | GAPPS  (GitHub release 2026-11-20)
# size + sha256 are GitHub's own asset metadata, not a guess.
DONOR = {
    "name": "Infinity-X-4.2-GSI_treble_arm64-ab-GAPPS-Official-20261120.img.xz",
    "url": ("https://github.com/Doze-off/ProjectInfinity-X_gsi/releases/download/"
            "2026-11-20/Infinity-X-4.2-GSI_treble_arm64-ab-GAPPS-Official-20261120.img.xz"),
    "size": 1739656336,
    "sha256": "85eb62ed88dbe703587ce946d8b2d46bb67e214599694586b4b63e34bf88c6ef",
    "android_level": "17",
    "tag": "infinityx-A17",
    "source": "https://github.com/Doze-off/ProjectInfinity-X_gsi/releases/tag/2026-11-20",
}

ROM_NAME = os.environ.get("ROM_NAME", "InfinityX")
KERNELS = ["bakasu", "kernelsunext", "stock"]        # stock == "vanilla" kernel
EXCLUDE_USERDATA = os.environ.get("EXCLUDE_USERDATA", "1")   # 1 = veriyi koru
SKIP_GSI_EXTRAS = os.environ.get("SKIP_GSI_EXTRAS", "1")     # 1 = GSI'a dokunma
VERIFY_DRIVE_HASH = os.environ.get("VERIFY_DRIVE_HASH", "1") == "1"
GIB = 1024 ** 3
# Gerçek boyutlardan hesap: super 9.35 GB + parçalar 11.7 GB + TAR 12.2 GB.
# SPLIT_BYTES=0 olduğu için 7 x 1.9 GB'lık transport parçaları hiç üretilmez.
NEED_COLAB_GIB = 45          # her build öncesi /content'te gereken boş alan
NEED_DRIVE_GIB = 13          # her build öncesi Drive'da gereken boş alan
LOCAL_TEST = os.environ.get("LOCAL_TEST") == "1"
# Test/inspection hooks. Üretimde boş kalır: donor GitHub'dan iner, pinler
# repodaki inputs/inputs.lock.json'dan okunur.
if LOCAL_TEST:
    DONOR["name"] = os.environ.get("DONOR_NAME", DONOR["name"])
    DONOR["size"] = int(os.environ.get("DONOR_SIZE", DONOR["size"]))
    DONOR["sha256"] = os.environ.get("DONOR_SHA256", DONOR["sha256"])
    DONOR["url"] = os.environ.get("DONOR_URL", DONOR["url"])
DONOR_LOCAL = os.environ.get("DONOR_LOCAL", "")
REPO_LOCK = os.environ.get("REPO_LOCK", "")   # boşsa <WORK>/inputs/inputs.lock.json

LOG_PATH = None
FAILURES = []


# ------------------------------------------------------------------ yardımcı --
def now():
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def log(msg=""):
    line = str(msg)
    print(line, flush=True)
    if LOG_PATH:
        with open(LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")


def run(cmd, cwd=None, env=None, check=True, stream_prefix=""):
    """Komutu çalıştır, çıktısını canlı bas. shell=True YOK (tırnak kaçışı yok)."""
    log("+ " + " ".join(cmd))
    proc = subprocess.Popen(cmd, cwd=cwd, env=env, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, bufsize=1)
    tail = []
    for raw in proc.stdout:
        line = raw.rstrip("\n")
        log(stream_prefix + line)
        tail.append(line)
        if len(tail) > 400:
            tail.pop(0)
    rc = proc.wait()
    if rc != 0 and check:
        raise RuntimeError(f"komut düştü rc={rc}: {' '.join(cmd)}")
    return rc, "\n".join(tail)


def hash_file(path, algo="sha256", chunk=8 << 20, label=None):
    h = hashlib.new(algo)
    total = os.path.getsize(path)
    done = 0
    t0 = time.time()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
            done += len(block)
            if label and total and (done % (512 << 20) < chunk):
                pct = 100.0 * done / total
                mbps = (done / (1 << 20)) / max(time.time() - t0, 1e-6)
                print(f"\r  {label}: {pct:5.1f}%  {done/(1<<20):8.0f} MiB  "
                      f"({mbps:5.0f} MiB/s)", end="", flush=True)
    if label:
        print("", flush=True)
    return h.hexdigest()


def copy_with_progress(src, dst, label="kopya", chunk=8 << 20):
    total = os.path.getsize(src)
    done = 0
    t0 = time.time()
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    tmp = dst + ".part"
    with open(src, "rb") as fi, open(tmp, "wb") as fo:
        for block in iter(lambda: fi.read(chunk), b""):
            fo.write(block)
            done += len(block)
            if total and (done % (512 << 20) < chunk):
                pct = 100.0 * done / total
                mbps = (done / (1 << 20)) / max(time.time() - t0, 1e-6)
                print(f"\r  {label}: {pct:5.1f}%  {done/(1<<20):8.0f} MiB  "
                      f"({mbps:5.0f} MiB/s)", end="", flush=True)
        fo.flush()
        os.fsync(fo.fileno())
    shutil.move(tmp, dst)
    print("", flush=True)


def free_gib(path):
    try:
        return shutil.disk_usage(path).free / GIB
    except OSError:
        return -1.0


def unique(path):
    """Append-only: var olan bir Drive dosyasının üzerine asla yazma."""
    if not os.path.exists(path):
        return path
    stem, ext = os.path.splitext(path)
    stamp = now()
    for i in range(1, 100):
        cand = f"{stem}-{stamp}" + (f"-{i}" if i > 1 else "") + ext
        if not os.path.exists(cand):
            return cand
    raise RuntimeError(f"no free name for {path}")


# -------------------------------------------------------------------- adımlar --
def preflight():
    """Ortam kontrolü: eksik araç varsa build'e hiç başlamadan söyle."""
    log("\n=== 0/7 ön kontrol ===")
    missing = [t for t in ("curl", "git", "tar", "xz") if shutil.which(t) is None]
    if missing:
        raise RuntimeError(f"eksik araç(lar): {', '.join(missing)} "
                           "(Colab'da: apt-get -y install xz-utils curl git)")
    log("curl / git / tar / xz: var")
    drive_free = free_gib(DRIVE)
    # AP başına ~10.8 GiB (EXCLUDE_USERDATA=1 userdata.img'yi çıkarır) + donor
    need = DONOR["size"] / GIB + 3 * 11.5
    if drive_free >= 0:
        log(f"Drive boş alan: {drive_free:.1f} GiB | 3 AP için gereken ~{need:.1f} GiB")
        if drive_free < need:
            log("UYARI: 3 AP sığmayabilir; sığmayan build 'Drive'da yer yok' diye "
                "atlanır ve özete yazılır (hiçbir şey silinmez).")


def mount_drive():
    log("\n=== 1/7 Google Drive ===")
    if LOCAL_TEST:
        log("LOCAL_TEST=1 -> mount atlandı")
        return
    from google.colab import drive  # Colab'da var
    if os.path.ismount("/content/drive"):
        log("Drive zaten bağlı")
    else:
        drive.mount("/content/drive")


def fetch_donor():
    log("\n=== 2/7 donor: Infinity X 4.2 GAPPS ===")
    os.makedirs(DL_DIR, exist_ok=True)
    local = os.path.join(DL_DIR, DONOR["name"])

    if DONOR_LOCAL:
        log(f"LOCAL_TEST: donor hazır dosyadan alınıyor: {DONOR_LOCAL}")
        if os.path.abspath(DONOR_LOCAL) != os.path.abspath(local):
            shutil.copyfile(DONOR_LOCAL, local)
    elif os.path.exists(local) and os.path.getsize(local) == DONOR["size"]:
        log(f"indirme zaten tamam: {local} ({DONOR['size']} B)")
    else:
        log(f"indiriliyor ({DONOR['size'] / GIB:.2f} GiB): {DONOR['url']}")
        rc, _ = run(["curl", "-L", "--fail", "--retry", "8", "--retry-delay", "5",
                     "-C", "-", "-o", local, DONOR["url"]], check=False)
        if rc != 0 and os.path.exists(local):
            # curl -C - 416 (zaten tam) durumunu da tolere et
            log(f"curl rc={rc}; dosya boyutu kontrol edilecek")
        if not os.path.exists(local):
            raise RuntimeError("donor indirilemedi (curl hata verdi, dosya yok)")

    size = os.path.getsize(local)
    if size != DONOR["size"]:
        raise RuntimeError(f"donor boyutu yanlış: {size} != {DONOR['size']} "
                           "(indirme eksik/bozuk, curl'ü tekrar çalıştır)")

    log("sha256 doğrulanıyor (GitHub asset digest)")
    got = hash_file(local, "sha256", label="sha256")
    if got != DONOR["sha256"]:
        raise RuntimeError(f"donor sha256 uyuşmuyor:\n  dosya : {got}\n  ilan  : {DONOR['sha256']}")
    log(f"sha256 OK: {got}")
    return local


def stage_donor_to_drive(local):
    log("\n=== 3/7 donoru Drive'a bırak ===")
    dst = os.path.join(DRIVE, DONOR["name"])
    if os.path.exists(dst) and os.path.getsize(dst) == DONOR["size"]:
        log(f"Drive'da zaten var: {dst}")
        md5 = hash_file(dst, "md5", label="md5(drive)")
        return dst, md5
    log(f"kopyalanıyor -> {dst}   (Drive boş: {free_gib(DRIVE):.1f} GiB)")
    if free_gib(DRIVE) >= 0 and free_gib(DRIVE) < DONOR["size"] / GIB + 1:
        raise RuntimeError(f"Drive'da yer yok: {free_gib(DRIVE):.1f} GiB "
                           f"(gerekli {(DONOR['size'] / GIB) + 1:.1f} GiB)")
    dst = unique(dst)
    copy_with_progress(local, dst, label="donor -> Drive")
    if os.path.getsize(dst) != DONOR["size"]:
        raise RuntimeError("Drive kopyasının boyutu tutmuyor")
    md5 = hash_file(dst, "md5", label="md5(drive)")
    if hash_file(local, "md5") != md5:
        raise RuntimeError("Drive kopyası kaynakla aynı değil (copy bozuk)")
    log(f"Drive kopyası doğrulandı: md5={md5}")
    return dst, md5


def prepare_repo():
    log("\n=== 4/7 repo + araç zinciri + testler ===")
    if LOCAL_TEST and os.path.isdir(os.path.join(WORK, ".git")):
        log(f"LOCAL_TEST: mevcut çalışma kopyası kullanılıyor: {WORK}")
    elif not os.path.isdir(os.path.join(WORK, ".git")):
        shutil.rmtree(WORK, ignore_errors=True)
        run(["git", "clone", "--branch", BRANCH, "--depth", "1", REPO, WORK])
    else:
        run(["git", "-C", WORK, "fetch", "--depth", "1", "origin", BRANCH])
        run(["git", "-C", WORK, "reset", "--hard", "FETCH_HEAD"])
    head = subprocess.run(["git", "-C", WORK, "log", "-1", "--format=%h %s"],
                          capture_output=True, text=True).stdout.strip()
    log(f"repo HEAD: {head}")

    if LOCAL_TEST:
        log("LOCAL_TEST: rom/tools.sh atlandı (araçlar hazır)")
    else:
        run(["bash", "rom/tools.sh"], cwd=WORK)
    run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-q"], cwd=WORK)
    return head


def donor_entry(drive_path, md5):
    return {
        "role": "donor-gsi-primary",
        "name": DONOR["name"],
        "url": DONOR["url"],
        "source": DONOR["source"],
        "drive_folder": "PixelOSA155F",
        "size": DONOR["size"],
        "md5": md5,
        "md5_source": ("runtime md5 of the Drive copy; bytes anchored by GitHub's "
                       "published sha256 " + DONOR["sha256"]),
        "sha256": DONOR["sha256"],
        "android_level": int(DONOR["android_level"]),
        "slot_layout": "AB",
        "arch": "arm64",
        "use": ("A17 TrebleDroid-lineage GSI (Infinity X 4.2, GAPPS variant); "
                "becomes the 'system' logical partition"),
        "caveat": ("A17 donor on an A15 vendor. Every Infinity X build here is "
                   "UNMEASURED on SM-A155F until a device logcat exists."),
    }


def write_lock(kernel, drive_path, donor_md5, build_tag):
    """G0 pin dosyası: donor (bu build'in ölçülen md5'i) + kernel + firmware.

    Kernel ve firmware pinleri repodaki inputs/inputs.lock.json'dan AYNEN alınır;
    onlar daha önce üç bağımsız Drive kopyasında doğrulanmış değerlerdir.
    """
    lock_src = REPO_LOCK or os.path.join(WORK, "inputs", "inputs.lock.json")
    with open(lock_src, encoding="utf-8") as fh:
        repo_lock = json.load(fh)
    kernel_entries = [e for e in repo_lock["inputs"]
                      if e.get("role") == "kernel-boot" and e.get("variant") == kernel]
    if not kernel_entries:
        raise RuntimeError(f"repoda '{kernel}' kernel pin'i yok")
    fw_entries = [e for e in repo_lock["inputs"] if e.get("role") == "stock-firmware"]
    if not fw_entries:
        raise RuntimeError("repoda stock-firmware pin'i yok")

    lock = {
        "schema": "pixelosa155f.inputs/1",
        "subject": f"Infinity X 4.2 GAPPS -> AP TAR, kernel={kernel}",
        "note": ("G0: bu build'in okuduğu her bayt burada pinli. Eksik pin ya da "
                 "boyut/MD5 farkı build'i durdurur (uyarıp devam etmez)."),
        "pinned_at": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "pinned_by": f"colab cell {build_tag}",
        "inputs": [donor_entry(drive_path, donor_md5)] + kernel_entries + fw_entries,
    }
    lock_dir = os.path.join(DRIVE, "locks")
    os.makedirs(lock_dir, exist_ok=True)
    path = unique(os.path.join(lock_dir, f"inputs.lock.infinityx-{kernel}-{build_tag}.json"))
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(lock, fh, indent=2)
    log(f"pin dosyası: {path}")
    return path


def build_one(kernel, donor_path, donor_md5, build_tag):
    log(f"\n{'=' * 70}\n=== 5/7 BUILD: kernel={kernel}  ({ROM_NAME}, A17)\n{'=' * 70}")

    # -1 == ölçülemedi (mount yok): o zaman durdurmak yerine uyar
    if 0 <= free_gib("/content") < NEED_COLAB_GIB:
        raise RuntimeError(f"Colab diskinde yer yok: {free_gib('/content'):.1f} GiB "
                           f"< {NEED_COLAB_GIB} GiB")
    if 0 <= free_gib(DRIVE) < NEED_DRIVE_GIB:
        raise RuntimeError(f"Drive'da yer yok: {free_gib(DRIVE):.1f} GiB "
                           f"< {NEED_DRIVE_GIB} GiB")

    # önceki build'in artıkları
    shutil.rmtree(os.path.join(WORK, "work"), ignore_errors=True)
    shutil.rmtree(os.path.join(WORK, "out"), ignore_errors=True)

    lock_path = write_lock(kernel, donor_path, donor_md5, build_tag)

    env = os.environ.copy()
    env.update({
        "INPUTS_DIR": DRIVE,
        "INPUTS_LOCK": lock_path,
        "KERNEL_VARIANT": kernel,
        "ROM_NAME": ROM_NAME,
        # donorun adında kod adı yok -> seviyeyi açıkça söylüyoruz
        "GSI_TAG": DONOR["tag"],
        "GSI_LEVEL": DONOR["android_level"],
        # tam yol: Drive'da eski Mystic zip'i de duruyor, otomatik bulma onu seçmesin
        "GSI_ZIP": donor_path,
        "EXCLUDE_USERDATA": EXCLUDE_USERDATA,
        "SKIP_GSI_EXTRAS": SKIP_GSI_EXTRAS,
        # Drive'a tek dosya gidiyor: 7 x 1.9 GB'lık transport parçalarını üretme
        "SPLIT_BYTES": "0",
    })
    t0 = time.time()
    rc, _ = run(["bash", "rom/gsi-build.sh"], cwd=WORK, env=env, check=False)
    elapsed = time.time() - t0
    if rc != 0:
        raise RuntimeError(f"gsi-build.sh rc={rc} (kernel={kernel}) "
                           f"({elapsed / 60:.1f} dk)")

    out_dir = os.path.join(WORK, "out")
    tars = [f for f in os.listdir(out_dir) if f.endswith(".tar")]
    if len(tars) != 1:
        raise RuntimeError(f"out/ içinde tek AP TAR bekleniyordu, bulunan: {tars}")
    local_tar = os.path.join(out_dir, tars[0])
    audit_src = local_tar[:-4] + ".audit.txt"
    if not os.path.isfile(audit_src):
        raise RuntimeError("audit dosyası yok - paket doğrulanmamış sayılır")
    with open(audit_src, encoding="utf-8", errors="replace") as fh:
        audit_text = fh.read()
    if "VERDICT: clean" not in audit_text:
        raise RuntimeError("odin_audit VERDICT clean DEĞİL - yüklemeye değmez")

    size = os.path.getsize(local_tar)
    sha = hash_file(local_tar, "sha256", label="sha256(AP)")
    md5 = hash_file(local_tar, "md5", label="md5(AP)")
    log(f"AP: {tars[0]}  {size} B  sha256={sha}")

    # ---- Drive'a bırak (append-only: aynı isim varsa -UTC eklenir)
    dst_tar = unique(os.path.join(DRIVE, "out", tars[0]))
    log(f"Drive'a kopyalanıyor -> {dst_tar}  (boş: {free_gib(DRIVE):.1f} GiB)")
    copy_with_progress(local_tar, dst_tar, label="AP -> Drive")
    if os.path.getsize(dst_tar) != size:
        raise RuntimeError("Drive kopyasının boyutu tutmuyor")

    drive_sha = None
    if VERIFY_DRIVE_HASH:
        drive_sha = hash_file(dst_tar, "sha256", label="sha256(Drive kopya)")
        if drive_sha != sha:
            raise RuntimeError(f"Drive kopyası bozuk: {drive_sha} != {sha}")

    moved = [dst_tar]
    # Sadece küçük metinler (.audit.txt / SHA256SUMS / JOIN). Transport parçaları
    # SPLIT_BYTES=0 ile zaten yok; olsalar bile yüklenmez (her biri ~1.9 GB).
    dist_dir = os.path.join(out_dir, "dist")
    extras = [audit_src]
    if os.path.isdir(dist_dir):
        extras += [os.path.join(dist_dir, f) for f in sorted(os.listdir(dist_dir))
                   if f.endswith(".txt")]
    for extra in extras:
        if not os.path.isfile(extra):
            continue
        d = unique(os.path.join(DRIVE, "out", os.path.basename(extra)))
        shutil.copyfile(extra, d)
        moved.append(d)

    # yerel kopyayı sil (Drive doğrulandı)
    os.remove(local_tar)
    shutil.rmtree(os.path.join(WORK, "work"), ignore_errors=True)
    log(f"yerel AP silindi, yer açıldı (Drive boş: {free_gib(DRIVE):.1f} GiB)")

    return {
        "kernel": kernel,
        "status": "ok",
        "ap_name": os.path.basename(dst_tar),
        "drive_path": dst_tar,
        "size": size,
        "sha256": sha,
        "md5": md5,
        "drive_sha256": drive_sha,
        "audit": "VERDICT: clean",
        "minutes": round(elapsed / 60, 1),
    }


def write_summary(build_tag, head, results):
    log("\n=== 7/7 özet ===")
    md = [f"# Infinity X 4.2 GAPPS — 3 kernel build, {build_tag}", ""]
    md.append(f"- repo HEAD: `{head}`")
    md.append(f"- donor: `{DONOR['name']}`")
    md.append(f"- donor sha256 (GitHub): `{DONOR['sha256']}`")
    md.append(f"- paketleme: `EXCLUDE_USERDATA={EXCLUDE_USERDATA}` "
              f"(1 = kullanıcı verisi korunur), `SKIP_GSI_EXTRAS={SKIP_GSI_EXTRAS}` "
              f"(1 = GSI'a hiç dokunulmaz)")
    md.append("")
    md.append("| kernel | durum | AP | boyut (B) | sha256 | süre |")
    md.append("|---|---|---|---|---|---|")
    for r in results:
        if r.get("status") == "ok":
            md.append(f"| {r['kernel']} | OK | `{r['ap_name']}` | {r['size']} | "
                      f"`{r['sha256']}` | {r['minutes']} dk |")
        else:
            md.append(f"| {r.get('kernel')} | HATA | — | — | — | — |")
    if FAILURES:
        md.append("")
        md.append("## Hatalar")
        for f in FAILURES:
            md.append(f"- **{f['kernel']}**: {f['error']}")
    md.append("")
    md.append("## Notlar")
    md.append("- Hiçbiri cihazda denenmedi; hepsi `unmeasured`.")
    md.append("- `stock` = vanilla (rootsuz) kernel; kök modülü (SIM fix) bu build'de kullanılamaz.")
    md.append("- İlk açılış 3-4 dakika sürebilir; boot olmazsa logcat: "
               "`adb logcat -b all -d > logcat.txt`, `bash tools/device_state.sh`.")
    path = unique(os.path.join(DRIVE, f"SUMMARY-infinityx-{build_tag}.md"))
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")
    with open(os.path.join(DRIVE, f"SUMMARY-infinityx-{build_tag}.json"), "w",
              encoding="utf-8") as fh:
        json.dump({"build_tag": build_tag, "head": head, "donor": DONOR,
                   "results": results, "failures": FAILURES}, fh, indent=2)
    log("özet yazıldı: " + path)
    print("\n".join(md))
    return path


def main():
    global LOG_PATH
    build_tag = now()
    os.makedirs(DRIVE, exist_ok=True)
    os.makedirs(os.path.join(DRIVE, "logs"), exist_ok=True)
    os.makedirs(os.path.join(DRIVE, "out"), exist_ok=True)
    LOG_PATH = os.path.join(DRIVE, "logs", f"infinityx-3builds-{build_tag}.log")
    log(f"log: {LOG_PATH}")
    log(f"Colab disk boş: {free_gib('/content'):.1f} GiB | "
        f"Drive boş: {free_gib(DRIVE):.1f} GiB")

    preflight()
    mount_drive()
    local = fetch_donor()
    donor_drive_path, donor_md5 = stage_donor_to_drive(local)
    head = prepare_repo()

    results = []
    for kernel in KERNELS:
        try:
            results.append(build_one(kernel, donor_drive_path, donor_md5, build_tag))
        except Exception as exc:                       # noqa: BLE001 - tek build düşsün, hepsi değil
            log(f"!! {kernel} build HATASI: {exc}")
            log(traceback.format_exc())
            FAILURES.append({"kernel": kernel, "error": str(exc)})
            results.append({"kernel": kernel, "status": "failed"})

    write_summary(build_tag, head, results)
    ok = sum(1 for r in results if r.get("status") == "ok")
    log(f"\nBİTTİ: {ok}/{len(KERNELS)} build tamam. Drive: {DRIVE}")
    if ok < len(KERNELS):
        log("Eksik kalanlar için log dosyasına bak: " + str(LOG_PATH))


try:
    main()
except Exception as fatal:                      # noqa: BLE001
    log(f"\n!! ÖLÜMCÜL HATA: {fatal} (build başlamadı ya da ortada durdu)")
    log(traceback.format_exc())
    try:
        write_summary(now(), "n/a", [{"kernel": k, "status": "failed"} for k in KERNELS])
    except Exception:                           # noqa: BLE001 - Drive yoksa özet de yazılamaz
        pass
    raise
