#!/usr/bin/env python3
"""Gate G0: refuse to use an input that is not pinned, or whose bytes differ.

``inputs/inputs.lock.json`` pins every donor/target file by Drive id, exact byte
size and MD5. The build reads files from a Drive mount where Google Drive may
have appended a localized copy suffix to the name::

    bakasu_35262_susfs_v2.4.0_A155FXXS7CYG4_A15_GKI.tar adlı dosyanın kopyası

so matching is done on the longest pinned name that is a prefix of the real file
name, never on an exact name alone.

Usage::

    python3 tools/pin_gate.py --file <path> [--lock LOCK] [--name NAME] [--role ROLE]

Exit codes: 0 pinned and byte-exact, 1 missing pin / size or MD5 mismatch,
2 usage error. Read-only: the file is never modified.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from verify_inputs import hash_file  # noqa: E402

DEFAULT_LOCK = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "inputs",
    "inputs.lock.json",
)


class GateError(Exception):
    """A G0 failure: the file may not be used."""


def load_lock(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def find_entry(lock: dict, path: str, name: str | None = None,
               role: str | None = None) -> dict:
    """Longest pinned name that is a prefix of the real file name."""
    base = os.path.basename(path)
    entries = lock.get("inputs", [])
    cands = [e for e in entries if e.get("name") and base.startswith(e["name"])]
    if name:
        narrowed = [e for e in cands
                    if e["name"] == name or name.startswith(e["name"])]
        cands = narrowed or cands
    if role:
        narrowed = [e for e in cands if e.get("role") == role]
        cands = narrowed or cands
    if not cands:
        raise GateError(
            f"'{base}' is not pinned in the lock (roles={role or 'any'}, "
            f"name hint={name or 'none'}); G0 gate not met"
        )
    return max(cands, key=lambda e: len(e["name"]))


def check(lock: dict, path: str, name: str | None = None,
          role: str | None = None, quiet: bool = False) -> dict:
    if not os.path.isfile(path):
        raise GateError(f"missing input file: {path}")
    entry = find_entry(lock, path, name=name, role=role)
    size = os.path.getsize(path)
    expected_md5 = entry.get("md5")
    expected_size = entry.get("size")
    if not expected_md5:
        raise GateError(f"no pinned MD5 for '{entry['name']}'")
    if expected_size is None:
        raise GateError(f"no pinned size for '{entry['name']}'")
    if size != expected_size:
        raise GateError(
            f"size mismatch for '{entry['name']}': file {size} != pinned {expected_size}"
        )
    actual_md5 = hash_file(path, "md5")
    if actual_md5 != expected_md5:
        raise GateError(
            f"MD5 mismatch for '{entry['name']}': file {actual_md5} != pinned {expected_md5}"
        )
    result = {
        "name": entry["name"],
        "role": entry.get("role"),
        "file": path,
        "size": size,
        "md5": actual_md5,
        "drive_id": entry.get("drive_id"),
        "suffix": os.path.basename(path)[len(entry["name"]):],
    }
    if not quiet:
        if result["suffix"]:
            print(f"  note   : matched pinned '{entry['name']}' (file name has extra suffix)")
        print(f"  size   : {size} bytes")
        print(f"  md5    : {actual_md5}")
        print(f"  pinned : {expected_md5}")
        print("  G0 gate: ok (size + MD5)")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", required=True)
    parser.add_argument("--lock", default=DEFAULT_LOCK)
    parser.add_argument("--name", help="expected base name (Stage input name)")
    parser.add_argument("--role", help="pinned role, e.g. donor-gsi-primary")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        lock = load_lock(args.lock)
        result = check(lock, args.file, name=args.name, role=args.role,
                       quiet=args.quiet or args.json)
    except (OSError, ValueError, GateError) as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
