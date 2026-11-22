#!/usr/bin/env python3
"""Synthetic self-tests for the packaging/verification tools.

These tests use entirely synthetic fixtures written into a temporary
directory. They prove the tooling behaves correctly; they say nothing about
donor firmware, kernel artifacts or the device.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools")
LZ4_MAGIC = b"\x04\x22\x4d\x18"


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, *args], capture_output=True, text=True, check=False
    )


class OdinPackTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        self.boot = os.path.join(self.dir, "boot.img")
        with open(self.boot, "wb") as fh:
            fh.write(b"ANDROID!" + b"\x00" * 4096)
        self.vendor = os.path.join(self.dir, "vendor_boot.img")
        with open(self.vendor, "wb") as fh:
            fh.write(b"ANDROID!" + b"\x01" * 8192)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def pack(self, out: str, *extra: str, members: list[str] | None = None):
        args = [
            os.path.join(TOOLS, "odin_pack.py"),
            "--out",
            out,
            "--manifest",
            out + ".json",
            *extra,
            *(members if members is not None else [self.boot, self.vendor]),
        ]
        return run(*args)

    def test_artifact_is_plain_tar_and_reproducible(self):
        first = self.pack(os.path.join(self.dir, "a.tar"))
        self.assertEqual(first.returncode, 0, first.stderr)
        second = self.pack(os.path.join(self.dir, "b.tar"))
        self.assertEqual(second.returncode, 0, second.stderr)
        with open(os.path.join(self.dir, "a.tar"), "rb") as a, open(
            os.path.join(self.dir, "b.tar"), "rb"
        ) as b:
            self.assertEqual(a.read(), b.read(), "output must be byte-reproducible")
        with open(os.path.join(self.dir, "a.tar.json")) as fh:
            record = json.load(fh)
        self.assertTrue(record["plain_tar"])
        self.assertFalse(record["md5_footer"])
        self.assertEqual(record["size"] % 512, 0)
        self.assertEqual(
            sorted(m["name"] for m in record["members"]), ["boot.img", "vendor_boot.img"]
        )

    def test_creates_missing_output_directory(self):
        out = os.path.join(self.dir, "nested", "deeper", "h.tar")
        result = self.pack(out)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(os.path.isfile(out))

    def test_refuses_to_overwrite(self):
        out = os.path.join(self.dir, "c.tar")
        self.assertEqual(self.pack(out).returncode, 0)
        again = self.pack(out)
        self.assertNotEqual(again.returncode, 0)
        self.assertIn("refusing to overwrite", again.stderr)

    def test_rejects_lz4_member(self):
        compressed = os.path.join(self.dir, "boot.img.lz4")
        with open(compressed, "wb") as fh:
            fh.write(LZ4_MAGIC + b"\x00" * 64)
        result = self.pack(os.path.join(self.dir, "d.tar"), members=[compressed])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("must be raw images", result.stderr)

    def test_rejects_md5_sidecar_name(self):
        sidecar = os.path.join(self.dir, "release.tar.md5")
        with open(sidecar, "wb") as fh:
            fh.write(b"x")
        result = self.pack(os.path.join(self.dir, "e.tar"), members=[sidecar])
        self.assertNotEqual(result.returncode, 0)

    def test_verify_roundtrip_and_tamper(self):
        out = os.path.join(self.dir, "f.tar")
        self.assertEqual(self.pack(out).returncode, 0)
        verify = run(
            os.path.join(TOOLS, "odin_pack.py"),
            "--out",
            out,
            "--manifest",
            out + ".json",
            "--verify",
        )
        self.assertEqual(verify.returncode, 0, verify.stdout + verify.stderr)
        with open(out, "ab") as fh:
            fh.write(b"\x00" * 512)
        tampered = run(
            os.path.join(TOOLS, "odin_pack.py"),
            "--out",
            out,
            "--manifest",
            out + ".json",
            "--verify",
        )
        self.assertNotEqual(tampered.returncode, 0)

    def test_chunks_are_transport_only(self):
        out = os.path.join(self.dir, "g.tar")
        result = self.pack(out, "--chunk-size", "1024")
        self.assertEqual(result.returncode, 0, result.stderr)
        with open(out + ".json") as fh:
            record = json.load(fh)
        chunks = record["chunks"]
        self.assertGreater(len(chunks), 1)
        self.assertEqual(chunks[0]["name"], "g.tar.00")
        self.assertIn("cat g.tar.?? > g.tar", record["join_command"])
        joined_parts = []
        for chunk in chunks:
            with open(os.path.join(self.dir, chunk["name"]), "rb") as fh:
                joined_parts.append(fh.read())
        joined = b"".join(joined_parts)
        with open(out, "rb") as fh:
            self.assertEqual(joined, fh.read())


class TarInspectTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_flags_lz4_member_and_md5_footer(self):
        plain = os.path.join(self.dir, "boot.img")
        with open(plain, "wb") as fh:
            fh.write(b"ANDROID!" + b"\x00" * 1024)
        lz4 = os.path.join(self.dir, "vendor_boot.img")
        with open(lz4, "wb") as fh:
            fh.write(LZ4_MAGIC + b"\x00" * 1024)
        archive = os.path.join(self.dir, "bad.tar")
        result = run(
            os.path.join(TOOLS, "odin_pack.py"),
            "--out",
            archive,
            "--manifest",
            archive + ".json",
            plain,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

        report = run(os.path.join(TOOLS, "tar_inspect.py"), "--json", archive)
        self.assertEqual(report.returncode, 0, report.stderr)
        self.assertEqual(json.loads(report.stdout)[0]["problems"], [])

        # append an Odin MD5 fingerprint: inspector must refuse to call it clean
        with open(archive, "ab") as fh:
            fh.write(b"0" * 32)
        flagged = run(os.path.join(TOOLS, "tar_inspect.py"), "--json", archive)
        self.assertEqual(flagged.returncode, 1)
        payload = json.loads(flagged.stdout)[0]
        self.assertTrue(payload["md5_footer"])
        self.assertTrue(any("MD5" in p for p in payload["problems"]))

    def test_lz4_member_detected(self):
        lz4 = os.path.join(self.dir, "boot.img")
        with open(lz4, "wb") as fh:
            fh.write(LZ4_MAGIC + b"\x00" * 512)
        archive = os.path.join(self.dir, "lz4.tar")
        # build directly with tarfile to bypass odin_pack's own guard
        import tarfile

        with tarfile.open(archive, "w") as tf:
            tf.add(lz4, arcname="boot.img")
        report = run(os.path.join(TOOLS, "tar_inspect.py"), archive)
        self.assertEqual(report.returncode, 1)
        self.assertIn("LZ4", report.stdout)


class VerifyInputsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        self.data = os.path.join(self.dir, "data")
        os.makedirs(self.data)
        self.payload = os.path.join(self.data, "kernel.tar")
        with open(self.payload, "wb") as fh:
            fh.write(b"x" * 5000)
        import hashlib

        self.lock = os.path.join(self.dir, "lock.json")
        with open(self.lock, "w") as fh:
            json.dump(
                {
                    "schema": "nothingosa155f.inputs/1",
                    "subject": "synthetic",
                    "inputs": [
                        {
                            "role": "synthetic-input",
                            "name": "kernel.tar",
                            "drive_id": "synthetic",
                            "size": 5000,
                            "md5": hashlib.md5(b"x" * 5000).hexdigest(),
                        }
                    ],
                },
                fh,
            )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_accepts_matching_input(self):
        result = run(
            os.path.join(TOOLS, "verify_inputs.py"),
            "--dir",
            self.data,
            "--lock",
            self.lock,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_rejects_size_and_hash_mismatch(self):
        with open(self.payload, "ab") as fh:
            fh.write(b"y")
        result = run(
            os.path.join(TOOLS, "verify_inputs.py"),
            "--dir",
            self.data,
            "--lock",
            self.lock,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("size-mismatch", result.stdout)

    def test_missing_input_fails(self):
        os.remove(self.payload)
        result = run(
            os.path.join(TOOLS, "verify_inputs.py"),
            "--dir",
            self.data,
            "--lock",
            self.lock,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("missing", result.stdout)


if __name__ == "__main__":
    unittest.main()
