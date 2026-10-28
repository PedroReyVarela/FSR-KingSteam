#!/usr/bin/env python3
"""Build the Decky ZIP: UI bundle, Python backend, pinned upstream binaries (hash-checked)."""

import hashlib
import json
import zipfile
from pathlib import Path

from fetch_assets import ROOT, verify

SOURCES = [("main.py", "main.py"), ("plugin.json", "plugin.json"), ("package.json", "package.json"),
           ("LICENSE", "LICENSE"), ("THIRD_PARTY.md", "THIRD_PARTY.md"), ("README.md", "README.md"),
           ("scripts/fetch_assets.py", "scripts/fetch_assets.py"), ("data/runtime-assets.json", "data/runtime-assets.json")]
FOLDERS = [("dist", "dist"), ("py_modules", "py_modules"), ("community", "community"), ("licenses", "licenses")]


def package():
    assets = json.loads((ROOT / "data" / "runtime-assets.json").read_text())
    names = [assets[key]["name"] for key in ("optiscaler", "optipatcher")]
    for key in ("optiscaler", "optipatcher"):
        verify(ROOT / "bin" / assets[key]["name"], assets[key]["sha256"])
    # AMD DLLs are NOT redistributed: the plugin downloads them from AMD on the device.
    for name, entry in assets["amd_driver"]["files"].items():
        if (ROOT / "bin" / name).is_file():
            raise RuntimeError(f"bin/{name} is an AMD file and must not be packaged; delete it")
    if not (ROOT / "dist" / "index.js").is_file():
        raise RuntimeError("Run pnpm run build first")
    version = json.loads((ROOT / "package.json").read_text())["version"]
    plugin_name = json.loads((ROOT / "plugin.json").read_text())["name"]
    destination = ROOT / "out" / f"{plugin_name}-{version}.zip"
    destination.parent.mkdir(exist_ok=True)
    files = [(ROOT / source, target) for source, target in SOURCES]
    files += [(ROOT / "bin" / name, "bin/" + name) for name in names]
    for folder, target in FOLDERS:
        for path in sorted((ROOT / folder).rglob("*")):
            if path.is_file() and path.suffix not in (".map", ".pyc") and "__pycache__" not in path.parts:
                files.append((path, str(Path(target) / path.relative_to(ROOT / folder))))
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path, name in sorted(files, key=lambda item: item[1]):
            info = zipfile.ZipInfo(plugin_name + "/" + name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, path.read_bytes())
    checksum = hashlib.sha256(destination.read_bytes()).hexdigest()
    destination.with_suffix(".zip.sha256").write_text(f"{checksum}  {destination.name}\n")
    print(destination)
    print(f"SHA-256: {checksum}")
    return destination


if __name__ == "__main__":
    package()
