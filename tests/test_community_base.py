import json
import tempfile
import unittest
from pathlib import Path

import helpers
from kingsteam.catalog import Catalog


class CommunityBaseTests(unittest.TestCase):
    def make(self, home: Path, name: str, info: dict) -> None:
        folder = home / "FSR4-custom" / name
        folder.mkdir(parents=True)
        (folder / "amd_fidelityfx_upscaler_dx12.dll").write_bytes(b"D" * 2048)
        (folder / "info.json").write_text(json.dumps(info))

    def test_base_preset_comes_from_info_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            self.make(home, "lite", {"name": "SDK Lite", "base": "fsr4-lite"})
            self.make(home, "plain", {"name": "Plain"})
            self.make(home, "bad", {"name": "Bad", "base": "no-such-variant"})
            found = {e["id"]: e["base"] for e in Catalog(helpers.ROOT, home).community()}
            self.assertEqual(found["user/lite"], "fsr4-lite")
            self.assertEqual(found["user/plain"], "fsr4-int8")
            self.assertEqual(found["user/bad"], "fsr4-int8")


if __name__ == "__main__":
    unittest.main()
