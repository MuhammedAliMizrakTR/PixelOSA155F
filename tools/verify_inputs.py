#!/usr/bin/env python3
"""Verify local copies of the pinned Drive inputs for the A155F project.

``inputs/inputs.lock.json`` pins every donor/target file the project is allowed
to build from: Drive file id, exact byte size and the Drive-reported MD5. This
tool re-hashes whatever you downloaded locally and refuses to let a build start
on a mismatched or renamed file.

Usage::

    python3 tools/verify_inputs.py --dir ~/A155F/inputs
    python3 tools/verify_inputs.py --dir /content/drive/MyDrive/GrapheneOS --json

Exit codes: 0 all pinned inputs present and matching, 1 mismatches/missing,
2 usage error. Nothing is ever written.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys

DEFAULT_LOCK = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "inputs",
    "inputs.lock.json",
)


def hash_file(path: str, algo: str, chunk: int = 1 << 20) -> str:
    h = hashlib.new(algo)
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def load_lock(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def check(lock: dict, directory: str, deep: bool) -> tuple[list[dict], bool]:
    results = []
    ok = True
    for entry in lock.get("inputs", []):
        name = entry["name"]
        path = os.path.join(directory, name)
        result = {
            "name": name,
            "role": entry.get("role"),
            "drive_id": entry.get("drive_id"),
            "expected_size": entry.get("size"),
            "state": "missing",
        }
        if os.path.isfile(path):
            size = os.path.getsize(path)
            result["actual_size"] = size
            if entry.get("size") is not None and size != entry["size"]:
                result["state"] = "size-mismatch"
                ok = False
            elif entry.get("md5"):
                result["state"] = "md5-ok"
                if deep:
                    actual = hash_file(path, "md5")
                    result["actual_md5"] = actual
                    if actual != entry["md5"]:
                        result["state"] = "md5-mismatch"
                        ok = False
            else:
                result["state"] = "size-ok"
        else:
            ok = False
        results.append(result)
    return results, ok


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", required=True, help="directory holding the inputs")
    parser.add_argument("--lock", default=DEFAULT_LOCK, help="lock file path")
    parser.add_argument("--quick", action="store_true",
                        help="sizes only (skip MD5 re-hash of multi-GB files)")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    if not os.path.isdir(args.dir):
        print(f"not a directory: {args.dir}", file=sys.stderr)
        return 2
    lock = load_lock(args.lock)
    results, ok = check(lock, args.dir, deep=not args.quick)

    if args.json:
        print(json.dumps({"ok": ok, "results": results}, indent=2))
    else:
        print(f"lock: {args.lock} (subject: {lock.get('subject', 'unknown')})")
        for item in results:
            marker = "OK  " if item["state"].endswith("-ok") else "FAIL"
            print(
                f"[{marker}] {item['state']:<13} {item['name']} "
                f"({item.get('actual_size', '?')} bytes, role={item['role']})"
            )
        print("inputs: verified" if ok else "inputs: REFUSED - fix before building")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
