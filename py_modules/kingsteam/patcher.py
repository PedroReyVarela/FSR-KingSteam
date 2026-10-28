"""Transactional install/removal of the OptiScaler payload inside a game folder.

Everything we write is recorded with its hash in `.kingsteam-files.json`; the files we replace are
saved in `.kingsteam-backups`. All changes of one operation are applied together or rolled back.
A managed file that the user changed afterwards (a game fix, say) is never overwritten or deleted.
"""

import configparser
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from .catalog import PROXIES, UPSCALER
from .util import atomic_write, read_json, sha256_bytes, sha256_file

STATE = ".kingsteam-files.json"
BACKUPS = ".kingsteam-backups"
MARKER = "KINGSTEAM_PATCH"
LEGACY_STATE, LEGACY_BACKUPS, LEGACY_MARKER = ".framegen-files.json", ".framegen-backups", "FRAMEGEN_PATCH"

LOG_DEFAULTS = {"Log.LogToFile": "true", "Log.LogLevel": "2"}
EDITABLE_SETTINGS = {
    "Menu.ShowFps": ("true", "false"),
    "Menu.FpsScale": ("1.0", "1.5", "2.0"),
    "Menu.FpsOverlayType": ("0", "1", "2", "3", "4", "5"),
    "Menu.FpsOverlayShowRatio": ("true", "false"),
}


class PatchError(Exception):
    """An error with a stable code, so the service can show a translated message."""

    def __init__(self, code: str, name: str = "", detail: str = ""):
        super().__init__(f"{code}: {name or detail}")
        self.code, self.name, self.detail = code, name, detail


# ── paths ────────────────────────────────────────────────────────────────────

def safe_path(root: Path, name: str) -> Path:
    relative = PurePosixPath(name)
    if relative.is_absolute() or not relative.parts or "\\" in name or any(p in ("..", ".") for p in relative.parts):
        raise PatchError("bad-path", name)
    path = root.joinpath(*relative.parts)
    for parent in [path, *path.parents]:
        if parent == root:
            break
        if parent.is_symlink():
            raise PatchError("symlink", str(parent))
    return path


def is_managed_name(name: str) -> bool:
    return name in PROXIES or name in {"OptiScaler.ini", MARKER} or name.startswith("OptiScaler/")


def is_patched(target: Path) -> bool:
    return (target / STATE).is_file() or (target / LEGACY_STATE).is_file()


# ── ini editing ──────────────────────────────────────────────────────────────

def ini_set(data: bytes, values: dict) -> bytes:
    """Set "Section.Key" entries without dropping comments or the user's other settings."""
    lines = data.decode("utf-8-sig").splitlines()
    for qualified, value in values.items():
        section, key = qualified.split(".", 1)
        start = next((i for i, l in enumerate(lines) if l.strip().lower() == f"[{section}]".lower()), None)
        if start is None:
            lines.extend(["", f"[{section}]", f"{key}={value}"])
            continue
        end = next((i for i in range(start + 1, len(lines)) if lines[i].strip().startswith("[")), len(lines))
        found = False
        for i in range(start + 1, end):
            if lines[i].split("=", 1)[0].strip().lower() == key.lower():
                lines[i] = f"{key}={value}"
                found = True
        if not found:
            lines.insert(end, f"{key}={value}")
    return ("\n".join(lines) + "\n").encode()


def ini_get(data: bytes, qualified: str):
    section, key = qualified.split(".", 1)
    current = None
    for line in data.decode("utf-8-sig", errors="replace").splitlines():
        stripped = line.strip()
        if stripped.startswith("["):
            current = stripped.strip("[]").lower()
        elif current == section.lower() and "=" in stripped and not stripped.startswith(";"):
            name, value = stripped.split("=", 1)
            if name.strip().lower() == key.lower():
                return value.strip()
    return None


def with_preset(data: bytes, overrides: dict) -> bytes:
    """Apply an FSR4 preset and switch file logging on unless the user already chose."""
    merged = dict(overrides)
    for qualified, value in LOG_DEFAULTS.items():
        if ini_get(data, qualified) in (None, "", "auto"):
            merged.setdefault(qualified, value)
    return ini_set(data, merged)


