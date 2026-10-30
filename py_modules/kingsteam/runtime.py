"""Build the shared OptiScaler runtime from the pinned, hash-verified binaries."""

import asyncio
import logging
import os
import re
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from . import sevenzip
from .catalog import Catalog, UPSCALER
from .i18n import tr
from .util import read_json, sha256_file, write_json

log = logging.getLogger("kingsteam")

REQUIRED = [
    "OptiScaler.dll", "OptiScaler.ini", UPSCALER, "runtime.json",
    "OptiScaler/amd_fidelityfx_loader_dx12.dll", "OptiScaler/amd_fidelityfx_framegeneration_dx12.dll",
    "OptiScaler/amdxcffx64.dll", "OptiScaler/amdvkffx64.dll", "OptiScaler/plugins/OptiPatcher.asi",
]


class Runtime:
    def __init__(self, plugin_dir: Path, data_dir: Path, catalog: Catalog, home: Path):
        self.plugin_dir, self.catalog, self.home = Path(plugin_dir), catalog, Path(home)
        self.root = Path(data_dir) / "runtime"
        self.bin = self.plugin_dir / "bin"
        self.progress: dict | None = None

    def _progress(self, step: str, percent: int | None = None) -> None:
        self.progress = {"step": step, "percent": percent}

    def info(self) -> dict | None:
        if not all((self.root / name).is_file() for name in REQUIRED):
            return None
        data = read_json(self.root / "runtime.json")
        variant = self.catalog.normalise_variant(data.get("default_variant"))
        return {"version": data.get("version"), "default_variant": variant,
                "default_variant_label": self.catalog.variant_label(variant)}

    def set_default_variant(self, variant: str) -> str:
        data = read_json(self.root / "runtime.json")
        if not data:
            raise RuntimeError(tr("OptiScaler is not installed. Press Install first.", "OptiScaler no está instalado. Pulsa Instalar primero."))
        variant = self.catalog.normalise_variant(variant)
        data["default_variant"] = variant
        write_json(self.root / "runtime.json", data)
        return variant

    def remove(self) -> bool:
        if self.root.exists():
            shutil.rmtree(self.root)
            return True
        return False

    # ── AMD driver DLLs: downloaded on the device, never redistributed ──────
    async def _ensure_amd_dlls(self) -> None:
        wanted = self.catalog.assets["amd_driver"]["files"]
        missing = [name for name, entry in wanted.items()
                   if not (self.bin / name).is_file() or sha256_file(self.bin / name).lower() != entry["sha256"].lower()]
        if not missing:
            return
        script = self.plugin_dir / "scripts" / "fetch_assets.py"
        if not script.is_file():
            raise RuntimeError(tr(f"Missing {', '.join(missing)} and there is no downloader.",
                                  f"Faltan {', '.join(missing)} y no hay descargador."))
        env = os.environ.copy()
        env.pop("LD_LIBRARY_PATH", None)  # Decky's own libs break the system Python
        if "LD_LIBRARY_PATH_ORIG" in env:
            env["LD_LIBRARY_PATH"] = env["LD_LIBRARY_PATH_ORIG"]
        scratch = self.home / ".cache" / "fsr-kingsteam-tmp"  # the AMD package is large: keep it off a RAM-backed /tmp
        scratch.mkdir(parents=True, exist_ok=True)
        env["TMPDIR"] = str(scratch)
        process = await asyncio.create_subprocess_exec(
            "/usr/bin/python3", "-I", str(script),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT, env=env)
        tail: list[str] = []

        async def pump() -> None:
            async for raw in process.stdout:
                line = raw.decode("utf-8", errors="replace").strip()
                if line.startswith("PROGRESS "):
                    parts = line.split()
                    try:
                        done, total = int(parts[-2]), int(parts[-1])
                        label = " ".join(parts[1:-2])
                        self._progress(tr(f"Downloading {label}", f"Descargando {label}"), done * 100 // total if total else None)
                    except (ValueError, IndexError):
                        pass
                elif line:
                    tail[:] = [*tail, line][-5:]
                    self._progress(tr("Preparing the AMD DLLs", "Preparando las DLL de AMD"))

        try:
            await asyncio.wait_for(pump(), timeout=3600)
            await process.wait()
        except asyncio.TimeoutError:
            process.kill()
            raise RuntimeError(tr("The AMD DLL download took over an hour and was cancelled.",
                                  "La descarga de las DLL de AMD tardó más de una hora y se canceló."))
        finally:
            shutil.rmtree(scratch, ignore_errors=True)
        if process.returncode != 0:
            raise RuntimeError(tr("The AMD DLLs could not be downloaded: ", "No se pudieron descargar las DLL de AMD: ") + " | ".join(tail[-3:]))

    # ── AMD's FSR SDK upscaler DLL (4.1.2 with the Lite model inside): downloaded on the device ──
    def sdk_folder(self) -> Path:
        return self.root / "sdk" / "fsr412-lite"

    async def _fetch_sdk(self, destination: Path) -> None:
        script = self.plugin_dir / "scripts" / "fetch_assets.py"
        env = os.environ.copy()
        env.pop("LD_LIBRARY_PATH", None)
        if "LD_LIBRARY_PATH_ORIG" in env:
            env["LD_LIBRARY_PATH"] = env["LD_LIBRARY_PATH_ORIG"]
        process = await asyncio.create_subprocess_exec(
            "/usr/bin/python3", "-I", str(script), "--sdk-to", str(destination),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT, env=env)
        output, _ = await asyncio.wait_for(process.communicate(), timeout=900)
        if process.returncode != 0:
            raise RuntimeError(output.decode("utf-8", errors="replace").strip()[-300:])

    async def ensure_sdk(self) -> None:
        """Put AMD's FSR SDK DLL next to the runtime, once. Any failure only logs: the rest keeps working."""
        try:
            asset = self.catalog.assets.get("fsr_sdk")
            if not asset or self.info() is None:
                return
            folder = self.sdk_folder()
            dll = folder / "amd_fidelityfx_upscaler_dx12.dll"
            if dll.is_file() and sha256_file(dll).lower() == asset["sha256"].lower():
                return
            scratch = self.home / ".cache" / "fsr-kingsteam-tmp"
            scratch.mkdir(parents=True, exist_ok=True)
            download = scratch / asset["name"]
            try:
                await self._fetch_sdk(download)
                if sha256_file(download).lower() != asset["sha256"].lower():
                    raise RuntimeError("the FSR SDK DLL does not match its pinned hash")
                folder.mkdir(parents=True, exist_ok=True)
                shutil.move(str(download), str(dll))
            finally:
                download.unlink(missing_ok=True)
            write_json(folder / "info.json", {
                "name": tr("FSR 4.1.2 | INT8 Lite (AMD SDK)", "FSR 4.1.2 | INT8 Lite (SDK de AMD)"),
                "base": "fsr4-lite",
                "note": tr("AMD's 4.1.2 DLL with the Lite model inside. Untested on the 890M.",
                           "DLL 4.1.2 de AMD con el Lite incluido. Sin probar en la 890M.")})
        except Exception as exc:  # noqa: BLE001
            log.warning("FSR SDK DLL not available: %s", exc)

    # ── build ──────────────────────────────────────────────────────────────────
    def _build(self, default_variant: str) -> dict:
        assets = self.catalog.assets
        required = [assets["optiscaler"], assets["optipatcher"],
                    *({"name": n, **e} for n, e in assets["amd_driver"]["files"].items())]
        for asset in required:
            if sha256_file(self.bin / asset["name"]).lower() != asset["sha256"].lower():
                raise RuntimeError(tr(f"{asset['name']} does not match its pinned hash.", f"{asset['name']} no coincide con su hash fijado."))
        self.root.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".stage-", dir=self.root.parent) as temporary:
            stage = Path(temporary) / "runtime"
            self._progress(tr("Extracting OptiScaler (a few seconds)", "Extrayendo OptiScaler (unos segundos)"))
            sevenzip.extract_all(self.bin / assets["optiscaler"]["name"], stage)
            if sha256_file(stage / UPSCALER) != assets["optiscaler"]["upscaler_sha256"]:
                raise RuntimeError(tr("The bundled FSR upscaler is not the expected one.", "El escalador FSR incluido no es el esperado."))
            for name in assets["amd_driver"]["files"]:
                shutil.copy2(self.bin / name, stage / "OptiScaler" / name)
            plugins = stage / "OptiScaler" / "plugins"
            plugins.mkdir(parents=True, exist_ok=True)
            shutil.copy2(self.bin / assets["optipatcher"]["name"], plugins / "OptiPatcher.asi")
            ini = stage / "OptiScaler.ini"
            text = ini.read_text(encoding="utf-8-sig")
            text = re.sub(r"(?m)^LoadAsiPlugins\s*=.*$", "LoadAsiPlugins=true", text)
            text = re.sub(r"(?m)^UseHQFont\s*=.*$", "UseHQFont=false", text)
            ini.write_text(text)
            files = {name: sha256_file(stage / name)
                     for name in (str(p.relative_to(stage)) for p in stage.rglob("*") if p.is_file())
                     if name in ("OptiScaler.dll", "OptiScaler.ini") or name.startswith("OptiScaler/")}
            write_json(stage / "runtime.json", {
                "version": assets["optiscaler"]["version"], "default_variant": default_variant,
                "installed_at": datetime.now(timezone.utc).isoformat(), "files": files})
            previous = Path(temporary) / "previous"
            if self.root.exists():
                self.root.rename(previous)
            try:
                stage.rename(self.root)
            except Exception:
                if previous.exists():
                    previous.rename(self.root)
                raise
        return self.info() or {}

    async def install(self, default_variant: str) -> dict:
        variant = self.catalog.normalise_variant(default_variant)
        try:
            self._progress(tr("Checking files", "Comprobando archivos"))
            await self._ensure_amd_dlls()
            info = await asyncio.to_thread(self._build, variant)
            await self.ensure_sdk()
            return info
        finally:
            self.progress = None
