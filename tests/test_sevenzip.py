"""Pure-Python 7z reader: needed because Bazzite ships no 7z/bsdtar."""
import hashlib
import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest
import zlib

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("sevenzip_min", ROOT / "py_modules/kingsteam/sevenzip.py")
sz = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sz)
REAL = ROOT / "bin" / "OptiScaler_v10.0.0-pre1_20261024.7z"


def make_7z(files):
    """Smallest valid 7z: one Copy folder with all files (no compression), plain header."""
    data = b"".join(content for _, content in files)
    def num(n):
        assert n < 0x80
        return bytes([n])
    header = b"\x01\x04"
    header += b"\x06" + num(0) + num(1) + b"\x09" + num(len(data)) + b"\x00"
    header += b"\x07\x0b" + num(1) + b"\x00" + num(1) + bytes([0x01]) + b"\x00" + b"\x0c" + num(len(data)) + b"\x00"
    header += b"\x08\x0d" + num(len(files)) + b"\x09" + b"".join(num(len(c)) for _, c in files[:-1])
    header += b"\x0a\x01" + b"".join(struct.pack("<I", zlib.crc32(c)) for _, c in files) + b"\x00"
    header += b"\x00"
    names = b"\x00" + b"".join(n.encode("utf-16-le") + b"\x00\x00" for n, _ in files)
    header += b"\x05" + num(len(files)) + b"\x11" + num(len(names)) + names + b"\x00"
    header += b"\x00"
    start = struct.pack("<QQI", len(data), len(header), zlib.crc32(header))
    return b"7z\xbc\xaf\x27\x1c\x00\x04" + struct.pack("<I", zlib.crc32(start)) + start + data + header


class SevenZipTests(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.tmp = Path(t.name)

    def test_copy_archive_with_exe_prefix_and_member_selection(self):
        archive = make_7z([("a/one.dll", b"first file"), ("b/two.dll", b"second file")])
        sfx = self.tmp / "installer.exe"
        sfx.write_bytes(b"MZ" + b"\x00" * 1000 + archive)
        out = self.tmp / "two.dll"
        sz.extract_members(sfx, {"b/two.dll": out}, offset=1002)
        self.assertEqual(out.read_bytes(), b"second file")
        self.assertFalse((self.tmp / "one.dll").exists())

    def test_missing_member_and_corruption_are_errors(self):
        path = self.tmp / "a.7z"
        path.write_bytes(make_7z([("x.bin", b"abc"), ("y.bin", b"def")]))
        with self.assertRaises(sz.SevenZipError):
            sz.extract_members(path, {"nope.bin": self.tmp / "n"})
        raw = bytearray(path.read_bytes())
        raw[32] ^= 0xFF  # flip a data byte: file CRC must catch it
        path.write_bytes(raw)
        with self.assertRaises(sz.SevenZipError):
            sz.extract_all(path, self.tmp / "out")

    def test_unsafe_paths_are_refused(self):
        path = self.tmp / "evil.7z"
        path.write_bytes(make_7z([("../escape.txt", b"x")]))
        with self.assertRaises(sz.SevenZipError):
            sz.extract_all(path, self.tmp / "out")
        self.assertFalse((self.tmp / "escape.txt").exists())

    def test_not_an_archive(self):
        path = self.tmp / "x.7z"
        path.write_bytes(b"not 7z at all" * 10)
        with self.assertRaises(sz.SevenZipError):
            sz.Archive(path)

    @unittest.skipUnless(REAL.is_file(), "pinned OptiScaler archive not downloaded")
    def test_real_optiscaler_archive_matches_manifest_layout(self):
        out = self.tmp / "opti"
        sz.extract_all(REAL, out)
        upscaler = out / "OptiScaler/amd_fidelityfx_upscaler_dx12.dll"
        import json
        assets = json.loads((ROOT / "data/runtime-assets.json").read_text())
        self.assertEqual(hashlib.sha256(upscaler.read_bytes()).hexdigest(), assets["optiscaler"]["upscaler_sha256"])
        self.assertTrue((out / "OptiScaler.dll").is_file())


if __name__ == "__main__":
    unittest.main()
