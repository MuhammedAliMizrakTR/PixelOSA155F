#!/usr/bin/env python3
"""Minimal Android sparse-image -> raw converter (pure python, no deps).
Format: 28-byte header, then chunks: RAW(0xCAC1), FILL(0xCAC2),
DONT_CARE(0xCAC3), CRC32(0xCAC4). Verified byte-exact against lpmake
sparse output in the pipeline dry-run (see docs/ROM_BUILD.md)."""
import struct, sys

def main(src, dst):
    with open(src, "rb") as f, open(dst, "wb") as o:
        hdr = f.read(28)
        magic, major, minor, fh, ch, blk, tblk, tch, csum = struct.unpack("<I4H4I", hdr)
        if magic != 0xED26FF3A:
            sys.exit("not a sparse image (magic %08x)" % magic)
        if major != 1:
            sys.exit("unsupported sparse major version %d" % major)
        for _ in range(tch):
            ctype, _, csz_out, csz_file = struct.unpack("<HHII", f.read(12))
            data_len = csz_file - 12
            if ctype == 0xCAC1:            # RAW
                data = f.read(data_len)
                if len(data) != csz_out * blk:
                    sys.exit("RAW chunk size mismatch")
                o.write(data)
            elif ctype == 0xCAC2:          # FILL: 4-byte pattern
                pat = f.read(4)
                o.write(pat * (csz_out * blk // 4))
            elif ctype == 0xCAC3:          # DON'T CARE -> zeros
                o.write(b"\0" * (csz_out * blk))
            elif ctype == 0xCAC4:          # CRC32 chunk
                f.read(data_len)
            else:
                sys.exit("unknown chunk type %04x" % ctype)
        print("unsparsed -> %d bytes" % o.tell())

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
