# ============================================================================
#  PixelOSA155F — TEK HÜCRE (Colab): kur -> derle -> biter bitmez Drive'a at
#
#  Kullanım: Colab'da yeni bir hücreye bu dosyanın TAMAMINI yapıştır, çalıştır.
#  Tek yaptığı iş: repoyu çeker, 39 testi koşar, G0 pinlerini doğrular,
#  AP TAR'ı üretir, sha256'sını çıkarır ve out/ klasörünü Drive'a kopyalar.
#  HİÇBİR ŞEY FLASH ETMEZ; cihaza dokunmaz.
#
#  Ayarlar aşağıdaki blokta. Varsayılanlar bu cihaz/Drive düzeni için:
#    INPUTS : /content/drive/MyDrive/PixelOSA155F   (GSI + kernel tar + firmware)
#    TARGET : /content/drive/MyDrive/PixelOSA155F/out
# ============================================================================

import glob
import hashlib
import os
import re
import shutil
import subprocess
import time

# ----------------------------------------------------------------- ayarlar --
REPO      = "https://github.com/MuhammedAliMizrakTR/PixelOSA155F.git"
BRANCH    = "arena/802af16c-pixelosa155f"
WORK      = "/content/PixelOSA155F"
INPUTS    = "/content/drive/MyDrive/PixelOSA155F"
TARGET    = "/content/drive/MyDrive/PixelOSA155F/out"
KERNEL    = "bakasu"      # bakasu | kernelsunext | stock
ROM_NAME  = "PixelOS"
UPLOAD    = True          # False -> sadece /content'te bırak
FORCE_UPLOAD = False      # True -> Drive kotası az olsa da denemeyi zorla
KERNEL_FALLBACK_DIRS = [
    "/content/drive/MyDrive/HyperOSA155F",
    "/content/drive/MyDrive/GrapheneOS",
]
# --------------------------------------------------------------------------

def sh(cmd, cwd=None, env=None, check=True):
    print("+ " + cmd, flush=True)
    return subprocess.run(cmd, shell=True, cwd=cwd, env=env, check=check)


