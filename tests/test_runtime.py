"""Build the runtime from the real pinned OptiScaler archive (AMD DLLs replaced by stand-ins)."""
import asyncio
import copy
import tempfile
import unittest
from pathlib import Path

import helpers
from kingsteam import patcher
from kingsteam.catalog import Catalog
from kingsteam.runtime import Runtime
from kingsteam.util import sha256_file

ARCHIVE = helpers.ROOT / "bin" / "OptiScaler_v10.0.0-pre1_20261024.7z"


@unittest.skipUnless(ARCHIVE.is_file(), "pinned OptiScaler archive not in bin/")
class RuntimeBuildTests(unittest.TestCase):
    def test_build_then_patch_real_payload(self):
        t = tempfile.TemporaryDirectory(); self.addCleanup(t.cleanup)
        tmp = Path(t.name)
        plugin = tmp / "plugin"
        (plugin / "bin").mkdir(parents=True)
        (plugin / "data").mkdir()
        (plugin / "bin" / ARCHIVE.name).symlink_to(ARCHIVE)
        (plugin / "bin" / "OptiPatcher_rolling.asi").symlink_to(helpers.ROOT / "bin" / "OptiPatcher_rolling.asi")
        catalog = Catalog(helpers.ROOT, tmp)
        assets = copy.deepcopy(catalog.assets)
        for name, entry in assets["amd_driver"]["files"].items():  # stand-ins for AMD's files
            (plugin / "bin" / name).write_bytes(name.encode() * 10)
            entry["sha256"] = sha256_file(plugin / "bin" / name)
        catalog.assets = assets
        runtime = Runtime(plugin, tmp / "data", catalog, tmp)
        info = asyncio.run(runtime.install("fsr4-lite"))
        self.assertEqual(info["default_variant"], "fsr4-lite")
        self.assertTrue((runtime.root / "OptiScaler.dll").is_file())
        game = tmp / "game"; game.mkdir()
        (game / "dxgi.dll").write_bytes(b"orig")
        patcher.patch(game, runtime.root, "dxgi.dll", "fsr4-lite", catalog.variants, {})
        ini = (game / "OptiScaler.ini").read_text()
        self.assertIn("Fsr4GpuSupport=4", ini)
        self.assertIn("LoadAsiPlugins" , (runtime.root / "OptiScaler.ini").read_text())
        patcher.unpatch(game)
        self.assertEqual(sorted(p.name for p in game.iterdir()), ["dxgi.dll"])


if __name__ == "__main__":
    unittest.main()
