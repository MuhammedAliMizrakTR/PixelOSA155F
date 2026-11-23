#!/usr/bin/env python3
"""Reads lpdump/lpdumps output of the stock super (JSON + text) plus the sizes
of the extracted partition images, and emits an lpmake command that rebuilds
super with the GSI as the system partition and stock vendor/product/odm (etc.)
carried byte-identical.

Usage: lp_plan.py <super.json> <super.txt> <parts_dir> <gsi.img> <out_cmd.sh> <super_out>
Exits 1 with a clear message if the layout cannot be rebuilt safely.
"""
import json, os, re, sys

def align(n, a=4096):
    return (n + a - 1) // a * a

json_path, txt_path, parts_dir, gsi_path, out_cmd, super_out = sys.argv[1:7]
jraw = open(json_path, encoding="utf-8", errors="replace").read() if os.path.exists(json_path) else ""
traw = open(txt_path, encoding="utf-8", errors="replace").read() if os.path.exists(txt_path) else ""

meta_max = slots = super_size = None
groups = {}   # name -> max_size (0 = unlimited/default group)
parts = []    # (name, group, readonly)

# --- JSON (real lpdumps -j schema: strings, group_name, block_devices[].name) ---
try:
    j = json.loads(jraw)
    for bd in j.get("block_devices", []):
        if bd.get("name") in ("super", "super_device") or bd.get("partition_name") == "super":
            super_size = int(bd.get("size"))
    for g in j.get("groups", []):
        if g.get("name") and g["name"] != "default":
            groups[g["name"]] = int(g.get("maximum_size") or 0)
    for p in j.get("partitions", []):
        parts.append((p["name"], p.get("group_name") or p.get("group"), True))
except Exception as e:
    print("note: JSON parse failed (%s), using text" % e)

# --- text (metadata block: not present in JSON) ----------------------------
m = re.search(r"Metadata max size:\s*(\d+)", traw)
if m: meta_max = int(m.group(1))
m = re.search(r"Metadata slot count:\s*(\d+)", traw)
if m: slots = int(m.group(1))
if super_size is None:
    m = re.search(r"Partition name:\s*super[\s\S]*?Size:\s*(\d+)\s*bytes", traw)
    if m: super_size = int(m.group(1))
if not parts:
    for pm in re.finditer(r"Name:\s*(\S+)\s*\n\s*Group:\s*(\S+)\s*\n\s*Attributes:\s*(\w+)", traw):
        parts.append((pm.group(1), pm.group(2), pm.group(3) == "readonly"))
    for gm in re.finditer(r"Name:\s*(\S+)\s*\n\s*Maximum size:\s*(\d+)\s*bytes", traw):
        if gm.group(1) != "default":
            groups[gm.group(1)] = int(gm.group(2))

meta_max = meta_max or 65536
slots = slots or 2
if not (super_size and groups and parts):
    print("FATAL: could not parse super layout", file=sys.stderr)
    sys.exit(1)

# --- map partitions to files, substitute the GSI for system ---------------
gsi_size = align(os.path.getsize(gsi_path))
entries = []
for name, group, ro in parts:
    base = name.split("_")[0] if name.endswith(("_a", "_b")) else name
    f = os.path.join(parts_dir, name + ".img")
    if base == "system":
        entries.append((name, group, ro, gsi_size, gsi_path))
    elif os.path.exists(f) and os.path.getsize(f) > 0:
        entries.append((name, group, ro, align(os.path.getsize(f)), f))
    else:
        entries.append((name, group, ro, 0, None))   # empty slot/stub partition

# --- capacity check per group ---------------------------------------------
need = {}
for name, group, ro, size, _ in entries:
    need.setdefault(group, 0)
    need[group] += size
for g, n in need.items():
    cap = groups.get(g, 0)
    head = super_size - 4 * 1024 * 1024          # metadata + rounding reserve
    if cap == 0:
        groups[g] = n
        print(f"note: group {g} had no max; set to needed {n}")
    elif n > cap:
        if n <= head:
            print(f"note: raising group {g} max {cap} -> {n} (fits super {super_size})")
            groups[g] = n
        else:
            print(f"FATAL: group {g} needs {n} bytes, super is {super_size}", file=sys.stderr)
            sys.exit(1)

# --- emit the lpmake command ----------------------------------------------
cmd = ["lpmake", "--metadata-size", str(meta_max), "--metadata-slots", str(slots),
       "--device-size", str(super_size), "--sparse", "--output", super_out]
for g, cap in groups.items():
    cmd += ["--group", f"{g}:{cap}"]
for name, group, ro, size, img in entries:
    ro_s = "readonly" if ro else "none"
    cmd += ["--partition", f"{name}:{ro_s}:{size}:{group}"]
    if img:
        cmd += ["--image", f"{name}={img}"]

with open(out_cmd, "w") as fh:
    fh.write("#!/bin/sh\nset -e\n" + " ".join("'%s'" % c for c in cmd) + "\n")
os.chmod(out_cmd, 0o755)

print(f"super {super_size}, slots {slots}, meta_max {meta_max}, groups {groups}")
for name, group, ro, size, img in entries:
    tag = "<- GSI" if img == gsi_path else (img or "(empty)")
    print(f"  {name:20s} {size:>12d}  {tag}")
print("lpmake plan written to", out_cmd)
