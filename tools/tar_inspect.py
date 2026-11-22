#!/usr/bin/env python3
"""Read-only TAR inspector for A155F Odin/kernel artifacts.

Prints the member table of a TAR and flags the packaging problems that the
project's safety rules care about:

  * LZ4-compressed members (Odin AP artifacts must be plain ``.img`` members)
  * a trailing ``MD5<32 hex chars>`` footer appended to the TAR
  * a TAR whose size is not a multiple of 512 bytes (footer or truncation)

The tool never writes to, moves or repairs an input. It is deliberately
read-only so it can be pointed at downloaded release assets.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tarfile

LZ4_MAGIC = b"\x04\x22\x4d\x18"
SPARSE_MAGIC = b"\x3a\xff\x26\xed"
ANDROID_BOOT_MAGIC = b"ANDROID!"
CHROMEOS_BOOT_MAGIC = b"CHROMEOS"
MTK_MAGIC = b"\x88\x16\x88\x58"
HEX = set(b"0123456789abcdefABCDEF")


def sha256_file(path: str, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def detect_md5_footer(path: str) -> bool:
    """True when the last 32 bytes look like an appended Odin MD5 fingerprint."""
    size = os.path.getsize(path)
    if size < 128:
        return False
    with open(path, "rb") as fh:
        fh.seek(-32, os.SEEK_END)
        tail = fh.read(32)
    return len(tail) == 32 and all(byte in HEX for byte in tail) and size % 512 != 0


def sniff(path_or_bytes) -> str:
    """Best-effort container label for the first bytes of a member."""
    if isinstance(path_or_bytes, (bytes, bytearray)):
        head = bytes(path_or_bytes[:16])
    else:
        with open(path_or_bytes, "rb") as fh:
            head = fh.read(16)
    if head[:4] == LZ4_MAGIC:
        return "lz4-frame"
    if head[:4] == SPARSE_MAGIC:
        return "sparse-image"
    if head[:8] == ANDROID_BOOT_MAGIC:
        return "android-boot"
    if head[:8] == CHROMEOS_BOOT_MAGIC:
        return "chromeos-boot"
    if head[:4] == MTK_MAGIC:
        return "mtk-header"
    return "unknown"


def inspect(path: str) -> dict:
    report: dict = {
        "path": path,
        "size": os.path.getsize(path),
        "sha256": sha256_file(path),
        "size_multiple_of_512": os.path.getsize(path) % 512 == 0,
        "md5_footer": detect_md5_footer(path),
        "members": [],
        "problems": [],
    }
    try:
        with tarfile.open(path, "r:") as tf:
            for member in tf:
                entry = {
                    "name": member.name,
                    "size": member.size,
                    "mode": oct(member.mode),
                    "mtime": member.mtime,
                    "type": "file" if member.isreg() else "other",
                }
                if member.isreg():
                    extracted = tf.extractfile(member)
                    if extracted is not None:
                        head = extracted.read(16)
                        entry["magic"] = head.hex()
                        entry["container"] = sniff(head)
                        if entry["container"] == "lz4-frame":
                            report["problems"].append(
                                f"member '{member.name}' is LZ4-compressed; "
                                "Odin AP artifacts must ship plain images"
                            )
                else:
                    report["problems"].append(
                        f"member '{member.name}' is not a regular file"
                    )
                report["members"].append(entry)
    except (tarfile.TarError, OSError) as exc:
        report["problems"].append(f"not a readable plain TAR: {exc}")
    if report["md5_footer"]:
        report["problems"].append(
            "TAR has an appended MD5 fingerprint (Odin .tar.md5 style); "
            "plain TAR required"
        )
    if not report["size_multiple_of_512"] and not report["md5_footer"]:
        report["problems"].append(
            "size is not a multiple of 512 and no MD5 footer detected; "
            "file may be truncated"
        )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archives", nargs="+", help="TAR files to inspect")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    args = parser.parse_args(argv)

    reports = []
    status = 0
    for archive in args.archives:
        if not os.path.isfile(archive):
            print(f"missing: {archive}", file=sys.stderr)
            status = 2
            continue
        report = inspect(archive)
        reports.append(report)
        if report["problems"]:
            status = 1
        if args.json:
            continue
        print(f"== {report['path']}")
        print(f"   size    : {report['size']} bytes")
        print(f"   sha256  : {report['sha256']}")
        for member in report["members"]:
            print(
                "   - {name:<32} {size:>12} {mode:>6} {container}".format(
                    name=member["name"][:32],
                    size=member["size"],
                    mode=member["mode"],
                    container=member.get("container", "-"),
                )
            )
        if report["problems"]:
            for problem in report["problems"]:
                print(f"   PROBLEM: {problem}")
        else:
            print("   packaging: clean (plain TAR, no LZ4 members, no MD5 footer)")

    if args.json:
        print(json.dumps(reports, indent=2))
    return status


if __name__ == "__main__":
    raise SystemExit(main())
