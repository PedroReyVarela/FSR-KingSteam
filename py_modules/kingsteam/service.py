"""The plugin's operations. Every method returns a plain dict with "status": "success" | "error"."""

import configparser
import logging
import re
from pathlib import Path

from . import launch, patcher, steam, targets
from .catalog import COMMUNITY_BASE_VARIANT, DEFAULT_PROXY, DEFAULT_VARIANT, PROXIES, Catalog
from .i18n import set_language, tr
from .patcher import PatchError
from .runtime import Runtime
from .util import read_json, write_json

log = logging.getLogger("kingsteam")

KINDS = ("game", "shortcut")


def ok(**fields) -> dict:
    return {"status": "success", **fields}


def fail(message: str, **fields) -> dict:
    return {"status": "error", "message": message, **fields}


def describe_error(error: Exception) -> str:
    if not isinstance(error, PatchError):
        return str(error)
    name = error.name
    table = {
        "file-changed": (
            f"{name} in the game folder was changed after patching (your fix?). Pick another proxy DLL, like winmm.dll or version.dll, so it is not overwritten.",
            f"{name} de la carpeta del juego se modificó después de parchear (¿tu fix?). Elige otra DLL proxy, como winmm.dll o version.dll, para no pisarlo."),
        "bundle-corrupt": (f"The installed runtime is damaged ({name}). Press Reinstall.", f"El runtime instalado está dañado ({name}). Pulsa Reinstalar."),
        "bad-runtime": ("The installed runtime is missing or outdated. Press Reinstall.", "Falta el runtime instalado o está desactualizado. Pulsa Reinstalar."),
        "old-install": ("This game has a patch from a much older plugin. Remove it with that plugin first.", "Este juego tiene un parche de un plugin muy antiguo. Quítalo primero con ese plugin."),
        "not-patched": ("This game is not patched.", "Este juego no está parcheado."),
        "bad-proxy": (f"Invalid proxy DLL name: {name}", f"Nombre de DLL proxy no válido: {name}"),
        "bad-community": ("That community DLL is not valid.", "Esa DLL de comunidad no es válida."),
        "bad-setting": (f"Setting not allowed: {name}", f"Ajuste no permitido: {name}"),
        "symlink": (f"Refusing to follow a symlink: {name}", f"No sigo un enlace simbólico: {name}"),
        "stray-backup": (f"An untracked backup is in the way: {name}", f"Hay una copia de seguridad ajena en medio: {name}"),
        "bad-state": ("The patch record in the game folder is not valid.", "El registro del parche en la carpeta del juego no es válido."),
    }
    en, es = table.get(error.code, (f"Patch error: {error.code} {name}", f"Error de parche: {error.code} {name}"))
    return tr(en, es)


