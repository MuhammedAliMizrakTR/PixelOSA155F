#!/usr/bin/env python3
"""Build plain, reproducible Odin TAR artifacts (AP-style) without clobbering.

Rules enforced (see docs/20-FIRST-BUILD.md):

  * plain ``tar`` only - no ``.tar.md5`` fingerprint, no LZ4 members
  * reproducible output (fixed owner, fixed mtime, sorted member order)
  * refuses to overwrite an existing artifact unless ``--force`` is given
  * never deletes anything; optional transport chunks use ``.00``, ``.01`` ...
  * writes a SHA-256 manifest next to the artifact

Example::

    python3 tools/odin_pack.py --out out/AP_kernel.tar \\
        --manifest out/AP_kernel.manifest.json \\
        boot.img vendor_boot.img

    python3 tools/odin_pack.py --out out/AP_kernel.tar --verify \\
        --manifest out/AP_kernel.manifest.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tarfile
import datetime

TOOL = "odin_pack/1"
LZ4_MAGIC = b"\x04\x22\x4d\x18"
HEX = set(b"0123456789abcdefABCDEF")
DEFAULT_MTIME = "2026-01-01T00:00:00Z"


def sha256_file(path: str, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def md5_file(path: str, chunk: int = 1 << 20) -> str:
    h = hashlib.md5()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def parse_utc(value: str) -> int:
    stamp = datetime.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    return int(stamp.replace(tzinfo=datetime.timezone.utc).timestamp())


def collect_members(paths: list[str]) -> list[str]:
    members: list[str] = []
    seen: dict[str, str] = {}
    for raw in paths:
        if os.path.isdir(raw):
            for name in sorted(os.listdir(raw)):
                candidate = os.path.join(raw, name)
                if os.path.isfile(candidate):
                    members.append(candidate)
            continue
        members.append(raw)

    resolved: list[str] = []
    for member in sorted(members, key=os.path.basename):
        if not os.path.isfile(member):
            raise SystemExit(f"not a regular file: {member}")
        if os.path.islink(member):
            raise SystemExit(f"refusing symlink member: {member}")
        base = os.path.basename(member)
        if base.lower().endswith((".md5", ".lz4", ".zip", ".tgz", ".gz")):
            raise SystemExit(
                f"refusing member '{base}': Odin AP members must be raw images "
                "(no compression, no md5 sidecars)"
            )
        if base in seen:
            raise SystemExit(
                f"duplicate member name '{base}' from {seen[base]} and {member}"
            )
        seen[base] = member
        with open(member, "rb") as fh:
            if fh.read(4) == LZ4_MAGIC:
                raise SystemExit(f"member '{base}' is LZ4-compressed; not allowed")
        resolved.append(member)
    if not resolved:
        raise SystemExit("no members selected")
    return resolved


def tail_has_md5_footer(path: str) -> bool:
    size = os.path.getsize(path)
    if size < 128:
        return False
    with open(path, "rb") as fh:
        fh.seek(-32, os.SEEK_END)
        tail = fh.read(32)
    return all(byte in HEX for byte in tail) and size % 512 != 0


def build(out_path: str, members: list[str], mtime: int) -> dict:
    tmp_path = out_path + ".part"
    member_records = []
    with tarfile.open(tmp_path, "w", format=tarfile.GNU_FORMAT) as tf:
        for member in members:
            info = tf.gettarinfo(member, arcname=os.path.basename(member))
            info.uid = 0
            info.gid = 0
            info.uname = "root"
            info.gname = "root"
            info.mtime = mtime
            info.mode = 0o755 if os.access(member, os.X_OK) else 0o644
            with open(member, "rb") as fh:
                tf.addfile(info, fh)
            member_records.append(
                {
                    "name": os.path.basename(member),
                    "size": os.path.getsize(member),
                    "sha256": sha256_file(member),
                }
            )
    os.replace(tmp_path, out_path)
    return {
        "size": os.path.getsize(out_path),
        "sha256": sha256_file(out_path),
        "md5": md5_file(out_path),
        "md5_footer": tail_has_md5_footer(out_path),
        "members": member_records,
    }


def manifest_for(out_path: str, built: dict, mtime: int, chunk_size: int | None) -> dict:
    record = {
        "schema": "nothingosa155f.odinpack/1",
        "tool": TOOL,
        "artifact": os.path.basename(out_path),
        "size": built["size"],
        "sha256": built["sha256"],
        "md5": built["md5"],
        "plain_tar": True,
        "md5_footer": built["md5_footer"],
        "lz4_members": [],
        "reproducible": True,
        "fixed_mtime_utc": datetime.datetime.fromtimestamp(
            mtime, datetime.timezone.utc
        ).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "members": built["members"],
        "notes": [
            "Odin AP artifact: flash the .tar itself, never a chunk.",
            "Chunks are transport containers only; join them before flashing.",
        ],
    }
    if chunk_size:
        chunks = []
        with open(out_path, "rb") as fh:
            index = 0
            while True:
                block = fh.read(chunk_size)
                if not block:
                    break
                name = f"{os.path.basename(out_path)}.{index:02d}"
                with open(os.path.join(os.path.dirname(out_path) or ".", name), "wb") as ch:
                    ch.write(block)
                chunks.append(
                    {"name": name, "size": len(block), "sha256": hashlib.sha256(block).hexdigest()}
                )
                index += 1
        record["chunks"] = chunks
        record["join_command"] = (
            f"cat {os.path.basename(out_path)}.?? > {os.path.basename(out_path)} && "
            f"sha256sum -c {os.path.basename(out_path)}.sha256"
        )
    return record


def verify(out_path: str, manifest_path: str) -> int:
    with open(manifest_path, "r", encoding="utf-8") as fh:
        expected = json.load(fh)
    actual = {
        "size": os.path.getsize(out_path),
        "sha256": sha256_file(out_path),
        "md5": md5_file(out_path),
    }
    ok = True
    for key in ("size", "sha256", "md5"):
        if expected.get(key) != actual[key]:
            print(f"mismatch {key}: expected {expected.get(key)} got {actual[key]}")
            ok = False
    if tail_has_md5_footer(out_path):
        print("mismatch: artifact has an MD5 footer")
        ok = False
    print("verify: OK" if ok else "verify: FAILED")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, help="output TAR path (plain tar)")
    parser.add_argument("--manifest", help="manifest JSON path")
    parser.add_argument("--mtime", default=DEFAULT_MTIME, help="fixed UTC mtime")
    parser.add_argument("--chunk-size", type=int, default=None,
                        help="also write .00/.01 transport chunks of N bytes")
    parser.add_argument("--force", action="store_true",
                        help="overwrite an existing --out (never a release asset)")
    parser.add_argument("--verify", action="store_true",
                        help="verify an existing artifact against --manifest")
    parser.add_argument("members", nargs="*", help="member files or a directory")
    args = parser.parse_args(argv)

    if args.verify:
        if not args.manifest:
            raise SystemExit("--verify requires --manifest")
        return verify(args.out, args.manifest)

    if not args.members:
        raise SystemExit("no members given")
    if os.path.exists(args.out) and not args.force:
        raise SystemExit(
            f"refusing to overwrite existing artifact: {args.out} "
            "(inspect it first, or pass --force for a local scratch rebuild)"
        )

    out_dir = os.path.dirname(os.path.abspath(args.out))
    os.makedirs(out_dir, exist_ok=True)
    mtime = parse_utc(args.mtime)
    members = collect_members(args.members)
    built = build(args.out, members, mtime)
    if built["md5_footer"]:
        raise SystemExit("internal error: produced artifact has an MD5 footer")
    record = manifest_for(args.out, built, mtime, args.chunk_size)

    manifest_path = args.manifest or args.out + ".manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=2)
        fh.write("\n")

    print(f"artifact : {args.out} ({built['size']} bytes)")
    print(f"sha256   : {built['sha256']}")
    print(f"md5      : {built['md5']}")
    print(f"members  : {', '.join(m['name'] for m in built['members'])}")
    print(f"manifest : {manifest_path}")
    if args.chunk_size:
        print(f"chunks   : {len(record['chunks'])} x <= {args.chunk_size} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
