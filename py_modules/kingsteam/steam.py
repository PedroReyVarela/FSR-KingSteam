"""Find Steam libraries, installed games, non-Steam shortcuts and the Proton version in use."""

import logging
from pathlib import Path

from .util import strip_quotes
from .vdf import get_ci, parse_binary_vdf, parse_text_vdf, shortcut_appid

log = logging.getLogger("kingsteam")

SKIP_NAMES = ("Proton", "Steam Linux Runtime", "Steamworks Common Redistributables")


def steam_roots(home: Path) -> list[Path]:
    flatpak = home / ".var" / "app" / "com.valvesoftware.Steam"
    candidates = [
        home / ".local" / "share" / "Steam",
        home / ".steam" / "steam",
        home / ".steam" / "root",
        flatpak / "home" / ".local" / "share" / "Steam",
        flatpak / "home" / ".steam" / "steam",
    ]
    seen, roots = set(), []
    for candidate in candidates:
        try:
            key = str(candidate.resolve())
        except OSError:
            key = str(candidate)
        if candidate.is_dir() and key not in seen:
            seen.add(key)
            roots.append(candidate)
    return roots


def library_paths(home: Path) -> list[Path]:
    paths, seen = [], set()

    def add(path: Path):
        key = str(path)
        if key not in seen:
            seen.add(key)
            paths.append(path)

    for root in steam_roots(home):
        add(root)
        library_file = root / "steamapps" / "libraryfolders.vdf"
        if not library_file.is_file():
            continue
        try:
            parsed = parse_text_vdf(library_file.read_text(encoding="utf-8", errors="replace"))
        except (OSError, ValueError) as exc:
            log.error("libraryfolders unreadable %s: %s", library_file, exc)
            continue
        folders = get_ci(parsed, "libraryfolders", {})
        for entry in folders.values() if isinstance(folders, dict) else []:
            if isinstance(entry, dict) and get_ci(entry, "path"):
                add(Path(str(get_ci(entry, "path"))))
            elif isinstance(entry, str):  # very old format: "1" "/path"
                add(Path(entry))
    return paths


def installed_games(home: Path) -> list[dict]:
    games: dict[str, dict] = {}
    for library in library_paths(home):
        steamapps = library / "steamapps"
        if not steamapps.is_dir():
            continue
        for manifest in steamapps.glob("appmanifest_*.acf"):
            try:
                state = get_ci(parse_text_vdf(manifest.read_text(encoding="utf-8", errors="replace")), "AppState", {})
            except (OSError, ValueError) as exc:
                log.error("skipping %s: %s", manifest, exc)
                continue
            appid, name = str(get_ci(state, "appid", "")), str(get_ci(state, "name", ""))
            installdir = str(get_ci(state, "installdir", ""))
            if not appid or not name or any(skip in name for skip in SKIP_NAMES):
                continue
            root = steamapps / "common" / installdir if installdir else None
            games[appid] = {"kind": "game", "appid": appid, "name": name,
                            "root": root if root and root.is_dir() else None, "launch_options": ""}
    return sorted(games.values(), key=lambda g: g["name"].lower())


def shortcut_files(home: Path) -> list[tuple[str, Path]]:
    files, seen = [], set()
    for root in steam_roots(home):
        userdata = root / "userdata"
        if not userdata.is_dir():
            continue
        for user in sorted(userdata.iterdir()):
            candidate = user / "config" / "shortcuts.vdf"
            try:
                key = str(candidate.resolve())
            except OSError:
                key = str(candidate)
            if candidate.is_file() and key not in seen:
                seen.add(key)
                files.append((user.name, candidate))
    return files


def shortcuts(home: Path) -> list[dict]:
    found: dict[str, dict] = {}
    for user, path in shortcut_files(home):
        try:
            parsed = parse_binary_vdf(path.read_bytes())
        except (OSError, ValueError) as exc:
            log.error("could not parse %s: %s", path, exc)
            continue
        container = get_ci(parsed, "shortcuts", {})
        for entry in container.values() if isinstance(container, dict) else []:
            if not isinstance(entry, dict):
                continue
            appid = shortcut_appid(entry)
            name = str(get_ci(entry, "appname", "") or "")
            exe = strip_quotes(str(get_ci(entry, "exe", "") or ""))
            if appid is None or not name or not exe:
                continue
            found[str(appid)] = {
                "kind": "shortcut", "appid": str(appid), "name": name, "exe": exe,
                "start_dir": strip_quotes(str(get_ci(entry, "startdir", "") or "")),
                "launch_options": str(get_ci(entry, "launchoptions", "") or ""),
                "user": user, "root": None,
            }
    return sorted(found.values(), key=lambda s: s["name"].lower())


def compat_tool(home: Path, appid: str) -> str | None:
    """Name of the Proton/compat tool Steam will use for this app (None = unknown)."""
    for root in steam_roots(home):
        config = root / "config" / "config.vdf"
        if not config.is_file():
            continue
        try:
            parsed = parse_text_vdf(config.read_text(encoding="utf-8", errors="replace"))
        except (OSError, ValueError):
            continue
        node = parsed
        for key in ("InstallConfigStore", "Software", "Valve", "Steam", "CompatToolMapping"):
            node = get_ci(node, key, {}) if isinstance(node, dict) else {}
        if not isinstance(node, dict):
            continue
        for key in (str(appid), "0"):
            entry = get_ci(node, key)
            if isinstance(entry, dict) and get_ci(entry, "name"):
                return str(get_ci(entry, "name"))
    return None