def variant_from_ini(target: Path, variants: dict) -> str | None:
    config = configparser.ConfigParser(strict=False, interpolation=None)
    try:
        config.read(target / "OptiScaler.ini", encoding="utf-8")
        gpu = config.get("FSR", "Fsr4GpuSupport", fallback="auto")
        model = config.get("FSR", "Fsr4Model", fallback="auto")
        dx12 = config.get("Upscalers", "Dx12Upscaler", fallback="auto")
    except configparser.Error:
        return None
    for name, info in variants.items():
        overrides = info["config_overrides"]
        if "FSR.Fsr4GpuSupport" not in overrides:
            if overrides.get("Upscalers.Dx12Upscaler") == dx12:
                return name
        elif dx12 == "ffx" and overrides["FSR.Fsr4GpuSupport"] == gpu and overrides.get("FSR.Fsr4Model") == model:
            return name
    return None


# ── state ────────────────────────────────────────────────────────────────────

def migrate_legacy(target: Path) -> None:
    """Adopt a game patched by FSR-KingSteam 1.0.x (it used the `.framegen-*` names)."""
    legacy_state = target / LEGACY_STATE
    if not legacy_state.is_file() or (target / STATE).exists():
        return
    state = read_json(legacy_state)
    files = state.get("files") if isinstance(state.get("files"), dict) else {}
    if LEGACY_MARKER in files:
        files[MARKER] = files.pop(LEGACY_MARKER)
    state["files"] = files
    legacy_marker, legacy_backups = target / LEGACY_MARKER, target / LEGACY_BACKUPS
    if legacy_marker.is_file() and not (target / MARKER).exists():
        os.replace(legacy_marker, target / MARKER)
    if legacy_backups.is_dir() and not (target / BACKUPS).exists():
        os.replace(legacy_backups, target / BACKUPS)
    atomic_write(target / STATE, json.dumps(state, indent=2).encode())
    legacy_state.unlink(missing_ok=True)


def read_state(target: Path) -> dict:
    migrate_legacy(target)
    path = safe_path(target, STATE)
    if not path.exists():
        return {"files": {}, "backups": []}
    state = json.loads(path.read_text())
    if not isinstance(state.get("files"), dict) or not isinstance(state.get("backups"), list):
        raise PatchError("bad-state")
    for name in [*state["files"], *state["backups"]]:
        if not is_managed_name(name):
            raise PatchError("bad-state", name)
        safe_path(target, name)
        safe_path(target, f"{BACKUPS}/{name}")
    return state


def read_marker(target: Path) -> dict:
    migrate_legacy(target)
    return read_json(target / MARKER)


def _transact(target: Path, writes: dict, removals: list) -> None:
    """Apply all writes/removals or roll every affected file back. Never follows game symlinks."""
    paths = {name: safe_path(target, name) for name in {*writes, *removals}}
    for path in paths.values():
        if path.exists() and not path.is_file():
            raise PatchError("not-file", str(path))
    with tempfile.TemporaryDirectory(prefix="kingsteam-tx-") as temporary:
        undo = {}
        for index, (name, path) in enumerate(paths.items()):
            if path.exists():
                undo[name] = Path(temporary) / str(index)
                shutil.copy2(path, undo[name])
        try:
            # originals are saved before being replaced; the state file is committed last
            for name in sorted(writes, key=lambda n: 0 if n.startswith(BACKUPS + "/") else 1):
                if name != STATE:
                    atomic_write(paths[name], writes[name])
            for name in removals:
                if name != STATE:
                    paths[name].unlink(missing_ok=True)
            if STATE in writes:
                atomic_write(paths[STATE], writes[STATE])
            elif STATE in removals:
                paths[STATE].unlink(missing_ok=True)
        except Exception:
            for name, path in paths.items():
                if name in undo:
                    atomic_write(path, undo[name].read_bytes())
                else:
                    path.unlink(missing_ok=True)
            raise


