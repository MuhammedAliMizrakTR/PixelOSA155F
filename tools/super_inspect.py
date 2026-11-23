#!/usr/bin/env python3
"""Read Android ``super`` partition metadata without lpdump/lpunpack.

The earlier Colab runs could not parse either the Motorola ``emerald`` donor or
the A155F target because ``lpdump``/``lpunpack`` were not installed; the phase-2
report therefore shows empty partition tables. This tool reads the liblp geometry
and metadata header directly, and handles Android **sparse** images by decoding
only the prefix that metadata lives in (no multi-GB expansion needed).

What it does *not* do: extract partitions. It reports the tables so a port plan
can be made; extraction can happen later with real ``lpunpack`` or a reviewed
extent walker.

Layout used (liblp, Android 10+, major version 10):

    offset 0        reserved            LP_PARTITION_RESERVED_BYTES = 4096
    offset 4096     LpMetadataGeometry   magic 0x616C4467, checksum @8,
                                         metadata_max_size @40, slots @44,
                                         logical_block_size @48
    offset 8192     backup geometry      a second copy of the geometry block
    offset 12288+   LpMetadataHeader     magic 0x414C5030, header_size @8,
                                         header_checksum @12, 5 tables from @44
                                         each {u32 offset, u32 num_entries,
                                               u32 entry_size}

(Verified against real ``lpmake`` output: the header magic sits at 12288, not
8192, because liblp keeps a backup geometry copy.)

Checksums are verified (SHA-256 over the structure with its checksum field
zeroed). If they fail, the tool reports the layout as unverified instead of
printing a guessed table.

Two metadata layouts exist and both are accepted:

* **classic** — the four table descriptors start at header offset 44;
* **v1.x** (current liblp, what ``lpmake`` emits) — header offset 44 holds
  ``tables_size``, 48..80 holds ``tables_checksum``, and the descriptors start at
  offset 80. The table payload begins at ``header_size`` and offsets in the
  descriptors are relative to it.

The layout is chosen by validating the descriptors, and for v1.x the table
payload checksum is verified too, so a corrupted table body is reported instead
of silently mis-parsed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
import sys

SPARSE_MAGIC = 0xED26FF3A
LP_GEOMETRY_MAGIC = 0x616C4467
LP_HEADER_MAGIC = 0x414C5030
RESERVED_BYTES = 4096
GEOMETRY_SIZE = 4096
PARTITION_NAME_LEN = 36
TABLE_NAMES = ["partitions", "extents", "groups", "block_devices", "flags"]
SECTOR = 512
SPARSE_CHUNK_TYPES = {
    0xCAC1: "raw",
    0xCAC2: "fill",
    0xCAC3: "don't-care",
    0xCAC4: "crc32",
}
MAX_PREFIX = 32 * 1024 * 1024  # metadata never needs more than this much prefix


def _cstr(raw: bytes) -> str:
    return raw.split(b"\x00", 1)[0].rstrip().decode("utf-8", "replace")


def parse_sparse_header(blob: bytes) -> dict:
    (magic, major, _minor, file_hdr_sz, chunk_hdr_sz, blk_sz,
     total_blks, total_chunks, _csum) = struct.unpack_from("<IHHHHIIII", blob, 0)
    if magic != SPARSE_MAGIC:
        raise ValueError("not an Android sparse image")
    return {
        "major": major,
        "file_hdr_sz": file_hdr_sz,
        "chunk_hdr_sz": chunk_hdr_sz,
        "blk_sz": blk_sz,
        "total_blks": total_blks,
        "total_chunks": total_chunks,
        "expanded_size": total_blks * blk_sz,
    }


def sparse_prefix(path_or_file, limit: int = MAX_PREFIX) -> tuple[bytes, dict]:
    """Decode the first ``limit`` bytes of the expanded stream of a sparse image."""
    if hasattr(path_or_file, "read"):
        return _sparse_prefix_fh(path_or_file, limit)
    with open(path_or_file, "rb") as fh:
        return _sparse_prefix_fh(fh, limit)


def _sparse_prefix_fh(fh, limit: int = MAX_PREFIX) -> tuple[bytes, dict]:
    if True:
        head = fh.read(28)
        header = parse_sparse_header(head)
        fh.seek(header["file_hdr_sz"])
        out = bytearray()
        chunks = []
        blk = header["blk_sz"]
        while len(out) < limit:
            chunk_start = fh.tell()
            raw = fh.read(header["chunk_hdr_sz"])
            if len(raw) < header["chunk_hdr_sz"]:
                break
            ctype, _res, chunk_sz, total_sz = struct.unpack_from("<HHII", raw, 0)
            name = SPARSE_CHUNK_TYPES.get(ctype, f"unknown-0x{ctype:04x}")
            chunks.append({"type": name, "output_blocks": chunk_sz})
            room = limit - len(out)
            take = min(chunk_sz * blk, room)
            if ctype == 0xCAC1:      # raw: payload follows the header
                out += fh.read(take)
            elif ctype == 0xCAC2:    # fill: a 4-byte value follows the header
                value = fh.read(4)
                value = value if len(value) == 4 else b"\x00\x00\x00\x00"
                out += (value * (take // 4 + 1))[:take]
            elif ctype == 0xCAC3:    # don't care: no payload
                out += b"\x00" * take
            elif ctype == 0xCAC4:    # crc32: 4-byte checksum, no output
                pass
            else:
                break
            # Resync on the declared chunk size: every chunk type carries its own
            # header+payload length, and a desync silently destroys the prefix.
            fh.seek(chunk_start + total_sz)
        return bytes(out), {"sparse": header, "chunks_scanned": len(chunks)}


def verify_geometry(geometry: bytes) -> dict:
    (magic, struct_size) = struct.unpack_from("<II", geometry, 0)
    checksum = geometry[8:40]
    body = bytearray(geometry[:struct_size])
    body[8:40] = b"\x00" * 32
    computed = hashlib.sha256(bytes(body)).digest()
    metadata_max_size, metadata_slot_count, logical_block_size = struct.unpack_from(
        "<III", geometry, 40
    )
    return {
        "magic": f"0x{magic:08x}",
        "magic_ok": magic == LP_GEOMETRY_MAGIC,
        "struct_size": struct_size,
        "checksum_ok": computed == checksum,
        "metadata_max_size": metadata_max_size,
        "metadata_slot_count": metadata_slot_count,
        "logical_block_size": logical_block_size,
    }


EXPECTED_ENTRY_SIZES = [52, 24, 48, 64]  # partitions, extents, groups, block_devices


def _descriptors(header: bytes, start: int, count: int) -> list[tuple[int, int, int]]:
    return [
        struct.unpack_from("<III", header, start + index * 12)
        for index in range(count)
    ]


def detect_layout(header: bytes, header_size: int) -> dict:
    """Pick the table-descriptor layout by requiring an exact entry-size sequence."""
    best = None
    for start, label in ((80, "v1x"), (44, "classic")):
        if header_size < start + 4 * 12:
            continue
        descs = _descriptors(header, start, 4)
        exact = sum(
            1 for index, (_o, _n, size) in enumerate(descs)
            if size == EXPECTED_ENTRY_SIZES[index]
        )
        monotonic = all(
            descs[i][0] <= descs[i + 1][0] for i in range(len(descs) - 1)
        )
        if exact < 4 or not monotonic:
            continue
        candidate = {"label": label, "start": start, "count": 4, "score": exact}
        if label == "v1x":
            candidate["tables_size"] = struct.unpack_from("<I", header, 44)[0]
            candidate["tables_checksum"] = header[48:80]
        if best is None:
            best = candidate
    return best or {"label": "unknown", "start": 44, "count": 0, "score": 0}


def parse_header(header: bytes) -> dict:
    magic, major, minor, header_size = struct.unpack_from("<IHHI", header, 0)
    checksum = header[12:44]
    header_size = max(min(header_size, len(header)), 44)
    body = bytearray(header[:header_size])
    body[12:44] = b"\x00" * 32
    computed = hashlib.sha256(bytes(body)).digest()
    layout = detect_layout(header, header_size)
    tables = {}
    for index, name in enumerate(TABLE_NAMES):
        if index >= layout["count"]:
            tables[name] = {"offset": 0, "num_entries": 0, "entry_size": 0}
            continue
        offset, num_entries, entry_size = struct.unpack_from(
            "<III", header, layout["start"] + index * 12
        )
        tables[name] = {"offset": offset, "num_entries": num_entries,
                        "entry_size": entry_size}
    return {
        "magic": f"0x{magic:08x}",
        "magic_ok": magic == LP_HEADER_MAGIC,
        "major": major,
        "minor": minor,
        "header_size": header_size,
        "checksum_ok": computed == checksum,
        "layout": layout["label"],
        "tables_verified": None,
        "tables": tables,
    }


def parse_tables(header_blob: bytes, header: dict) -> dict:
    out: dict = {"partitions": [], "extents": [], "groups": [], "block_devices": []}
    tables = header["tables"]
    base = header["header_size"]

    def rows(name: str) -> list[bytes]:
        table = tables[name]
        count, size = table["num_entries"], table["entry_size"]
        if not size or count > 1 << 20:
            return []
        start = base + table["offset"]
        available = max(len(header_blob) - start, 0) // size
        count = min(count, available)
        return [
            header_blob[start + i * size: start + (i + 1) * size]
            for i in range(count)
        ]

    for blob in rows("partitions"):
        if len(blob) < 52:
            continue
        name = _cstr(blob[:PARTITION_NAME_LEN])
        attributes, first_extent, num_extents, group_index = struct.unpack_from(
            "<IIII", blob, PARTITION_NAME_LEN
        )
        out["partitions"].append({
            "name": name,
            "attributes": f"0x{attributes:08x}",
            "first_extent_index": first_extent,
            "num_extents": num_extents,
            "group_index": group_index,
        })

    for blob in rows("extents"):
        if len(blob) < 24:
            continue
        num_sectors, target_type, target_data, target_source = struct.unpack_from(
            "<QIIQ", blob, 0
        )
        out["extents"].append({
            "num_sectors": num_sectors,
            "size_bytes": num_sectors * SECTOR,
            "target_type": "linear" if target_type == 0 else
                           ("zero" if target_type == 1 else f"0x{target_type:x}"),
            "target_data": target_data,
            "target_source": target_source,
        })

    for blob in rows("groups"):
        if len(blob) < 48:
            continue
        name = _cstr(blob[:PARTITION_NAME_LEN])
        flags, maximum_size = struct.unpack_from("<IQ", blob, PARTITION_NAME_LEN)
        out["groups"].append({"name": name, "flags": f"0x{flags:08x}",
                              "maximum_size": maximum_size})

    for blob in rows("block_devices"):
        if len(blob) < 64:
            continue
        first_sector, alignment, alignment_offset, size = struct.unpack_from(
            "<QIIQ", blob, 0
        )
        dev_name = _cstr(blob[24:24 + PARTITION_NAME_LEN])
        flags = struct.unpack_from("<I", blob, 24 + PARTITION_NAME_LEN)[0]
        out["block_devices"].append({
            "first_logical_sector": first_sector,
            "alignment": alignment,
            "alignment_offset": alignment_offset,
            "size": size,
            "partition_name": dev_name,
            "flags": f"0x{flags:08x}",
        })
    return out


def describe(prefix: bytes, extra: dict | None = None) -> dict:
    report: dict = {"container": "unknown", "problems": [], **(extra or {})}
    if len(prefix) < RESERVED_BYTES + GEOMETRY_SIZE:
        report["problems"].append("image prefix too short to hold LP geometry")
        return report
    geometry = verify_geometry(prefix[RESERVED_BYTES:RESERVED_BYTES + GEOMETRY_SIZE])
    report["geometry"] = geometry
    if not geometry["magic_ok"]:
        report["problems"].append(
            f"geometry magic {geometry['magic']} is not LP (0x616c4467); "
            "this super does not use liblp metadata"
        )
        return report
    report["container"] = "liblp"
    backup = verify_geometry(
        prefix[RESERVED_BYTES + GEOMETRY_SIZE:RESERVED_BYTES + 2 * GEOMETRY_SIZE]
    )
    report["backup_geometry"] = backup
    if not backup["magic_ok"]:
        report["problems"].append("backup geometry block missing or corrupt")
    elif backup["metadata_max_size"] != geometry["metadata_max_size"]:
        report["problems"].append(
            "primary and backup geometry disagree on metadata_max_size"
        )
    metadata_offset = RESERVED_BYTES + 2 * GEOMETRY_SIZE
    if len(prefix) < metadata_offset + 128:
        report["problems"].append("prefix does not reach the metadata header")
        return report
    header = parse_header(prefix[metadata_offset:metadata_offset + 128])
    report["header"] = header
    if not header["checksum_ok"]:
        report["problems"].append(
            "metadata header checksum mismatch: layout unverified, tables not trusted"
        )
        return report
    if not header["magic_ok"]:
        report["problems"].append("metadata header magic invalid")
        return report
    layout = detect_layout(prefix[metadata_offset:metadata_offset + header["header_size"]],
                           header["header_size"])
    if layout["label"] == "v1x" and layout.get("tables_size"):
        payload_start = metadata_offset + header["header_size"]
        payload = prefix[payload_start:payload_start + layout["tables_size"]]
        verified = hashlib.sha256(payload).digest() == layout["tables_checksum"]
        header["tables_verified"] = verified
        if not verified and len(payload) == layout["tables_size"]:
            report["problems"].append(
                "metadata table payload checksum mismatch: table contents untrusted"
            )
    tables = parse_tables(prefix[metadata_offset:], header)
    report.update(tables)

    used_by_group: dict[int, int] = {}
    for partition in report["partitions"]:
        total = 0
        for index in range(
            partition["first_extent_index"],
            partition["first_extent_index"] + partition["num_extents"],
        ):
            if index < len(report["extents"]):
                total += report["extents"][index]["size_bytes"]
        partition["size_bytes"] = total
        used_by_group[partition["group_index"]] = (
            used_by_group.get(partition["group_index"], 0) + total
        )
    for index, group in enumerate(report["groups"]):
        group["used_bytes"] = used_by_group.get(index, 0)
        group["free_bytes"] = max(group["maximum_size"] - group["used_bytes"], 0)
    report["total_logical_bytes"] = sum(
        p["size_bytes"] for p in report["partitions"]
    )
    report["physical_bytes"] = sum(d["size"] for d in report["block_devices"])
    return report


def inspect_stream(fh, size: int) -> dict:
    """Parse LP metadata from an open, seekable binary stream of known size."""
    fh.seek(0)
    head = fh.read(4)
    if len(head) == 4 and struct.unpack("<I", head)[0] == SPARSE_MAGIC:
        fh.seek(0)
        prefix, extra = sparse_prefix(fh)
        report = describe(prefix, extra)
        report["source"] = "sparse"
    else:
        fh.seek(0)
        prefix = fh.read(min(size, MAX_PREFIX))
        report = describe(prefix, {"source_size": size})
        report["source"] = "raw"
    return report


def inspect(path: str) -> dict:
    with open(path, "rb") as fh:
        return inspect_stream(fh, os.path.getsize(path))


def human(report: dict) -> str:
    lines = [f"container: {report.get('container')} (source {report.get('source')})"]
    sparse = report.get("sparse")
    if sparse:
        lines.append(
            f"sparse   : {sparse['total_chunks']} chunks, block {sparse['blk_sz']} B, "
            f"expanded {sparse['expanded_size']} B"
        )
    geometry = report.get("geometry")
    if geometry:
        lines.append(
            "geometry : magic {magic} ok={magic_ok} checksum_ok={checksum_ok} "
            "metadata_max_size={metadata_max_size} slots={metadata_slot_count} "
            "logical_block={logical_block_size}".format(**geometry)
        )
    header = report.get("header")
    if header:
        lines.append(
            f"header   : v{header['major']}.{header['minor']} "
            f"size={header['header_size']} checksum_ok={header['checksum_ok']}"
        )
    if report.get("groups"):
        lines.append("groups:")
        for group in report["groups"]:
            lines.append(
                f"  - {group['name']:<20} max={group['maximum_size']:>14} "
                f"used={group['used_bytes']:>14} free={group['free_bytes']:>14}"
            )
    if report.get("partitions"):
        lines.append("partitions:")
        for partition in report["partitions"]:
            lines.append(
                f"  - {partition['name']:<22} {partition['size_bytes']:>14} B "
                f"group={partition['group_index']} extents={partition['num_extents']}"
            )
        lines.append(
            f"total logical: {report['total_logical_bytes']} B, "
            f"physical block devices: {report['physical_bytes']} B"
        )
    for problem in report.get("problems", []):
        lines.append(f"PROBLEM: {problem}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if not os.path.isfile(args.image):
        print(f"missing: {args.image}", file=sys.stderr)
        return 2
    report = inspect(args.image)
    print(json.dumps(report, indent=2) if args.json else human(report))
    return 1 if report.get("problems") else 0


if __name__ == "__main__":
    sys.exit(main())