class Service:
    def __init__(self, home: Path, plugin_dir: Path, data_dir: Path):
        self.home = Path(home)
        self.catalog = Catalog(plugin_dir, self.home)
        self.runtime = Runtime(plugin_dir, data_dir, self.catalog, self.home)
        self.registry_path = self.home / ".config" / "fsr-kingsteam" / "targets.json"

    # ── registry: where each target was patched (shortcuts have no fixed install dir) ──
    def _registry(self) -> dict:
        registry = read_json(self.registry_path)
        # adopt shortcuts patched by FSR-KingSteam 1.0.x
        legacy = read_json(self.home / ".config" / "decky-framegen-nonsteam.json")
        for appid, folder in legacy.items():
            registry.setdefault(f"shortcut:{appid}", folder)
        return registry

    def _remember(self, kind: str, appid: str, folder: Path | None) -> None:
        registry = self._registry()
        key = f"{kind}:{appid}"
        if folder is None:
            registry.pop(key, None)
        else:
            registry[key] = str(folder)
        try:
            write_json(self.registry_path, registry)
        except OSError as exc:
            log.error("could not save the target registry: %s", exc)

    # ── targets ──────────────────────────────────────────────────────────────
    def _find(self, kind: str, appid: str) -> dict | None:
        if kind not in KINDS:
            return None
        pool = steam.installed_games(self.home) if kind == "game" else steam.shortcuts(self.home)
        return next((item for item in pool if item["appid"] == str(appid)), None)

    def _patched_folder(self, target: dict) -> Path | None:
        """Folder where this target is patched (registry first, then a scan of its own folder)."""
        remembered = self._registry().get(f"{target['kind']}:{target['appid']}")
        if remembered and patcher.is_patched(Path(remembered)):
            return Path(remembered)
        root = targets.search_root(target, self.home)
        if root is None or not root.is_dir() or targets.is_unsafe_root(root, self.home):
            return None
        try:
            for marker in (*root.rglob(patcher.MARKER), *root.rglob(patcher.LEGACY_MARKER)):
                if marker.is_file():
                    return marker.parent
        except OSError:
            pass
        return None

    def _context(self, kind: str, appid: str):
        target = self._find(kind, appid)
        if target is None:
            return None, tr("Not found in Steam.", "No se encuentra en Steam.")
        return target, None

    def list_targets(self) -> dict:
        games = [{"kind": "game", "appid": g["appid"], "name": g["name"], "installed": g["root"] is not None}
                 for g in steam.installed_games(self.home)]
        shortcuts = [{"kind": "shortcut", "appid": s["appid"], "name": s["name"], "exe": s["exe"], "installed": True}
                     for s in steam.shortcuts(self.home)]
        patched = {key for key, folder in self._registry().items() if patcher.is_patched(Path(folder))}
        for item in (*games, *shortcuts):
            item["patched"] = f"{item['kind']}:{item['appid']}" in patched
        return ok(games=games, shortcuts=shortcuts)

    def _proton(self, target: dict) -> dict:
        tool = steam.compat_tool(self.home, target["appid"])
        match = re.search(r"(?i)proton[- _]?(?:ge[- _]?)?(?:proton)?[- _]?(\d+)", tool or "") if tool else None
        major = int(match.group(1)) if match else None
        return {"name": tool, "major": major, "ge": bool(tool and "ge-proton" in tool.lower())}

    def status(self, kind: str, appid: str, directory: str = "") -> dict:
        target, error = self._context(kind, appid)
        if error:
            return fail(error)
        folder = self._patched_folder(target)
        data = {"kind": kind, "appid": str(appid), "name": target["name"], "patched": folder is not None,
                "launch_options": target.get("launch_options", ""), "proton": self._proton(target)}
        if folder is not None:
            marker = patcher.read_marker(folder)
            variant = self._current_variant(folder, marker)
            dll = marker.get("dll_name", DEFAULT_PROXY)
            data.update(target_dir=str(folder), dll_name=dll, dll_present=(folder / dll).exists(),
                        variant=variant, variant_label=self.catalog.variant_label(variant),
                        optiscaler_version=marker.get("optiscaler_version"), patched_at=marker.get("patched_at"))
        else:
            try:
                data["suggested_dir"] = str(targets.guess_folder(target, self.home, directory)[0])
            except (ValueError, OSError) as exc:
                data["suggestion_error"] = str(exc)
        return ok(**data)

    def _current_variant(self, folder: Path, marker: dict) -> str | None:
        upscaler = marker.get("upscaler")
        if isinstance(upscaler, dict) and upscaler.get("source") == "community":
            dll = folder / "OptiScaler" / "amd_fidelityfx_upscaler_dx12.dll"
            from .util import sha256_file
            if dll.is_file() and sha256_file(dll) == upscaler.get("sha256"):
                return f"community:{upscaler.get('id')}"
        stored = marker.get("fsr4_variant")
        return patcher.variant_from_ini(folder, self.catalog.variants) or (stored if stored in self.catalog.variants else None)

    # ── patch / unpatch ──────────────────────────────────────────────────────
    def patch(self, kind: str, appid: str, directory: str = "", dll_name: str = DEFAULT_PROXY,
              variant: str = "", current_options: str = "") -> dict:
        try:
            if dll_name not in PROXIES:
                return fail(describe_error(PatchError("bad-proxy", dll_name)))
            target, error = self._context(kind, appid)
            if error:
                return fail(error)
            if self.runtime.info() is None:
                return fail(tr("OptiScaler is not installed. Press Install first.", "OptiScaler no está instalado. Pulsa Instalar primero."))
            try:
                folder, exe = targets.guess_folder(target, self.home, directory)
            except (ValueError, OSError) as exc:
                if not self._patched_folder(target):
                    return fail(str(exc), needs_directory=True)
                folder, exe = self._patched_folder(target), None
            if targets.is_running(folder) or targets.is_running(target.get("root")):
                return fail(tr("Close the game before patching.", "Cierra el juego antes de parchear."))
            variant = self.catalog.normalise_variant(variant or self.runtime.info()["default_variant"])
            previous = self._patched_folder(target)
            if previous and not directory:
                folder = previous  # re-patching: stay where the game was patched
            stored = str(patcher.read_marker(previous).get("original_launch_options") or "") if previous else ""
            original = launch.original_options(current_options or target.get("launch_options", ""), stored)
            if previous and previous != folder:
                return fail(tr(f"It is already patched in {previous}. Remove that patch first.",
                               f"Ya está parcheado en {previous}. Quita ese parche primero."))
            result = patcher.patch(folder, self.runtime.root, dll_name, variant, self.catalog.variants,
                                   {"kind": kind, "appid": str(appid), "game_name": target["name"],
                                    "original_launch_options": original})
            self._remember(kind, str(appid), folder)
            options, merged = launch.build(original, dll_name)
            note = ""
            if original and not merged:
                note = tr(" Your previous launch options come back when you remove the patch.",
                          " Tus opciones de inicio anteriores vuelven al quitar el parche.")
            return ok(kind=kind, appid=str(appid), name=target["name"], dll_name=dll_name, target_dir=str(folder),
                      target_exe=str(exe) if exe else None, launch_options=options, original_launch_options=original,
                      variant=variant, variant_label=self.catalog.variant_label(variant),
                      optiscaler_version=result["optiscaler_version"], kept_files=result["kept_files"],
                      message=tr(f"Patched {target['name']} in {folder}.{note}", f"Parcheado {target['name']} en {folder}.{note}"))
        except (PatchError, OSError, ValueError) as exc:
            log.warning("patch failed: %s", exc)
            return fail(describe_error(exc))

    def unpatch(self, kind: str, appid: str) -> dict:
        try:
            target, error = self._context(kind, appid)
            if error:
                return fail(error)
            folder = self._patched_folder(target)
            if folder is None:
                return ok(kind=kind, appid=str(appid), name=target["name"], launch_options=None,
                          message=tr("This game has no patch.", "Este juego no tiene parche."))
            if targets.is_running(folder) or targets.is_running(target.get("root")):
                return fail(tr("Close the game before removing the patch.", "Cierra el juego antes de quitar el parche."))
            original = str(patcher.read_marker(folder).get("original_launch_options") or "")
            result = patcher.unpatch(folder)
            self._remember(kind, str(appid), None)
            message = tr(f"Patch removed from {target['name']}.", f"Parche quitado de {target['name']}.")
            if result["kept_files"]:
                names = ", ".join(result["kept_files"])
                message += " " + tr(f"Kept {names}: it was changed after patching (your fix?). The original stays in .kingsteam-backups.",
                                    f"Se deja {names} como estaba: se modificó después de parchear (¿tu fix?). El original queda en .kingsteam-backups.")
            return ok(kind=kind, appid=str(appid), name=target["name"], launch_options=original,
                      kept_files=result["kept_files"], message=message)
        except (PatchError, OSError, ValueError) as exc:
            log.warning("unpatch failed: %s", exc)
            return fail(describe_error(exc))

    # ── model switch, settings, diagnosis ─────────────────────────────────────
    def _patched_context(self, kind: str, appid: str, need_closed: bool = True):
        target, error = self._context(kind, appid)
        if error:
            return None, None, fail(error)
        folder = self._patched_folder(target)
        if folder is None:
            return None, None, fail(tr("This game is not patched.", "Este juego no está parcheado."))
        if need_closed and (targets.is_running(folder) or targets.is_running(target.get("root"))):
            return None, None, fail(tr("Close the game first (or change it in the OptiScaler menu with Insert).",
                                       "Cierra el juego primero (o cámbialo en el menú de OptiScaler con Insert)."))
        return target, folder, None

    def set_variant(self, kind: str, appid: str, variant: str) -> dict:
        try:
            _, folder, problem = self._patched_context(kind, appid)
            if problem:
                return problem
            community = None
            base = variant
            if variant.startswith("community:"):
                community = self.catalog.community_entry(variant[len("community:"):])
                if community is None:
                    return fail(tr("That community DLL was not found.", "No encuentro esa DLL de comunidad."))
                base = COMMUNITY_BASE_VARIANT
            if base not in self.catalog.variants:
                return fail(tr(f"Unknown variant: {variant}", f"Variante desconocida: {variant}"))
            patcher.set_variant(folder, self.runtime.root, base, self.catalog.variants, community)
            return ok(variant=variant, variant_label=self.catalog.variant_label(variant),
                      message=tr(f"Switched to {self.catalog.variant_label(variant)}.", f"Cambiado a {self.catalog.variant_label(variant)}."))
        except (PatchError, OSError, ValueError) as exc:
            log.warning("set_variant failed: %s", exc)
            return fail(describe_error(exc))

    def extras(self, kind: str, appid: str) -> dict:
        target, error = self._context(kind, appid)
        if error:
            return fail(error)
        folder = self._patched_folder(target)
        root = targets.search_root(target, self.home) or folder
        show_fps = None
        if folder is not None:
            value = patcher.ini_get((folder / "OptiScaler.ini").read_bytes(), "Menu.ShowFps") if (folder / "OptiScaler.ini").is_file() else None
            show_fps = None if value is None else value.lower() == "true"
        return ok(anticheat=targets.detect_anticheat(root, self.home), show_fps=show_fps, proton=self._proton(target))

    def set_setting(self, kind: str, appid: str, setting: str, enabled: bool) -> dict:
        try:
            if setting != "show_fps":
                return fail(tr(f"Unknown setting: {setting}", f"Ajuste desconocido: {setting}"))
            _, folder, problem = self._patched_context(kind, appid)
            if problem:
                return problem
            pairs = {"Menu.ShowFps": "true" if enabled else "false"}
            if enabled:  # biggest size, detailed type, and the render -> output ratio next to it
                pairs.update({"Menu.FpsScale": "2.0", "Menu.FpsOverlayType": "2", "Menu.FpsOverlayShowRatio": "true"})
            patcher.set_settings(folder, pairs)
            return ok(message=tr("Saved.", "Guardado."))
        except (PatchError, OSError, ValueError) as exc:
            return fail(describe_error(exc))

    def diagnose(self, kind: str, appid: str) -> dict:
        """Read OptiScaler.log. Patterns are heuristic, so the raw lines come back too."""
        try:
            _, folder, problem = self._patched_context(kind, appid, need_closed=False)
            if problem:
                return problem
            config = configparser.ConfigParser(strict=False, interpolation=None)
            config.read(folder / "OptiScaler.ini", encoding="utf-8")
            settings = {
                "dx12_upscaler": config.get("Upscalers", "Dx12Upscaler", fallback="auto"),
                "fsr4_gpu_support": config.get("FSR", "Fsr4GpuSupport", fallback="auto"),
                "fsr4_model": config.get("FSR", "Fsr4Model", fallback="auto"),
                "log_to_file": config.get("Log", "LogToFile", fallback="auto"),
            }
            log_path = folder / "OptiScaler.log"
            if not log_path.is_file():
                hint = (tr("Logging is off for this game: patch it again or change the model to turn it on.", "El log está desactivado en este juego: vuelve a parchearlo o cambia de modelo para activarlo.")
                        if settings["log_to_file"].lower() == "false" else
                        tr("No log yet: open the game with the patch on, play a minute and come back.", "Todavía no hay log: abre el juego con el parche puesto, juega un minuto y vuelve aquí."))
                return ok(log_found=False, settings=settings, summary=[hint], lines=[])
            size = log_path.stat().st_size
            with log_path.open("rb") as handle:
                handle.seek(max(0, size - 600_000))
                text = handle.read().decode("utf-8", errors="replace")
            all_lines = [line.strip() for line in text.splitlines() if line.strip()]
            interesting = re.compile(r"fsr ?4|int8|lite|amdxc|amdvk|upscaler|xess|fall ?back|unsupported|not supported|error|fail", re.I)
            lines = [line[:170] for line in all_lines if interesting.search(line)][-14:]
            summary = []
            if re.search(r"fsr ?4", text, re.I):
                summary.append(tr("The log mentions FSR4.", "El log menciona FSR4."))
            if re.search(r"int8[ _-]?lite|\blite\b", text, re.I):
                summary.append(tr("The Lite model appears.", "Aparece el modelo Lite."))
            if re.search(r"xess", text, re.I) and settings["dx12_upscaler"] == "xess":
                summary.append(tr("XeSS appears.", "Aparece XeSS."))
            if re.search(r"fall ?back|falling back|not supported|unsupported", text, re.I):
                summary.append(tr("There are 'fallback' or 'unsupported' messages: it may have fallen back to FSR 3.",
                                  "Hay mensajes de 'fallback' o 'no soportado': puede haber caído a FSR 3."))
            errors = sum(1 for line in all_lines if re.search(r"\berror\b|failed", line, re.I))
            if errors:
                summary.append(tr(f"{errors} lines with an error or failure.", f"{errors} líneas con error o fallo."))
            if not summary:
                summary.append(tr("The log has nothing clear about FSR4; check the lines below.", "El log no tiene nada claro sobre FSR4; revisa las líneas de abajo."))
            return ok(log_found=True, settings=settings, summary=summary, lines=lines, size=size,
                      note=tr("Approximate reading: compare with the OptiScaler menu.", "Lectura aproximada: compara con el menú de OptiScaler."))
        except (OSError, ValueError, configparser.Error) as exc:
            log.exception("diagnose failed")
            return fail(str(exc))

    # ── runtime ──────────────────────────────────────────────────────────────
    def runtime_status(self) -> dict:
        info = self.runtime.info()
        return ok(installed=info is not None, **(info or {}), catalog=self.catalog.describe())

    def community_list(self) -> dict:
        items = [{"id": e["id"], "name": e["name"], "note": e["note"], "sha256": self.catalog.community_sha(e["path"]),
                  "size": e["path"].stat().st_size} for e in self.catalog.community()]
        return ok(dlls=items)

    def set_default_variant(self, variant: str) -> dict:
        try:
            chosen = self.runtime.set_default_variant(variant)
            return ok(default_variant=chosen, default_variant_label=self.catalog.variant_label(chosen))
        except RuntimeError as exc:
            return fail(str(exc))

    async def install(self, variant: str = DEFAULT_VARIANT) -> dict:
        try:
            info = await self.runtime.install(variant)
            return ok(**info, message=tr(f"OptiScaler {info.get('version')} installed.", f"OptiScaler {info.get('version')} instalado."))
        except Exception as exc:  # download, hash and disk errors all end here with a readable message
            log.exception("install failed")
            return fail(tr(f"Installation failed: {exc}", f"Falló la instalación: {exc}"))

    def uninstall(self) -> dict:
        try:
            removed = self.runtime.remove()
            return ok(message=tr("OptiScaler removed. Patched games keep working until you remove their patch.",
                                 "OptiScaler quitado. Los juegos parcheados siguen funcionando hasta que les quites el parche.")
                      if removed else tr("Nothing to remove.", "No hay nada que quitar."))
        except OSError as exc:
            return fail(tr(f"Could not remove it: {exc}", f"No se pudo quitar: {exc}"))

    def progress(self) -> dict:
        return {"active": self.runtime.progress is not None, **(self.runtime.progress or {})}

    def language(self, code: str) -> dict:
        return ok(language=set_language(code))