def _changed(path: Path, expected: str) -> bool:
    return path.exists() and sha256_file(path) != expected


def _prune_empty(target: Path) -> None:
    for folder in (target / "OptiScaler", target / BACKUPS):
        if not folder.is_dir():
            continue
        for path in sorted(folder.rglob("*"), key=lambda p: len(p.parts), reverse=True):
            if path.is_dir() and not path.is_symlink():
                try:
                    path.rmdir()
                except OSError:
                    pass
        try:
            folder.rmdir()
        except OSError:
            pass


# ── operations ───────────────────────────────────────────────────────────────

def patch(target: Path, bundle: Path, dll_name: str, variant: str, variants: dict, marker_extra: dict,
          keep_ini: bool = True) -> dict:
    if dll_name not in PROXIES:
        raise PatchError("bad-proxy", dll_name)
    manifest = read_json(bundle / "runtime.json")
    files = manifest.get("files") or {}
    if not files or variant not in variants:
        raise PatchError("bad-runtime")
    state = read_state(target)
    if (target / LEGACY_MARKER).exists() and not (target / STATE).exists():
        raise PatchError("old-install")

    incoming = {dll_name if name == "OptiScaler.dll" else name for name in files}
    for name, expected in state["files"].items():
        if name in incoming and name not in ("OptiScaler.ini", MARKER) and _changed(safe_path(target, name), expected):
            raise PatchError("file-changed", name)

    payload: dict[str, bytes] = {}
    for name, expected in files.items():
        if name not in ("OptiScaler.dll", "OptiScaler.ini") and not name.startswith("OptiScaler/"):
            raise PatchError("bad-path", name)
        source = safe_path(bundle, name)
        if sha256_file(source) != expected:
            raise PatchError("bundle-corrupt", name)
        payload[dll_name if name == "OptiScaler.dll" else name] = source.read_bytes()

    ini_path = safe_path(target, "OptiScaler.ini")
    base_ini = ini_path.read_bytes() if keep_ini and ini_path.is_file() else payload["OptiScaler.ini"]
    ini = with_preset(base_ini, variants[variant]["config_overrides"])
    config = configparser.ConfigParser(strict=False, interpolation=None)
    config.read_string(ini.decode("utf-8-sig"))
    renames = {}
    for key in ("Dx11Upscaler", "Dx12Upscaler", "VulkanUpscaler"):
        old = config.get("Upscalers", key, fallback="auto")
        if old in ("fsr31", "fsr31_12"):
            renames[f"Upscalers.{key}"] = "ffx" if old == "fsr31" else "ffx_12"
    payload["OptiScaler.ini"] = ini_set(ini, renames) if renames else ini

    marker = {**read_marker(target), **marker_extra, "target_dir": str(target), "dll_name": dll_name,
              "fsr4_variant": variant, "optiscaler_version": manifest.get("version"),
              "patched_at": datetime.now(timezone.utc).isoformat()}
    marker.pop("upscaler", None)  # a fresh install carries the official upscaler
    payload[MARKER] = json.dumps(marker, indent=2).encode()

    writes, removals, kept = dict(payload), [], []
    backups = set(state["backups"])
    for name in state["files"]:  # files of an earlier patch that this one no longer writes (proxy switch)
        if name in payload:
            continue
        existing = safe_path(target, name)
        if name not in ("OptiScaler.ini", MARKER) and _changed(existing, state["files"][name]):
            kept.append(name)  # the user's own version: keep it and its backup, stop managing it
            continue
        if name in backups:
            writes[name] = safe_path(target, f"{BACKUPS}/{name}").read_bytes()
            removals.append(f"{BACKUPS}/{name}")
            backups.discard(name)
        else:
            removals.append(name)
    for name in payload:
        existing = safe_path(target, name)
        if name in state["files"] or not existing.is_file():
            continue
        if name in backups:
            raise PatchError("file-changed", name)  # leftover of a file we stopped managing: the user's
        backup = f"{BACKUPS}/{name}"
        if safe_path(target, backup).exists():
            raise PatchError("stray-backup", backup)
        writes[backup] = existing.read_bytes()
        backups.add(name)
    new_state = {"files": {name: sha256_bytes(data) for name, data in payload.items()}, "backups": sorted(backups)}
    writes[STATE] = json.dumps(new_state, indent=2).encode()
    _transact(target, writes, removals)
    return {"kept_files": kept, "backed_up": sorted(backups), "optiscaler_version": manifest.get("version"),
            "variant": variant}


