"""Steam launch options that load the proxy DLL, and how to keep the user's own ones."""

from .catalog import PROXIES


def managed_options(dll_name: str) -> str:
    if dll_name == "OptiScaler.asi":
        return "SteamDeck=0"
    return f"WINEDLLOVERRIDES={dll_name.removesuffix('.dll')}=n,b SteamDeck=0"


def is_managed(options: str) -> bool:
    flat = " ".join((options or "").split())
    if "fgmod/fgmod" in flat:  # written by the plugin this one replaces
        return True
    return any(f"WINEDLLOVERRIDES={name.removesuffix('.dll')}=n,b" in flat for name in PROXIES if name != "OptiScaler.asi")


def original_options(current: str, stored: str) -> str:
    """The user's real launch options, ignoring anything this plugin wrote before."""
    if stored and not is_managed(stored):
        return stored
    return "" if is_managed(current) else (current or "")


def build(original: str, dll_name: str) -> tuple[str, bool]:
    """Put the DLL override in front of the user's options. Returns (options, merged).

    When the user's options already set WINEDLLOVERRIDES we do not guess a merge: the managed
    options replace them and the originals come back on unpatch.
    """
    managed = managed_options(dll_name)
    original = (original or "").strip()
    if not original or "WINEDLLOVERRIDES" in original or "fgmod/fgmod" in original:
        return f"{managed} %command%", False
    if "%command%" in original:
        before, _, after = original.partition("%command%")
        return " ".join(part for part in (managed, before.strip(), "%command%", after.strip()) if part), True
    return f"{managed} %command% {original}", True
