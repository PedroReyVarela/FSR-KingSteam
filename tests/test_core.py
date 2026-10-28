import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import helpers
from kingsteam import i18n, launch, patcher, steam, targets, vdf
from kingsteam.catalog import Catalog
from kingsteam.patcher import PatchError


class VdfTests(unittest.TestCase):
    def test_text_vdf_nested(self):
        parsed = vdf.parse_text_vdf('"libraryfolders"\n{\n "0"\n {\n  "path" "/a b"\n }\n // c\n "1" { "path" "C:\\\\x" }\n}')
        self.assertEqual(parsed["libraryfolders"]["0"]["path"], "/a b")
        self.assertEqual(parsed["libraryfolders"]["1"]["path"], "C:\\x")

    def test_shortcut_appid_from_field_and_crc(self):
        self.assertEqual(vdf.shortcut_appid({"appid": -1}), 0xFFFFFFFF)
        value = vdf.shortcut_appid({"Exe": '"/g.exe"', "AppName": "G"})
        self.assertTrue(value & 0x80000000)

    def test_binary_roundtrip(self):
        data = helpers.binary_vdf([{"appid": -5, "AppName": "Juego", "Exe": '"/x/g.exe"'}])
        parsed = vdf.parse_binary_vdf(data)
        self.assertEqual(parsed["shortcuts"]["0"]["AppName"], "Juego")


class LaunchTests(unittest.TestCase):
    def test_build_cases(self):
        self.assertEqual(launch.build("", "dxgi.dll"), ("WINEDLLOVERRIDES=dxgi=n,b SteamDeck=0 %command%", False))
        self.assertEqual(launch.build("-w 1", "winmm.dll")[0], "WINEDLLOVERRIDES=winmm=n,b SteamDeck=0 %command% -w 1")
        self.assertEqual(launch.build("MANGOHUD=1 %command% -x", "dxgi.dll")[0],
                         "WINEDLLOVERRIDES=dxgi=n,b SteamDeck=0 MANGOHUD=1 %command% -x")
        self.assertFalse(launch.build("WINEDLLOVERRIDES=foo=n %command%", "dxgi.dll")[1])
        self.assertEqual(launch.build("", "OptiScaler.asi")[0], "SteamDeck=0 %command%")

    def test_original_options_never_keeps_managed(self):
        managed = "WINEDLLOVERRIDES=dxgi=n,b SteamDeck=0 %command%"
        self.assertEqual(launch.original_options(managed, ""), "")
        self.assertEqual(launch.original_options(managed, "-fast"), "-fast")
        self.assertEqual(launch.original_options("-x", managed), "-x")


