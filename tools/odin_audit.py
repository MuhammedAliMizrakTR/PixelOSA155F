#!/usr/bin/env python3
"""Audit a ready-made Odin AP TAR before anyone flashes it.

Answers three questions about an AP package, using only the bytes:

1. Packaging: plain TAR? any LZ4 members? an appended MD5 fingerprint?
2. Content: what is each member (sparse / ext4 / EROFS / liblp super / boot)?
3. **Safety**: if a `super.img` member is present, is it a real liblp super that
   still contains the Samsung `vendor`/`odm` logical partitions, or is it a
   renamed `system` image that would wipe them?

Exit codes: 0 clean, 1 warnings, 2 critical (do not flash as-is), 3 unreadable.

This tool never writes; it reads the TAR member prefixes only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tarfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import gsi_inspect  # noqa: E402
import super_inspect  # noqa: E402

LZ4_MAGIC = b"\x04\x22\x4d\x18"
HEX = set(b"0123456789abcdefABCDEF")
SUPER_NAMES = ("super.img",)
SYSTEM_NAMES = ("system.img", "system_ext.img", "product.img", "vendor.img", "odm.img")


def sha256_file(path: str, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def md5_footer(path: str) -> bool:
    size = os.path.getsize(path)
    if size < 128:
        return False
    with open(path, "rb") as fh:
        fh.seek(-32, os.SEEK_END)
        tail = fh.read(32)
    return all(byte in HEX for byte in tail) and size % 512 != 0


def audit(path: str) -> dict:
    report = {
        "archive": path,
        "size": os.path.getsize(path),
        "sha256": sha256_file(path),
        "plain_tar_size": os.path.getsize(path) % 512 == 0,
        "md5_footer": md5_footer(path),
        "members": [],
        "findings": [],
    }

    def add(severity: str, code: str, message: str) -> None:
        report["findings"].append({"severity": severity, "code": code, "message": message})

    if report["md5_footer"]:
        add("warning", "md5-footer",
            "TAR carries an Odin MD5 fingerprint; the project's packaging rule is a plain TAR")
    if not report["plain_tar_size"] and not report["md5_footer"]:
        add("warning", "odd-size", "size is not a multiple of 512; possible truncation")

    try:
        tf = tarfile.open(path, "r:")
    except (tarfile.TarError, OSError) as exc:
        add("critical", "unreadable", f"not a readable plain TAR: {exc}")
        return report

    with tf:
        for member in tf:
            if not member.isreg():
                # Odin AP TARs really do carry explicit directory entries (Samsung's
                # stock AP has `meta-data/` next to `meta-data/fota.zip`). A literal
                # directory entry is harmless; anything else (symlink, device node)
                # is not, so only those stay warnings.
                if member.isdir():
                    report["notes"] = report.get("notes", [])
                    report["notes"].append(f"directory entry '{member.name}' (stock APs have these too)")
                else:
                    add("warning", "non-regular", f"member '{member.name}' is not a regular file")
                continue
            entry = {"name": member.name, "size": member.size}
            stream = tf.extractfile(member)
            if stream is None:
                add("warning", "no-data", f"member '{member.name}' has no readable data")
                report["members"].append(entry)
                continue
            head = stream.read(4096)
            entry.update(gsi_inspect.classify(head))
            if head[:4] == LZ4_MAGIC:
                add("critical", "lz4-member",
                    f"member '{member.name}' is LZ4-compressed; Odin AP members must be raw images")
            stream.seek(0)

            if entry["container"] == "android-sparse":
                expanded = entry.get("expanded_bytes")
                entry["expanded_bytes"] = expanded
            else:
                entry["expanded_bytes"] = member.size

            base = os.path.basename(member.name).lower()
            if base in SUPER_NAMES or (entry["container"] == "android-sparse"
                                       and "super" in base):
                lp = super_inspect.inspect_stream(stream, member.size)
                entry["lp"] = {
                    "container": lp.get("container"),
                    "partitions": [
                        {"name": p["name"], "size_bytes": p.get("size_bytes")}
                        for p in lp.get("partitions", [])
                    ],
                    "groups": [
                        {"name": g["name"], "maximum_size": g["maximum_size"]}
                        for g in lp.get("groups", [])
                    ],
                    "problems": lp.get("problems", []),
                }
                names = {p["name"] for p in lp.get("partitions", [])}
                if lp.get("container") != "liblp":
                    add("critical", "super-not-lp",
                        f"'{member.name}' is '{entry['container']}', not a liblp super. If Odin "
                        f"writes this to the super partition it replaces EVERY logical partition "
                        f"(system, system_ext, product, vendor, odm). Recoverable only by a full "
                        f"stock Odin flash; it will not boot as a PixelOS GSI.")
                else:
                    if not names:
                        add("warning", "lp-empty",
                            f"'{member.name}' parsed as liblp but exposes no partitions")
                    missing = [p for p in ("vendor", "odm") if p not in names]
                    if missing:
                        add("critical", "super-missing-vendor",
                            f"super member has no {missing} logical partition: the Samsung/MTK "
                            f"HALs would be gone, so the device cannot boot with a working "
                            f"display/RIL/camera stack")
                    if "system" not in names:
                        add("warning", "super-missing-system",
                            "super member has no 'system' partition; nothing would replace the ROM")
                    entry["lp"]["missing_vendor_parts"] = missing
            elif base in SYSTEM_NAMES:
                add("info", "logical-partition-image",
                    f"'{member.name}' is a bare partition image ({entry['container']}); this is the "
                    f"usual Samsung-GSI shape only if your Odin method flashes it into the logical "
                    f"partition of the same name")
            report["members"].append(entry)

    has_super = any(os.path.basename(m["name"]).lower() in SUPER_NAMES for m in report["members"])
    has_system = any(os.path.basename(m["name"]).lower() == "system.img" for m in report["members"])
    if has_super and has_system:
        add("warning", "two-targets",
            "both super.img and system.img present; Odin would fight over the same content")
    if not report["members"]:
        add("critical", "empty", "archive has no members")

    severities = {f["severity"] for f in report["findings"]}
    report["verdict"] = (
        "critical" if "critical" in severities else
        "warnings" if "warning" in severities else "clean"
    )
    return report


def human(report: dict) -> str:
    lines = [
        f"archive  : {report['archive']} ({report['size']} bytes)",
        f"sha256   : {report['sha256']}",
        f"plain tar: {report['plain_tar_size']}   md5 footer: {report['md5_footer']}",
        "members  :",
    ]
    for member in report["members"]:
        detail = member.get("container", "?")
        lines.append(
            f"  - {member['name']:<20} raw={member['size']:>13} "
            f"expanded={member.get('expanded_bytes')} container={detail}"
        )
        lp = member.get("lp")
        if lp:
            parts = ", ".join(
                f"{p['name']}({p['size_bytes']})" for p in lp["partitions"]
            ) or "<none>"
            lines.append(f"      liblp={lp['container']} partitions: {parts}")
    for note in report.get("notes", []):
        lines.append(f"[NOTE] {note}")
    for finding in report["findings"]:
        lines.append(f"[{finding['severity'].upper()}] {finding['message']}")
    lines.append(f"VERDICT: {report['verdict']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if not os.path.isfile(args.archive):
        print(f"missing: {args.archive}", file=sys.stderr)
        return 3
    report = audit(args.archive)
    print(json.dumps(report, indent=2) if args.json else human(report))
    return {"clean": 0, "warnings": 1, "critical": 2}.get(report["verdict"], 3)


if __name__ == "__main__":
    sys.exit(main())
