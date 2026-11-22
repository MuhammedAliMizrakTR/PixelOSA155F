#!/usr/bin/env python3
"""Inspect a GSI zip (or loose image) without committing to a flash.

Reports what the archive actually contains: members, image container type
(Android sparse / ext4 / EROFS / raw), expanded size, and GSI flavour hints from
the filename. Optional ``--extract`` unpacks to a directory, refusing to
overwrite anything.

The point is to answer, before any device action: *is this an AB arm64 system
image, how big is it once expanded, and does it fit the target's system
partition?*
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
import sys
import zipfile

SPARSE_MAGIC = 0xED26FF3A
EXT4_MAGIC_OFFSET = 1080
EXT4_MAGIC = 0xEF53
EROFS_MAGIC_OFFSET = 1024
EROFS_MAGIC = 0xE0F5E1E2
HEX = set(b"0123456789abcdefABCDEF")
IMAGE_SUFFIXES = (".img", ".img.raw", ".bin")
COMPRESSED_SUFFIXES = (".xz", ".gz", ".lz4", ".zst", ".zip")
# system.img.{gz,xz,lz4} is a supported donor layout (handled by gsi-inputs.sh);
# .zst and every non-system compressed member are still refused.
HANDLED_SYSTEM_SUFFIXES = ("system.img.gz", "system.img.xz", "system.img.lz4")


def classify(blob: bytes) -> dict:
    info: dict = {"container": "unknown"}
    if len(blob) >= 28 and struct.unpack_from("<I", blob, 0)[0] == SPARSE_MAGIC:
        (magic, major, _minor, file_hdr_sz, chunk_hdr_sz, blk_sz,
         total_blks, total_chunks, _csum) = struct.unpack_from("<IHHHHIIII", blob, 0)
        info = {
            "container": "android-sparse",
            "sparse_major": major,
            "file_hdr_sz": file_hdr_sz,
            "chunk_hdr_sz": chunk_hdr_sz,
            "block_size": blk_sz,
            "total_blocks": total_blks,
            "total_chunks": total_chunks,
            "expanded_bytes": total_blks * blk_sz,
            "magic": f"0x{magic:08x}",
        }
        return info
    if len(blob) >= EXT4_MAGIC_OFFSET + 2 and struct.unpack_from(
        "<H", blob, EXT4_MAGIC_OFFSET
    )[0] == EXT4_MAGIC:
        log_block = struct.unpack_from("<I", blob, 1024 + 24)[0]
        block_size = 1024 << log_block if log_block < 8 else None
        blocks_lo = struct.unpack_from("<I", blob, 1024 + 4)[0]
        info = {
            "container": "ext4",
            "log_block_size": log_block,
            "block_size": block_size,
            "blocks_count_lo": blocks_lo,
            "expanded_bytes": block_size * blocks_lo if block_size else None,
        }
        return info
    if len(blob) >= EROFS_MAGIC_OFFSET + 4 and struct.unpack_from(
        "<I", blob, EROFS_MAGIC_OFFSET
    )[0] == EROFS_MAGIC:
        info = {"container": "erofs", "magic": "0xe0f5e1e2"}
        return info
    # AVB0 = avbtool vbmeta image (verification-disabled images made in stage 6/8).
    if blob[:4] == b"AVB0":
        info = {"container": "avb-vbmeta", "magic": "AVB0"}
        return info
    # VNDRBOOT = the AOSP/MTK vendor_boot header; without this it showed up as
    # "unknown" in odin_audit even though the member is perfectly normal.
    if blob[:8] == b"VNDRBOOT":
        info = {"container": "android-vendor-boot", "magic": "VNDRBOOT"}
        return info
    if blob[:8] in (b"ANDROID!", b"CHROMEOS"):
        info = {"container": "chromeos-boot" if blob[:8] == b"CHROMEOS" else "android-boot"}
        return info
    return info


def flavour_hint(name: str) -> dict:
    lowered = name.lower()
    hint = {
        "ab_token": "ab" in lowered,
        "aonly_token": "aonly" in lowered or "a-only" in lowered,
        "vndklite_token": "vndklite" in lowered,
        "arch_arm64": "arm64" in lowered or "a64" in lowered,
        "android_major_guess": None,
    }
    for token in ("-16-", "-15-", "-14-", "-13-", "-17-"):
        if token in lowered:
            hint["android_major_guess"] = int(token.strip("-"))
            break
    return hint


def inspect_zip(path: str) -> dict:
    report: dict = {
        "archive": path,
        "size": os.path.getsize(path),
        "archive_md5": md5_file(path),
        "members": [],
        "problems": [],
        "notes": [],
        "flavour": flavour_hint(os.path.basename(path)),
    }
    try:
        with zipfile.ZipFile(path) as zf:
            for info in zf.infolist():
                entry = {
                    "name": info.filename,
                    "zip_size": info.file_size,
                    "compressed_size": info.compress_size,
                }
                lower = info.filename.lower()
                if info.is_dir():
                    entry["kind"] = "directory"
                elif lower.endswith(HANDLED_SYSTEM_SUFFIXES):
                    # A compressed *system* member is fine: rom/gsi-inputs.sh
                    # decompresses it once into work/gsi/zip/system.img. Any
                    # other compressed member stays a problem - the pipeline
                    # only ever consumes the system image.
                    entry["kind"] = "compressed-system-image"
                    report["notes"].append(
                        f"'{info.filename}' is a compressed system image - "
                        "rom/gsi-inputs.sh decompresses it automatically"
                    )
                elif lower.endswith(COMPRESSED_SUFFIXES):
                    entry["kind"] = "compressed-image"
                    report["problems"].append(
                        f"'{info.filename}' is compressed inside the zip; "
                        "decompress once and keep the original"
                    )
                elif lower.endswith(IMAGE_SUFFIXES):
                    entry["kind"] = "image"
                    with zf.open(info) as fh:
                        head = fh.read(4096)
                    entry.update(classify(head))
                    if info.file_size > 4 * 1024 ** 3:
                        # Not a defect: modern GSIs are routinely larger than 4 GiB.
                        # What matters is whether the rebuilt super can reserve it.
                        report["notes"].append(
                            f"'{info.filename}' is {info.file_size} bytes "
                            f"({info.file_size / 1024 ** 3:.2f} GiB) - the rebuilt super must "
                            "reserve at least this much for 'system'; rom/lp_plan.py grows the "
                            "partition/group and fails loudly if the super is too small"
                        )
                else:
                    entry["kind"] = "other"
                report["members"].append(entry)
    except zipfile.BadZipFile as exc:
        report["problems"].append(f"not a readable zip: {exc}")
    images = [m for m in report["members"] if m["kind"] == "image"]
    packed_system = [m for m in report["members"] if m["kind"] == "compressed-system-image"]
    report["image_count"] = len(images) + len(packed_system)
    if not images and not packed_system:
        report["problems"].append("no .img member found in the archive")
    report["largest_image"] = max(
        (m for m in images), key=lambda m: m["zip_size"], default=None
    )
    return report


def md5_file(path: str, chunk: int = 1 << 20) -> str:
    h = hashlib.md5()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def extract(path: str, dest: str, only: str | None = None) -> list[str]:
    written = []
    os.makedirs(dest, exist_ok=True)
    with zipfile.ZipFile(path) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            if only and info.filename != only:
                continue
            target = os.path.join(dest, os.path.basename(info.filename))
            if os.path.exists(target):
                raise SystemExit(f"refusing to overwrite existing file: {target}")
            with zf.open(info) as src, open(target, "wb") as dst:
                while True:
                    block = src.read(1 << 20)
                    if not block:
                        break
                    dst.write(block)
            written.append(target)
    return written


def human(report: dict) -> str:
    lines = [
        f"archive : {report['archive']} ({report['size']} bytes)",
        f"md5     : {report['archive_md5']}",
        "flavour : " + ", ".join(
            f"{k}={v}" for k, v in report["flavour"].items() if v is not None
        ),
        "members :",
    ]
    for member in report["members"]:
        detail = member.get("container", member["kind"])
        expanded = member.get("expanded_bytes")
        extra = f" expanded={expanded}" if expanded else ""
        lines.append(
            f"  - {member['name']:<46} {member['zip_size']:>13} B  {detail}{extra}"
        )
    for note in report.get("notes", []):
        lines.append(f"NOTE: {note}")
    for problem in report["problems"]:
        lines.append(f"PROBLEM: {problem}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--extract", metavar="DIR", help="extract members to DIR")
    parser.add_argument("--only", help="extract only this member name")
    args = parser.parse_args(argv)

    if not os.path.isfile(args.archive):
        print(f"missing: {args.archive}", file=sys.stderr)
        return 2
    report = inspect_zip(args.archive)
    print(json.dumps(report, indent=2) if args.json else human(report))
    status = 1 if report["problems"] else 0
    if args.extract:
        written = extract(args.archive, args.extract, args.only)
        for path in written:
            print(f"extracted: {path}")
    return status


if __name__ == "__main__":
    sys.exit(main())
