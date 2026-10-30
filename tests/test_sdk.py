import asyncio
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import helpers
from kingsteam.catalog import Catalog
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
        self.catalog.sdk_dir = self.runtime.root / "sdk"

    def install_fake_runtime(self):
        for name in REQUIRED:
            path = self.runtime.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"x")
        (self.runtime.root / "runtime.json").write_text(json.dumps({"version": "t", "default_variant": "fsr4-lite"}))

    def test_manifest_pins_the_sdk_dll(self):
        asset = Catalog(helpers.ROOT, self.tmp).assets["fsr_sdk"]
        self.assertTrue(asset["url"].startswith("https://raw.githubusercontent.com/GPUOpen-LibrariesAndSDKs/FidelityFX-SDK/"))
        self.assertEqual(len(asset["sha256"]), 64)

    def test_nothing_happens_without_a_runtime(self):
        asyncio.run(self.runtime.ensure_sdk())
        self.assertFalse((self.runtime.root / "sdk").exists())

    def test_download_is_placed_and_listed_as_lite(self):
        self.install_fake_runtime()

        async def fake(destination):
            destination.write_bytes(DATA)
        self.runtime._fetch_sdk = fake
        asyncio.run(self.runtime.ensure_sdk())
        entries = {e["id"]: e for e in self.catalog.community()}
        self.assertIn("sdk/fsr412-lite", entries)
        self.assertEqual(entries["sdk/fsr412-lite"]["base"], "fsr4-lite")
        self.assertEqual(entries["sdk/fsr412-lite"]["path"].read_bytes(), DATA)

    def test_wrong_hash_is_refused(self):
        self.install_fake_runtime()

        async def fake(destination):
            destination.write_bytes(b"tampered")
        self.runtime._fetch_sdk = fake
        asyncio.run(self.runtime.ensure_sdk())
        self.assertFalse(self.runtime.sdk_folder().exists())


if __name__ == "__main__":
    unittest.main()
