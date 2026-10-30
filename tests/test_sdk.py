import asyncio
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import helpers
from kingsteam.catalog import Catalog, UPSCALER
from kingsteam.runtime import REQUIRED, Runtime

DATA = b"S" * 4096


class SdkDllTests(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory(); self.addCleanup(t.cleanup)
        self.tmp = Path(t.name)
        self.catalog = Catalog(helpers.ROOT, self.tmp)
        self.catalog.assets = copy.deepcopy(self.catalog.assets)
        self.catalog.assets["fsr_sdk"]["sha256"] = hashlib.sha256(DATA).hexdigest()
        self.runtime = Runtime(helpers.ROOT, self.tmp / "data", self.catalog, self.tmp)

    def install_fake_runtime(self):
        for name in REQUIRED:
            path = self.runtime.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"old")
        (self.runtime.root / "runtime.json").write_text(json.dumps(
            {"version": "t", "default_variant": "fsr4-lite", "files": {UPSCALER: "0" * 64}}))

    def test_manifest_pins_the_sdk_dll(self):
        asset = Catalog(helpers.ROOT, self.tmp).assets["fsr_sdk"]
        self.assertTrue(asset["url"].startswith("https://raw.githubusercontent.com/GPUOpen-LibrariesAndSDKs/FidelityFX-SDK/"))
        self.assertEqual(len(asset["sha256"]), 64)

    def test_nothing_happens_without_a_runtime(self):
        asyncio.run(self.runtime.ensure_sdk())
        self.assertFalse((self.runtime.root / UPSCALER).exists())

    def test_upscaler_is_swapped_in_place_and_recorded(self):
        self.install_fake_runtime()

        async def fake(destination):
            destination.write_bytes(DATA)
        self.runtime._fetch_sdk = fake
        asyncio.run(self.runtime.ensure_sdk())
        self.assertEqual((self.runtime.root / UPSCALER).read_bytes(), DATA)
        manifest = json.loads((self.runtime.root / "runtime.json").read_text())
        self.assertEqual(manifest["files"][UPSCALER], hashlib.sha256(DATA).hexdigest())
        self.assertEqual(manifest["default_variant"], "fsr4-lite")
        self.assertFalse((self.runtime.root / (UPSCALER + ".new")).exists())

    def test_second_run_downloads_nothing(self):
        self.install_fake_runtime()
        calls = []

        async def fake(destination):
            calls.append(1)
            destination.write_bytes(DATA)
        self.runtime._fetch_sdk = fake
        asyncio.run(self.runtime.ensure_sdk())
        asyncio.run(self.runtime.ensure_sdk())
        self.assertEqual(len(calls), 1)

    def test_wrong_hash_keeps_the_old_dll(self):
        self.install_fake_runtime()

        async def fake(destination):
            destination.write_bytes(b"tampered")
        self.runtime._fetch_sdk = fake
        asyncio.run(self.runtime.ensure_sdk())
        self.assertEqual((self.runtime.root / UPSCALER).read_bytes(), b"old")


if __name__ == "__main__":
    unittest.main()
