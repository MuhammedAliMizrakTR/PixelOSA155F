# ============================================================================
#  PixelOSA155F — KURTARMA HÜCRESİ (build bittikten SONRA, aynı Colab oturumunda)
#
#  Ne yapar: /content'te duran AP TAR'ı doğrular (sha256), küçük dosyaları
#  (audit + sha256 listesi + JOIN notu) Drive'a hemen yazar, sonra
#   - Drive'da yer varsa  -> TAR'ı Drive'a kopyalar
#   - yer yoksa           -> 1900 MB'lık parçalara böler ve indirme satırlarını basar
#
#  ÖNEMLİ: Colab diski oturum kapanınca SİLİNİR. Bu hücreyi çalıştırmadan sekmeyi
#  kapatma. Hücre hiçbir şeyi flash etmez, cihaza dokunmaz.
# ============================================================================

import glob
import hashlib
import os
import shutil
import subprocess
import time

WORK = "/content/PixelOSA155F"                                    # build dizini
TARGET = "/content/drive/MyDrive/PixelOSA155F/out"                # Drive hedefi
EXPECTED_SHA256 = "f0cc78c9ae26a4066ffd0bd0888e1d2be63673ca44828d658beeaedaedbe3662"
PART_SIZE = "1900M"                     # taşıma parçası boyutu (GitHub 2 GB sınırı)
FORCE_COPY = False                      # True -> kota uyarısına rağmen kopyalamayı dene

def human(n):
    return f"{n / 2**30:.2f} GiB ({n:,} B)"

def sha256_with_progress(path, label="sha256"):
    total = os.path.getsize(path)
    h = hashlib.sha256()
    done = 0
    t0 = time.time()
    last = 0
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(8 << 20), b""):
            h.update(block)
            done += len(block)
            if done - last >= (2 << 30) or done == total:
                last = done
                pct = 100.0 * done / total if total else 100.0
                pct = min(100.0, max(0.0, pct))
                print(f"  {label}: {pct:5.1f}%  {human(done)}  "
                      f"({int(time.time() - t0)} s)", flush=True)
    return h.hexdigest()

# ---------------------------------------------------------------- 1) artefakt
cands = sorted(glob.glob(os.path.join(WORK, "out", "AP_*.tar")), key=os.path.getmtime)
if not cands:
    cands = sorted(glob.glob("/content/**/AP_*.tar", recursive=True), key=os.path.getmtime)
if not cands:
    raise SystemExit("FATAL: AP_*.tar bulunamadı. Build'i yapan oturumda mısın? "
                     "(Colab diski oturumla birlikte silinir)")
ap = cands[-1]
size = os.path.getsize(ap)
base = os.path.basename(ap)[:-4]
print("AP      :", ap)
print("boyut   :", human(size))

# ---------------------------------------------------------------- 2) doğrula
digest = sha256_with_progress(ap)
ok = (digest == EXPECTED_SHA256)
print("sha256  :", digest)
print("beklenen:", EXPECTED_SHA256, "->", "EŞLEŞTİ" if ok else "FARKLI")
if not ok:
    print("UYARI: hash beklenenle uyuşmuyor; dosya yeniden üretildiyse EXPECTED_SHA256'yı")
    print("       güncelle, kopyalamadan önce sebebini anla.")

# ------------------------------------------------------- 3) küçük dosyalar
os.makedirs(TARGET, exist_ok=True)
audit = os.path.join(WORK, "out", base + ".audit.txt")
manifest = os.path.join(WORK, "out", base + ".drive-SHA256SUMS.txt")
join_note = os.path.join(WORK, "out", base + ".JOIN.txt")

with open(manifest, "w") as fh:
    fh.write(f"{digest}  {base}.tar\n")
    if os.path.isfile(audit):
        h = hashlib.sha256(open(audit, "rb").read()).hexdigest()
        fh.write(f"{h}  {base}.audit.txt\n")

for extra in (audit, manifest):
    if os.path.isfile(extra):
        dst = os.path.join(TARGET, os.path.basename(extra))
        shutil.copyfile(extra, dst)
        print("->", dst)

