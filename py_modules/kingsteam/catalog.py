"""Pinned runtime assets, FSR4 presets, proxy DLL names and community upscaler DLLs."""

from pathlib import Path

from .i18n import pick
from .util import read_json, sha256_file

PROXIES = ["dxgi.dll", "winmm.dll", "version.dll", "dbghelp.dll", "winhttp.dll", "wininet.dll", "OptiScaler.asi"]
DEFAULT_PROXY = "dxgi.dll"
DEFAULT_VARIANT = "fsr4-lite"
UPSCALER = "OptiScaler/amd_fidelityfx_upscaler_dx12.dll"
COMMUNITY_DLL_NAME = "amd_fidelityfx_upscaler_dx12.dll"
COMMUNITY_BASE_VARIANT = "fsr4-int8"  # community INT8 builds are driven by the INT8 ini settings


class Catalog:
    def __init__(self, plugin_dir: Path, home: Path):
        self.plugin_dir = Path(plugin_dir)
        self.home = Path(home)
        self.assets = read_json(self.plugin_dir / "data" / "runtime-assets.json")
        self.variants: dict = self.assets.get("variants", {})
        self._sha_cache: dict = {}

    def variant_label(self, variant: str | None) -> str | None:
        if not variant:
            return None
        if variant.startswith("community:"):
            entry = self.community_entry(variant[len("community:"):])
            return entry["name"] if entry else None
        info = self.variants.get(variant)
        return pick(info["label"]) if info else None

    def describe(self) -> dict:
        return {
            "variants": [{"id": key, "label": pick(info["label"]), "hint": pick(info["hint"])}
                         for key, info in self.variants.items()],
            "proxies": [{"id": item["id"], "hint": pick(item["hint"])} for item in self.assets.get("proxies", [])],
            "default_variant": DEFAULT_VARIANT,
            "default_proxy": DEFAULT_PROXY,
        }

    def normalise_variant(self, variant: str | None) -> str:
        variant = str(variant or "").strip()
        return variant if variant in self.variants else DEFAULT_VARIANT

    # community DLLs: bundled with the plugin (community/) or dropped by the user in ~/FSR4-custom
    def _roots(self) -> list[tuple[str, Path]]:
        return [("plugin", self.plugin_dir / "community"), ("user", self.home / "FSR4-custom")]

    def community(self) -> list[dict]:
        found = []
        for origin, root in self._roots():
            if not root.is_dir():
                continue
            for folder in sorted(root.iterdir()):
                dll = folder / COMMUNITY_DLL_NAME
                if folder.is_symlink() or dll.is_symlink() or not dll.is_file():
                    continue
                info = read_json(folder / "info.json")
                found.append({"id": f"{origin}/{folder.name}", "name": str(info.get("name") or folder.name),
                              "note": str(info.get("note") or ""), "path": dll})
        return found

    def community_entry(self, entry_id: str) -> dict | None:
        return next((entry for entry in self.community() if entry["id"] == entry_id), None)

    def community_sha(self, dll: Path) -> str:
        stat = dll.stat()
        key = (str(dll), stat.st_size, stat.st_mtime_ns)
        if key not in self._sha_cache:
            self._sha_cache[key] = sha256_file(dll)
        return self._sha_cache[key]