def unpatch(target: Path) -> dict:
    state = read_state(target)
    if not (target / STATE).exists():
        raise PatchError("not-patched")
    writes, removals, kept = {}, [STATE], []
    for name, expected in state["files"].items():
        path = safe_path(target, name)
        if name not in ("OptiScaler.ini", MARKER) and _changed(path, expected):
            kept.append(name)  # a game fix we must not touch: leave it and its backup
            continue
        if name in state["backups"]:
            writes[name] = safe_path(target, f"{BACKUPS}/{name}").read_bytes()
            removals.append(f"{BACKUPS}/{name}")
        else:
            removals.append(name)
    _transact(target, writes, removals)
    _prune_empty(target)
    return {"kept_files": kept}


def _require_patched(target: Path) -> tuple[dict, Path, Path]:
    state = read_state(target)
    marker_path, ini_path = safe_path(target, MARKER), safe_path(target, "OptiScaler.ini")
    if not (target / STATE).exists() or not marker_path.is_file() or not ini_path.is_file():
        raise PatchError("not-patched")
    return state, marker_path, ini_path


def _commit(target: Path, state: dict, writes: dict) -> None:
    for name, data in writes.items():
        if name != STATE:
            state["files"][name] = sha256_bytes(data)
    writes[STATE] = json.dumps(state, indent=2).encode()
    _transact(target, writes, [])


def set_variant(target: Path, bundle: Path, variant: str, variants: dict, community: dict | None = None) -> dict:
    """Switch the FSR4 model of a patched game: ini preset plus, optionally, the upscaler DLL.

    `community` = {"id": ..., "path": Path} installs that DLL; None puts the bundle's verified DLL back.
    """
    if variant not in variants:
        raise PatchError("bad-runtime")
    state, marker_path, ini_path = _require_patched(target)
    marker = json.loads(marker_path.read_text())
    writes = {"OptiScaler.ini": with_preset(ini_path.read_bytes(), variants[variant]["config_overrides"])}
    manifest = read_json(bundle / "runtime.json")
    if community is None:
        source = safe_path(bundle, UPSCALER)
        if sha256_file(source) != (manifest.get("files") or {}).get(UPSCALER):
            raise PatchError("bundle-corrupt", UPSCALER)
        data = source.read_bytes()
        marker["upscaler"] = {"source": "official", "sha256": sha256_bytes(data)}
    else:
        source = Path(community["path"])
        if source.is_symlink() or not source.is_file() or source.stat().st_size < 1024 * 1024:
            raise PatchError("bad-community")
        data = source.read_bytes()
        marker["upscaler"] = {"source": "community", "id": community["id"], "sha256": sha256_bytes(data)}
    current = safe_path(target, UPSCALER)
    if UPSCALER in state["files"] and _changed(current, state["files"][UPSCALER]):
        raise PatchError("file-changed", UPSCALER)
    writes[UPSCALER] = data
    marker["fsr4_variant"] = variant
    writes[MARKER] = json.dumps(marker, indent=2).encode()
    _commit(target, state, writes)
    return {"variant": variant}


def set_settings(target: Path, pairs: dict) -> None:
    state, _, ini_path = _require_patched(target)
    for key, value in pairs.items():
        if key not in EDITABLE_SETTINGS or value not in EDITABLE_SETTINGS[key]:
            raise PatchError("bad-setting", f"{key}={value}")
    _commit(target, state, {"OptiScaler.ini": ini_set(ini_path.read_bytes(), pairs)})