# ------------------------------------------------------------ 4) Drive kotası
free = shutil.disk_usage(TARGET).free
print("\nDrive boş:", human(free), "| gereken:", human(int(size * 1.05)))

def copy_with_progress(src, dst):
    total = os.path.getsize(src)
    done = 0
    t0 = time.time()
    last = 0
    with open(src, "rb") as fi, open(dst, "wb") as fo:
        for block in iter(lambda: fi.read(16 << 20), b""):
            fo.write(block)
            done += len(block)
            if done - last >= (1 << 30) or done == total:
                last = done
                elapsed = max(1e-9, time.time() - t0)
                rate = done / elapsed
                eta = max(0.0, (total - done) / max(1e-9, rate))
                pct = min(100.0, max(0.0, 100.0 * done / total))
                print(f"  kopya: {pct:5.1f}%  {human(done)}  "
                      f"{rate / 2**20:.1f} MiB/s  kalan ~{int(eta // 60)} dk", flush=True)

if free >= size * 1.05 or FORCE_COPY:
    dest = os.path.join(TARGET, base + ".tar")
    if os.path.exists(dest):
        dest = os.path.join(TARGET, base + "-v2.tar")
    print("\nDrive'a kopyalanıyor ->", dest)
    copy_with_progress(ap, dest)
    print("kopya bitti:", human(os.path.getsize(dest)))
    print("Drive'da doğrulanıyor (yavaş olabilir)...")
    got = sha256_with_progress(dest, "drive")
    print("Drive sha256:", got, "->", "OK" if got == digest else "FARKLI (tekrar dene!)")
else:
    print("\nDrive'da yer yok: TAR kopyalanmadı, parçalara bölünüyor.")
    parts_dir = "/content/AP_parts"
    os.makedirs(parts_dir, exist_ok=True)
    prefix = os.path.join(parts_dir, base + ".tar.")
    for old in glob.glob(prefix + "[0-9][0-9]"):
        os.remove(old)                     # aynı oturumda yeniden bölme
    subprocess.run(["split", "-b", PART_SIZE, "-d", "-a", "2", ap, prefix], check=True)
    parts = sorted(glob.glob(prefix + "[0-9][0-9]"))
    sums = os.path.join(parts_dir, base + ".SHA256SUMS.txt")
    with open(sums, "w") as fh:
        fh.write(f"{digest}  {base}.tar\n")
        for part in parts:
            with open(part, "rb") as pf:
                hh = hashlib.sha256()
                for block in iter(lambda: pf.read(8 << 20), b""):
                    hh.update(block)
            fh.write(f"{hh.hexdigest()}  {os.path.basename(part)}\n")
    with open(os.path.join(parts_dir, base + ".JOIN.txt"), "w") as fh:
        fh.write(f"{base}.tar  ({size:,} B)  sha256 {digest}\n\n"
                 f"cat {base}.tar.[0-9][0-9] > {base}.tar\n"
                 "sha256sum -c " + base + ".SHA256SUMS.txt\n\n"
                 "Parçalar tek başına FLASH EDİLMEZ; AP tek dosyadır.\n")
    print(f"\n{len(parts)} parça yazıldı ({parts_dir}):")
    for part in parts:
        print("  ", human(os.path.getsize(part)), part)
    print("\nŞimdi sırayla indir (her satırı ayrı hücrede çalıştır, biri bitmeden")
    print("sonrakini başlatma; tarayıcı 1.9 GB'lık parçayı daha güvenli indirir):")
    for part in parts:
        print(f"  from google.colab import files; files.download('{part}')")
    print("\nDrive'da yer açarsan TAR'ı tek parça olarak da kopyalayabilirsin:")
    print("  FORCE_COPY = True yapıp bu hücreyi yeniden çalıştır.")

print("\n================ ÖZET ================")
print("AP      :", ap)
print("boyut   :", human(size))
print("sha256  :", digest, "(beklenenle eşleşti)" if ok else "(BEKLENENLE EŞLEŞMEDİ)")
print("Drive   :", TARGET)
print("Flash YOK — paketleme 'clean' olsa bile boot UNMEASURED.")
print("======================================")
