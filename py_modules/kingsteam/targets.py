"""Pick the folder to patch inside a game, spot running games, anti-cheat and existing patches."""

import os
import re
import subprocess
from pathlib import Path

from .i18n import tr

BAD_EXE_PARTS = ("crashreport", "eac", "easyanticheat", "beclient", "eosbootstrap", "benchmark",
                 "uninstall", "setup", "launcher", "updater", "bootstrap", "_redist", "prereq")

ANTICHEAT_MARKERS = {
    "easyanticheat": "Easy Anti-Cheat", "beservice": "BattlEye", "beclient": "BattlEye",
    "battleye": "BattlEye", "vgc.exe": "Riot Vanguard", "eaanticheat": "EA Javelin",
    "gameguard": "GameGuard", "xigncode": "XIGNCODE3", "nprotect": "nProtect", "equ8": "EQU8",
}

# Never scan or patch these as a game folder (a shortcut pointing at a launcher in $HOME, etc.).
UNSAFE_ROOTS = {
    "/", "/bin", "/boot", "/dev", "/etc", "/home", "/lib", "/lib64", "/opt", "/proc", "/root", "/run",
    "/sbin", "/srv", "/sys", "/tmp", "/usr", "/var", "/var/home", "/var/mnt", "/var/lib", "/mnt",
    "/media", "/run/media",
}


def is_unsafe_root(path: Path, home: Path) -> bool:
    try:
        resolved = path.resolve()
        home_resolved = home.resolve()
    except OSError:
        return True
    return (str(resolved).rstrip("/") or "/") in UNSAFE_ROOTS or resolved == home_resolved


def check_directory(directory: str, home: Path) -> Path:
    path = Path(directory).expanduser()
    if not path.exists():
        raise FileNotFoundError(tr(f"The folder does not exist: {directory}", f"La carpeta no existe: {directory}"))
    if not path.is_dir():
        raise NotADirectoryError(tr(f"Not a folder: {directory}", f"No es una carpeta: {directory}"))
    if is_unsafe_root(path, home):
        raise ValueError(tr(f"Folder too generic to patch: {path}", f"Carpeta demasiado genérica para parchear: {path}"))
    if not os.access(path, os.W_OK | os.X_OK):
        raise PermissionError(tr(f"No write permission in {directory}", f"Sin permiso de escritura en {directory}"))
    return path


def executables(root: Path | None) -> list[Path]:
    if root is None or not root.is_dir():
        return []
    try:
        return [exe for exe in root.rglob("*.exe") if exe.is_file()]
    except OSError:
        return []


def _normalise(text: str) -> str:
    return text.lower().replace("\\", "/").replace("z:/", "/").replace("//", "/")


def score(exe: Path, root: Path, name: str) -> int:
    path, file = _normalise(str(exe)), exe.name.lower()
    value = 0
    if path.endswith("-win64-shipping.exe"):
        value += 300
    if "shipping.exe" in file:
        value += 220
    if "/binaries/win64/" in path:
        value += 200
    elif "/win64/" in path:
        value += 80
    if exe.parent == root:
        value += 20
    flat = lambda text: re.sub(r"[^a-z0-9]", "", text.lower())
    if flat(name) and flat(name) in flat(exe.stem):
        value += 120
    if flat(root.name) and flat(root.name) in flat(exe.stem):
        value += 90
    value -= 200 * sum(1 for bad in BAD_EXE_PARTS if bad in path)
    return value - len(exe.parts)


def running_executable(candidates: list[Path]) -> Path | None:
    """The candidate whose full path appears in the process list (game is running), if any."""
    if not candidates:
        return None
    try:
        lines = subprocess.run(["ps", "-eo", "args="], capture_output=True, text=True, check=False).stdout.splitlines()
    except OSError:
        return None
    normalised = [_normalise(line) for line in lines]
    best = None
    for exe in candidates:
        path = _normalise(str(exe))
        if any(path in line for line in normalised) and (best is None or len(path) > len(str(best))):
            best = exe
    return best


def is_running(root: Path | None) -> bool:
    return running_executable(executables(root)) is not None


def search_root(target: dict, home: Path) -> Path | None:
    """Folder to look in for a target: install dir for Steam games, shortcut folder otherwise."""
    if target["kind"] == "game":
        return target.get("root")
    start = Path(target["start_dir"]).expanduser() if target.get("start_dir") else None
    if start and start.is_dir() and not is_unsafe_root(start, home):
        return start
    exe = Path(target["exe"]).expanduser()
    if exe.suffix.lower() == ".exe" and exe.parent.is_dir() and not is_unsafe_root(exe.parent, home):
        return exe.parent
    return None


def guess_folder(target: dict, home: Path, directory: str = "") -> tuple[Path, Path | None]:
    """Folder that holds the real game executable. An explicit folder from the user wins."""
    if directory:
        return check_directory(directory, home), None
    root = search_root(target, home)
    if root is None:
        raise ValueError(tr(
            "This shortcut does not point to an .exe with a clear folder (Heroic, Lutris, script?). Pick the game folder yourself.",
            "El acceso directo no apunta a un .exe con carpeta clara (¿Heroic, Lutris, script?). Elige la carpeta del juego a mano."))
    if not root.is_dir():
        raise FileNotFoundError(tr(f"The game folder does not exist: {root}", f"La carpeta del juego no existe: {root}"))
    own = Path(target["exe"]).expanduser() if target["kind"] == "shortcut" else None
    candidates = executables(root)
    if own and own.suffix.lower() == ".exe" and own.is_file() and own not in candidates:
        candidates.append(own)
    if not candidates:
        return root, None
    running = running_executable(candidates)
    if running:
        return running.parent, running
    # the shortcut's own exe gets a bonus, but a real game binary (Unreal "-Win64-Shipping") still beats a launcher stub
    best = max(candidates, key=lambda c: score(c, root, target["name"]) + (150 if c == own else 0))
    return best.parent, best


def detect_anticheat(root: Path | None, home: Path) -> list[str]:
    if root is None or not root.is_dir() or is_unsafe_root(root, home):
        return []
    found: set[str] = set()
    budget, base = 6000, len(root.parts)
    try:
        for current, dirs, files in os.walk(root, followlinks=False):
            if len(Path(current).parts) - base >= 3:
                dirs[:] = []
            for name in [*dirs, *files]:
                budget -= 1
                lowered = name.lower()
                found.update(label for needle, label in ANTICHEAT_MARKERS.items() if needle in lowered)
            if budget <= 0:
                break
    except OSError:
        pass
    return sorted(found)
