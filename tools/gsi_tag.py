#!/usr/bin/env python3
"""Derive the build TAG that goes into the AP file name from a GSI file name.

The AP name contract is::

    AP_SM-A155F_PixelOS-<TAG>_<kernel>_<FW_VERSION>.tar

Mystic GSI Updates names its builds two different ways:

    Pixel-cheetah-CinnamonBun-14911996-AB-20260227-MysticGSI.zip   (codename token)
    Pixel-raven-17-15063635-AB-20260327-MysticGSI.zip              (numeric token)

Splitting on '-' and taking field 3 produced ``ACinnamonBun`` for the first
shape, so the Android level is resolved from the *content* of the tokens:

1. first token that is a plain integer in 9..25 (a build id and a date never are),
2. otherwise a known Android codename (CinnamonBun = 17, Baklava = 16,
   VanillaIceCream = 15),
3. otherwise ``unknown`` (the build continues, the name stays honest).

Usage::

    python3 tools/gsi_tag.py /path/Pixel-cheetah-CinnamonBun-...-MysticGSI.zip
    -> cheetah-A17
    python3 tools/gsi_tag.py --version ...   # prints just 17

Diagnostics go to stderr; stdout carries only the tag/version so shell command
substitution stays clean.
"""

from __future__ import annotations

import argparse
import os
import re
import sys

# Android dessert codenames used by the GSI projects this repo consumes.
CODENAMES = {
    "vanillaicecream": 15,
    "baklava": 16,
    "cinnamonbun": 17,
}

MIN_LEVEL, MAX_LEVEL = 9, 25


def android_level(name: str) -> int | None:
    tokens = re.split(r"[-_]", name)
    for token in tokens:
        if token.isdigit() and MIN_LEVEL <= int(token) <= MAX_LEVEL:
            return int(token)
    joined = name.lower()
    for codename, level in CODENAMES.items():
        if codename in joined:
            return level
    return None


def codename(name: str) -> str:
    base = os.path.basename(name)
    for suffix in (".zip", ".img", ".gz"):
        if base.lower().endswith(suffix):
            base = base[: -len(suffix)]
    tokens = [t for t in base.split("-") if t]
    # <vendor>-<codename>-... ; fall back to the vendor token for odd names
    return tokens[1] if len(tokens) > 1 else (tokens[0] if tokens else "unknown")


def build_tag(name: str) -> str:
    level = android_level(name)
    suffix = f"A{level}" if level is not None else "Aunknown"
    return f"{codename(name)}-{suffix}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("gsi", help="GSI file name (a path is fine)")
    parser.add_argument("--version", action="store_true",
                        help="print only the Android level")
    args = parser.parse_args(argv)

    base = os.path.basename(args.gsi)
    level = android_level(base)
    if level is None:
        print(f"note: no Android level in '{base}'; TAG uses Aunknown", file=sys.stderr)
    upper = base.upper()
    if not re.search(r"(^|[-_])A?B([-_]|$)", upper) and "AONLY" not in upper:
        print(f"note: '{base}' does not advertise an AB slot layout in its name",
              file=sys.stderr)
    if args.version:
        print(level if level is not None else "unknown")
    else:
        print(build_tag(base))
    return 0


if __name__ == "__main__":
    sys.exit(main())
