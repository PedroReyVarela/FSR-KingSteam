#!/usr/bin/env python3
"""Fetch pinned upstream assets over verified HTTPS. Never run the AMD EXE."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import ssl
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "data" / "runtime-assets.json"


def load_sevenzip():
    import importlib.util
    candidate = ROOT / "py_modules" / "kingsteam" / "sevenzip.py"
    spec = importlib.util.spec_from_file_location("kingsteam_sevenzip", candidate)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify(path, expected):
    if sha256(path) != expected:
        raise ValueError(f"SHA-256 mismatch: {path.name}")


def download(asset, destination):
    request = urllib.request.Request(asset["url"], headers={"User-Agent": "FSR-KingSteam/2.0", "Referer": "https://www.amd.com/"})
    if not asset["url"].startswith("https://"):
        raise ValueError("Only HTTPS sources are allowed")
    with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as handle:
        temporary = Path(handle.name)
        try:
            with urllib.request.urlopen(request, timeout=300, context=ssl.create_default_context()) as response:
                if not response.url.startswith("https://"):
                    raise ValueError("Insecure download redirect")
                total = int(response.headers.get("Content-Length") or 0)
                done = 0
                last = -1
                while True:
                    block = response.read(1024 * 1024)
                    if not block:
                        break
                    handle.write(block)
                    done += len(block)
                    percent = int(done * 100 / total) if total else -1
                    if percent != last:
                        last = percent
                        print(f"PROGRESS {asset['name']} {done} {total}", flush=True)
            handle.close()
            verify(temporary, asset["sha256"])
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)


def fetch(amd_package=None, skip_amd=False):
    manifest = json.loads(MANIFEST.read_text())
    binary_dir = ROOT / "bin"
    binary_dir.mkdir(exist_ok=True)
    for key in ("optiscaler", "optipatcher"):
        asset = manifest[key]
        destination = binary_dir / asset["name"]
        if not destination.is_file() or sha256(destination) != asset["sha256"]:
            print(f"Downloading {asset['name']}", flush=True)
            download(asset, destination)
        verify(destination, asset["sha256"])

    if skip_amd:  # packaging: AMD's files are never redistributed
        print("Pinned OptiScaler and OptiPatcher verified.")
        return
    driver = manifest["amd_driver"]
    if all((binary_dir / name).is_file() and sha256(binary_dir / name) == entry["sha256"]
           for name, entry in driver["files"].items()):
        print("All pinned runtime assets verified.")
        return
    with tempfile.TemporaryDirectory(prefix="framegen-amd-") as temporary:
        work = Path(temporary)
        package = Path(amd_package) if amd_package else work / driver["name"]
        if not amd_package:
            print("Downloading AMD driver package for DLL extraction only", flush=True)
            download(driver, package)
        verify(package, driver["sha256"])
        extracted = {}
        for name, entry in driver["files"].items():
            extracted[name] = work / name
        # Extract only the two named members, never arbitrary archive paths.
        load_sevenzip().extract_members(
            package, {entry["member"]: extracted[name] for name, entry in driver["files"].items()},
            offset=driver["archive_offset"],
        )
        for name, entry in driver["files"].items():
            verify(extracted[name], entry["sha256"])
            shutil.copy2(extracted[name], binary_dir / name)
    print("All pinned runtime assets verified.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--amd-package", type=Path, help="Reuse the exact pinned AMD installer downloaded from AMD")
    parser.add_argument("--skip-amd", action="store_true", help="Only fetch the files that go inside the ZIP")
    arguments = parser.parse_args()
    fetch(arguments.amd_package, arguments.skip_amd)