class SteamTests(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory(); self.addCleanup(t.cleanup)
        self.home = Path(t.name)
        root = self.home / ".local/share/Steam"
        (root / "steamapps/common/Cool Game").mkdir(parents=True)
        (root / "steamapps/libraryfolders.vdf").write_text(f'"libraryfolders" {{ "0" {{ "path" "{root}" }} }}')
        (root / "steamapps/appmanifest_10.acf").write_text('"AppState" { "appid" "10" "name" "Cool Game" "installdir" "Cool Game" }')
        (root / "steamapps/appmanifest_11.acf").write_text('"AppState" { "appid" "11" "name" "Proton 9.0" "installdir" "P" }')
        user = root / "userdata/123/config"
        user.mkdir(parents=True)
        (user / "shortcuts.vdf").write_bytes(helpers.binary_vdf([{"appid": -7, "AppName": "Mi Exe", "Exe": '"/games/x/x.exe"', "StartDir": '"/games/x"', "LaunchOptions": "-a"}]))
        (root / "config").mkdir()
        (root / "config/config.vdf").write_text('"InstallConfigStore" { "Software" { "Valve" { "Steam" { "CompatToolMapping" { "0" { "name" "proton_experimental" } "10" { "name" "GE-Proton11-2" } } } } } }')

    def test_games_skip_tools(self):
        games = steam.installed_games(self.home)
        self.assertEqual([g["name"] for g in games], ["Cool Game"])
        self.assertIsNotNone(games[0]["root"])

    def test_shortcuts(self):
        found = steam.shortcuts(self.home)
        self.assertEqual(found[0]["name"], "Mi Exe")
        self.assertEqual(found[0]["exe"], "/games/x/x.exe")
        self.assertEqual(found[0]["launch_options"], "-a")
        self.assertEqual(found[0]["appid"], str(0xFFFFFFF9))

    def test_compat_tool_falls_back_to_default(self):
        self.assertEqual(steam.compat_tool(self.home, "10"), "GE-Proton11-2")
        self.assertEqual(steam.compat_tool(self.home, "999"), "proton_experimental")


class TargetTests(unittest.TestCase):
    def test_shipping_exe_beats_launcher(self):
        t = tempfile.TemporaryDirectory(); self.addCleanup(t.cleanup)
        root = Path(t.name) / "Game"
        (root / "Game/Binaries/Win64").mkdir(parents=True)
        (root / "Launcher.exe").write_bytes(b"x")
        (root / "Game/Binaries/Win64/Game-Win64-Shipping.exe").write_bytes(b"x")
        target = {"kind": "game", "name": "Game", "root": root, "appid": "1"}
        with mock.patch.object(targets, "running_executable", return_value=None):
            folder, exe = targets.guess_folder(target, Path(t.name))
        self.assertEqual(folder, root / "Game/Binaries/Win64")

    def test_unsafe_folder_refused(self):
        with self.assertRaises(ValueError):
            targets.check_directory("/usr", Path("/home/x"))

    def test_anticheat(self):
        t = tempfile.TemporaryDirectory(); self.addCleanup(t.cleanup)
        root = Path(t.name) / "g"
        (root / "EasyAntiCheat").mkdir(parents=True)
        self.assertEqual(targets.detect_anticheat(root, Path("/nonexistent")), ["Easy Anti-Cheat"])


class PatcherTests(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory(); self.addCleanup(t.cleanup)
        self.tmp = Path(t.name)
        self.bundle = helpers.make_runtime(self.tmp / "runtime")
        self.game = self.tmp / "game"; self.game.mkdir()
        self.variants = Catalog(helpers.ROOT, self.tmp).variants

    def patch(self, dll="dxgi.dll", variant="fsr4-lite"):
        return patcher.patch(self.game, self.bundle, dll, variant, self.variants, {"original_launch_options": "-x"})

    def test_patch_backup_and_unpatch_restore(self):
        (self.game / "dxgi.dll").write_bytes(b"original")
        self.patch()
        self.assertEqual((self.game / "dxgi.dll").read_bytes(), b"injector")
        self.assertEqual((self.game / patcher.BACKUPS / "dxgi.dll").read_bytes(), b"original")
        ini = (self.game / "OptiScaler.ini").read_text()
        self.assertIn("Fsr4GpuSupport=4", ini); self.assertIn("LogToFile=true", ini)
        self.assertEqual(patcher.read_marker(self.game)["original_launch_options"], "-x")
        patcher.unpatch(self.game)
        self.assertEqual((self.game / "dxgi.dll").read_bytes(), b"original")
        self.assertEqual(sorted(p.name for p in self.game.iterdir()), ["dxgi.dll"])

    def test_user_fix_survives_unpatch_and_proxy_switch(self):
        (self.game / "dxgi.dll").write_bytes(b"original")
        self.patch()
        (self.game / "dxgi.dll").write_bytes(b"MY FIX")
        self.patch("winmm.dll")  # switching proxy must not touch the fix
        self.assertEqual((self.game / "dxgi.dll").read_bytes(), b"MY FIX")
        self.assertEqual((self.game / "winmm.dll").read_bytes(), b"injector")
        result = patcher.unpatch(self.game)
        self.assertEqual(result["kept_files"], [])  # dxgi no longer managed
        self.assertEqual((self.game / "dxgi.dll").read_bytes(), b"MY FIX")

    def test_unpatch_keeps_changed_managed_file(self):
        (self.game / "dxgi.dll").write_bytes(b"original")
        self.patch()
        (self.game / "dxgi.dll").write_bytes(b"MY FIX")
        result = patcher.unpatch(self.game)
        self.assertEqual(result["kept_files"], ["dxgi.dll"])
        self.assertEqual((self.game / "dxgi.dll").read_bytes(), b"MY FIX")
        self.assertTrue((self.game / patcher.BACKUPS / "dxgi.dll").exists())

    def test_repatch_same_proxy_blocked_when_changed(self):
        self.patch()
        (self.game / "dxgi.dll").write_bytes(b"MY FIX")
        with self.assertRaises(PatchError) as raised:
            self.patch()
        self.assertEqual(raised.exception.code, "file-changed")

    def test_corrupt_bundle_changes_nothing(self):
        (self.bundle / "OptiScaler.dll").write_bytes(b"tampered")
        with self.assertRaises(PatchError):
            self.patch()
        self.assertEqual(list(self.game.iterdir()), [])

    def test_symlink_refused(self):
        (self.game / "OptiScaler").symlink_to(self.tmp)
        with self.assertRaises(PatchError):
            self.patch()

    def test_variant_switch_and_community(self):
        self.patch()
        patcher.set_variant(self.game, self.bundle, "fsr4-int8", self.variants)
        self.assertEqual(patcher.variant_from_ini(self.game, self.variants), "fsr4-int8")
        dll = self.tmp / "c.dll"; dll.write_bytes(b"C" * 2_000_000)
        patcher.set_variant(self.game, self.bundle, "fsr4-int8", self.variants, {"id": "user/x", "path": dll})
        self.assertEqual((self.game / patcher.UPSCALER).read_bytes(), dll.read_bytes())
        patcher.set_variant(self.game, self.bundle, "fsr4-lite", self.variants)
        self.assertEqual((self.game / patcher.UPSCALER).read_bytes(), b"U" * 2048)
        patcher.unpatch(self.game)
        self.assertEqual(list(self.game.iterdir()), [])

    def test_settings_allowlist(self):
        self.patch()
        patcher.set_settings(self.game, {"Menu.ShowFps": "true", "Menu.FpsScale": "2.0"})
        self.assertEqual(patcher.ini_get((self.game / "OptiScaler.ini").read_bytes(), "Menu.FpsScale"), "2.0")
        with self.assertRaises(PatchError):
            patcher.set_settings(self.game, {"Log.LogLevel": "9"})
        patcher.unpatch(self.game)  # ini edits are ours, so removal is clean
        self.assertEqual(list(self.game.iterdir()), [])

    def test_adopts_1_0_x_install(self):
        """A game patched by the previous plugin generation keeps working and can be removed."""
        (self.game / "dxgi.dll").write_bytes(b"original")
        self.patch()
        # rewrite to the old names
        state = json.loads((self.game / patcher.STATE).read_text())
        state["files"]["FRAMEGEN_PATCH"] = state["files"].pop(patcher.MARKER)
        (self.game / patcher.STATE).rename(self.game / ".framegen-files.json")
        (self.game / ".framegen-files.json").write_text(json.dumps(state))
        (self.game / patcher.MARKER).rename(self.game / "FRAMEGEN_PATCH")
        (self.game / patcher.BACKUPS).rename(self.game / ".framegen-backups")
        self.assertTrue(patcher.is_patched(self.game))
        patcher.unpatch(self.game)
        self.assertEqual((self.game / "dxgi.dll").read_bytes(), b"original")
        self.assertEqual(sorted(p.name for p in self.game.iterdir()), ["dxgi.dll"])


class ServiceTests(unittest.TestCase):
    def setUp(self):
        from kingsteam.service import Service
        t = tempfile.TemporaryDirectory(); self.addCleanup(t.cleanup)
        self.home = Path(t.name) / "home"
        root = self.home / ".local/share/Steam"
        self.game = root / "steamapps/common/Cool"
        (self.game / "bin").mkdir(parents=True)
        (self.game / "bin/cool.exe").write_bytes(b"x")
        (root / "steamapps/appmanifest_10.acf").write_text('"AppState" { "appid" "10" "name" "Cool" "installdir" "Cool" }')
        self.fix_dir = Path(t.name) / "fixgame"; self.fix_dir.mkdir()
        (self.fix_dir / "g.exe").write_bytes(b"x")
        user = root / "userdata/1/config"; user.mkdir(parents=True)
        (user / "shortcuts.vdf").write_bytes(helpers.binary_vdf([
            {"appid": -9, "AppName": "Fixed", "Exe": f'"{self.fix_dir}/g.exe"', "StartDir": f'"{self.fix_dir}"'}]))
        data = Path(t.name) / "data"
        helpers.make_runtime(data / "runtime")
        self.service = Service(self.home, helpers.ROOT, data)
        i18n.set_language("en")
        self.running = mock.patch.object(targets, "running_executable", return_value=None)
        self.running.start(); self.addCleanup(self.running.stop)

    def test_steam_game_roundtrip_and_status(self):
        result = self.service.patch("game", "10", current_options="-skip")
        self.assertEqual(result["status"], "success", result)
        self.assertEqual(result["launch_options"], "WINEDLLOVERRIDES=dxgi=n,b SteamDeck=0 -skip %command%".replace("-skip %command%", "%command% -skip"))
        status = self.service.status("game", "10")
        self.assertTrue(status["patched"]); self.assertEqual(status["variant"], "fsr4-lite")
        self.assertTrue(self.service.list_targets()["games"][0]["patched"])
        # re-patch with a different proxy: the real original options are kept, not the managed ones
        again = self.service.patch("game", "10", dll_name="winmm.dll", current_options=result["launch_options"])
        self.assertEqual(again["original_launch_options"], "-skip")
        undone = self.service.unpatch("game", "10")
        self.assertEqual(undone["launch_options"], "-skip")
        self.assertFalse(self.service.status("game", "10")["patched"])

    def test_shortcut_with_user_fix_in_dxgi(self):
        appid = str(0xFFFFFFF7)
        (self.fix_dir / "dxgi.dll").write_bytes(b"FIX")
        patched = self.service.patch("shortcut", appid, dll_name="winmm.dll")
        self.assertEqual(patched["status"], "success", patched)
        self.assertEqual((self.fix_dir / "dxgi.dll").read_bytes(), b"FIX")
        self.assertEqual(self.service.unpatch("shortcut", appid)["status"], "success")
        self.assertEqual((self.fix_dir / "dxgi.dll").read_bytes(), b"FIX")

    def test_changed_file_error_is_readable(self):
        self.service.patch("game", "10")
        (self.game / "bin/dxgi.dll").write_bytes(b"x")
        result = self.service.patch("game", "10")
        self.assertEqual(result["status"], "error")
        self.assertIn("winmm.dll", result["message"])
        i18n.set_language("es")
        self.assertIn("Elige otra DLL", self.service.patch("game", "10")["message"])

    def test_patch_requires_runtime_and_known_proxy(self):
        self.assertEqual(self.service.patch("game", "10", dll_name="evil.dll")["status"], "error")
        self.assertEqual(self.service.patch("game", "404")["status"], "error")

    def test_running_game_blocks(self):
        with mock.patch.object(targets, "running_executable", return_value=Path("x")):
            self.assertIn("Close", self.service.patch("game", "10")["message"])

    def test_extras_and_settings(self):
        self.service.patch("game", "10")
        self.assertFalse(self.service.extras("game", "10")["show_fps"])
        self.assertEqual(self.service.set_setting("game", "10", "show_fps", True)["status"], "success")
        self.assertTrue(self.service.extras("game", "10")["show_fps"])
        self.assertEqual(self.service.set_setting("game", "10", "nope", True)["status"], "error")

    def test_variant_and_diagnose(self):
        self.service.patch("game", "10")
        self.assertEqual(self.service.set_variant("game", "10", "xess")["status"], "success")
        self.assertEqual(self.service.status("game", "10")["variant"], "xess")
        self.assertFalse(self.service.diagnose("game", "10")["log_found"])
        (self.game / "bin/OptiScaler.log").write_text("FSR4 init\nfalling back\nERROR x\n")
        diagnosis = self.service.diagnose("game", "10")
        self.assertTrue(diagnosis["log_found"]); self.assertGreaterEqual(len(diagnosis["summary"]), 2)

    def test_catalog_is_bilingual(self):
        i18n.set_language("es")
        labels = [v["label"] for v in self.service.runtime_status()["catalog"]["variants"]]
        self.assertTrue(any("oficial" in l for l in labels))
        i18n.set_language("en")
        self.assertTrue(any("official" in v["label"] for v in self.service.runtime_status()["catalog"]["variants"]))


if __name__ == "__main__":
    unittest.main()