def sha256_file(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def human(n):
    return f"{n / 2**30:.2f} GiB ({n:,} B)"


print("=== 0/6 Drive bağlanıyor ===", flush=True)
from google.colab import drive  # noqa: E402
drive.mount("/content/drive")

if not os.path.isdir(INPUTS):
    raise SystemExit(f"FATAL: girdi klasörü yok: {INPUTS}\nDrive bağlı mı, klasör adı doğru mu?")

print("\n=== 1/6 repo hazırlanıyor ===", flush=True)
if not os.path.isdir(os.path.join(WORK, ".git")):
    sh(f"git clone -b {BRANCH} --depth 1 {REPO} '{WORK}'")
else:
    sh(f"git -C '{WORK}' fetch --depth 1 origin {BRANCH} && "
       f"git -C '{WORK}' checkout -q FETCH_HEAD")
os.chdir(WORK)
print(subprocess.run("git -C '%s' log --oneline -1" % WORK, shell=True,
                     capture_output=True, text=True).stdout.strip())

print("\n=== 2/6 girdiler ve disk kontrolü ===", flush=True)
gsi = sorted(glob.glob(os.path.join(INPUTS, "*-MysticGSI.zip*")))
fw = sorted(glob.glob(os.path.join(INPUTS, "*_fac.zip*")) +
            glob.glob(os.path.join(INPUTS, "SAMFW*.zip*")))
ktar_names = {
    "bakasu": "bakasu_35262_susfs_v2.4.0_A155FXXS7CYG4_A15_GKI.tar",
    "kernelsunext": "kernelsunext_33548_susfs_v2.4.0_A155FXXS7CYG4_A15_GKI.tar",
    "stock": "stock_optimized_5.10.226_A155FXXS7CYG4_A15_GKI.tar",
}
if KERNEL not in ktar_names:
    raise SystemExit(f"FATAL: KERNEL={KERNEL} (bakasu|kernelsunext|stock)")
want_kernel = ktar_names[KERNEL]
if not gsi:
    raise SystemExit(f"FATAL: {INPUTS} içinde *-MysticGSI.zip yok")
if not fw:
    raise SystemExit(f"FATAL: {INPUTS} içinde *_fac.zip (stok firmware) yok")
if not glob.glob(os.path.join(INPUTS, want_kernel + "*")):
    copied = None
    for extra in KERNEL_FALLBACK_DIRS:
        src = os.path.join(extra, want_kernel)
        if os.path.isfile(src):
            dst = os.path.join(INPUTS, want_kernel)
            print(f"kernel {extra} içinden kopyalanıyor -> {INPUTS}")
            shutil.copyfile(src, dst)
            copied = dst
            break
    if not copied:
        raise SystemExit(
            f"FATAL: kernel tar yok: {want_kernel}\n"
            f"  {INPUTS} içine kopyala, ya da KERNEL_FALLBACK_DIRS listesini düzelt")

print("GSI      :", os.path.basename(gsi[0]), human(os.path.getsize(gsi[0])))
print("firmware :", os.path.basename(fw[0]), human(os.path.getsize(fw[0])))
print("kernel   :", want_kernel, human(os.path.getsize(glob.glob(os.path.join(INPUTS, want_kernel + "*"))[0])))
free_local = shutil.disk_usage("/content").free
print("yerel boş:", human(free_local))
if free_local < 40 * 2**30:
    print("UYARI: 40 GiB'tan az boş alan var; build sığmayabilir.")

# Drive kotası burada görünür: AP ~10-11 GiB tutar, hesap 15 GiB ise sığmaz.
try:
    free_drive = shutil.disk_usage("/content/drive").free
    print("Drive boş:", human(free_drive))
    if UPLOAD and free_drive < 13 * 2**30:
        print("UYARI: Drive'da 13 GiB'tan az boş yer var — build bitecek ama AP")
        print("       kopyalanamayabilir. Yer aç, ya da UPLOAD=False ile sadece")
        print("       yerelde bırakıp files.download(...) kullan.")
except OSError as exc:
    print("Drive boş alanı okunamadı:", exc)

print("\n=== 3/6 araç zinciri + testler ===", flush=True)
sh("bash rom/tools.sh")
sh("python3 -m unittest discover -s tests")

print("\n=== 4/6 GERÇEK BUILD (30-60 dk sürebilir) ===", flush=True)
env = os.environ.copy()
env.update(INPUTS_DIR=INPUTS, KERNEL_VARIANT=KERNEL, ROM_NAME=ROM_NAME,
           SKIP_GSI_EXTRAS="1")
if os.environ.get("INPUTS_LOCK"):          # varsa kendi pin dosyanı kullan
    env["INPUTS_LOCK"] = os.environ["INPUTS_LOCK"]
t0 = time.time()
log = os.path.join(WORK, "build.log")
rc = subprocess.call(["/bin/bash", "-c",
                      f"set -o pipefail; bash rom/gsi-build.sh 2>&1 | tee '{log}'"],
                     env=env)
print(f"build rc={rc}  ({int(time.time() - t0)} s)  log: {log}")
if rc != 0:
    body = open(log, encoding="utf-8", errors="replace").read() if os.path.isfile(log) else ""
    print("\n".join(body.splitlines()[-60:]))
    stages = re.findall(r"########## (\d/8[^\n]*)", body)
    if stages:
        print("son başlayan aşama:", stages[-1])
    raise SystemExit(
        "BUILD DÜŞTÜ — yukarıdaki son 60 satıra bak. "
        "Aşama düşerse tümünü baştan koşma: docs/ROM_BUILD.md -> 'Re-running one stage'.")

print("\n=== 5/6 artefakt doğrulaması ===", flush=True)
aps = sorted(glob.glob(os.path.join(WORK, "out", "AP_*.tar")), key=os.path.getmtime)
if not aps:
    raise SystemExit("FATAL: out/AP_*.tar üretilmedi")
ap = aps[-1]
size = os.path.getsize(ap)
digest = sha256_file(ap)
print(f"AP      : {os.path.basename(ap)}\nboyut   : {human(size)}\nsha256  : {digest}")

audit = os.path.join(WORK, "out", os.path.basename(ap)[:-4] + ".audit.txt")
verdict = "?"
if os.path.isfile(audit):
    text = open(audit, encoding="utf-8", errors="replace").read()
    verdict = next((l.split(":", 1)[1].strip() for l in text.splitlines()
                    if l.startswith("VERDICT")), "?")
    print("audit   :", verdict)
level_file = os.path.join(WORK, "work", "gsi", "ANDROID_LEVEL")
if os.path.isfile(level_file):
    level = open(level_file).read().strip()
    print("donor   : Android", level)
    if level not in ("", "unknown") and int(level) > 15:
        print("UYARI: donor A15'ten yeni. Bu cihazda A16 denemesi arayüze ulaşmadı;"
              " boot UNMEASURED.")

print("\n=== 6/6 Drive'a kopyalama ===", flush=True)
def upload(local, folder):
    os.makedirs(folder, exist_ok=True)
    dest = os.path.join(folder, os.path.basename(local))
    if os.path.exists(dest):
        if os.path.getsize(dest) == os.path.getsize(local) and \
                sha256_file(dest) == sha256_file(local):
            print(f"zaten var, sha256 aynı -> atlandı: {os.path.basename(dest)}")
            return dest
        stem, ext = os.path.splitext(dest)
        n = 2
        while os.path.exists(f"{stem}-v{n}{ext}"):
            n += 1
        dest = f"{stem}-v{n}{ext}"
    need = os.path.getsize(local)
    free = shutil.disk_usage(folder).free
    if free and need and free < need * 1.05 and not FORCE_UPLOAD:
        print(f"UYARI: Drive boş alanı {human(free)} < gereken {human(need)} — kopyalanmadı.")
        return None
    t = time.time()
    shutil.copyfile(local, dest)
    print(f"-> {dest}  ({int(time.time() - t)} s)")
    return dest

# Drive'a yalnızca gerçekten orada duran dosyalar için bir sha256 listesi yaz
# (out/dist manifesti, Drive'a kopyalanmayan .tar.NN taşıma parçalarını da listeler).
manifest = os.path.join(WORK, "out", os.path.basename(ap)[:-4] + ".drive-SHA256SUMS.txt")
with open(manifest, "w") as fh:
    fh.write(f"{digest}  {os.path.basename(ap)}\n")
    if os.path.isfile(audit):
        fh.write(f"{sha256_file(audit)}  {os.path.basename(audit)}\n")

uploaded = []
if UPLOAD:
    for extra in (audit, manifest):
        if os.path.isfile(extra):
            upload(extra, TARGET)
    target = upload(ap, TARGET)
    if target:
        uploaded.append(target)
else:
    print("UPLOAD=False -> sadece yerel dosya bırakıldı")

print("\n================ SONUÇ ================")
print("AP      :", ap)
print("boyut   :", human(size))
print("sha256  :", digest)
print("audit   :", verdict)
if uploaded:
    print("Drive   :", uploaded[-1])
else:
    print("Drive   : kopyalanmadı (yukarıdaki uyarıya bak)")
    print("indirmek için:\n  from google.colab import files;"
          f" files.download('{ap}')")
print("=======================================")
print("Flash YOK. Paketleme 'clean' ise bile boot UNMEASURED;"
      " cihazda logcat olmadan 'çalışıyor' denmez.")
