"""Decky entry point: FSR-KingSteam. All logic lives in py_modules/kingsteam."""

import asyncio
import logging
from pathlib import Path

import decky

from kingsteam.service import Service

# send the backend's logs to Decky's log
logging.getLogger("kingsteam").parent = decky.logger
logging.getLogger("kingsteam").setLevel(logging.INFO)


class Plugin:
    service: Service

    async def _main(self):
        data_dir = Path(getattr(decky, "DECKY_PLUGIN_RUNTIME_DIR", Path(decky.HOME) / ".local" / "share" / "fsr-kingsteam"))
        self.service = Service(Path(str(decky.HOME)), Path(decky.DECKY_PLUGIN_DIR), data_dir)
        asyncio.create_task(self.service.runtime.ensure_sdk())  # small background download, never blocks the UI
        decky.logger.info("FSR-KingSteam loaded")

    async def _unload(self):
        decky.logger.info("FSR-KingSteam unloaded")

    # every blocking call goes to a worker thread so Steam's UI never waits on the disk
    async def set_language(self, code: str = "en"): return self.service.language(code)
    async def runtime_status(self): return await asyncio.to_thread(self.service.runtime_status)
    async def install(self, variant: str = "fsr4-lite"): return await self.service.install(variant)
    async def install_progress(self): return self.service.progress()
    async def uninstall(self): return await asyncio.to_thread(self.service.uninstall)
    async def set_default_variant(self, variant: str): return await asyncio.to_thread(self.service.set_default_variant, variant)
    async def community_list(self): return await asyncio.to_thread(self.service.community_list)
    async def list_targets(self): return await asyncio.to_thread(self.service.list_targets)
    async def status(self, kind: str, appid: str, directory: str = ""): return await asyncio.to_thread(self.service.status, kind, appid, directory)
    async def patch(self, kind: str, appid: str, directory: str = "", dll_name: str = "dxgi.dll", variant: str = "", current_options: str = ""):
        return await asyncio.to_thread(self.service.patch, kind, appid, directory, dll_name, variant, current_options)
    async def unpatch(self, kind: str, appid: str): return await asyncio.to_thread(self.service.unpatch, kind, appid)
    async def set_variant(self, kind: str, appid: str, variant: str): return await asyncio.to_thread(self.service.set_variant, kind, appid, variant)
    async def extras(self, kind: str, appid: str): return await asyncio.to_thread(self.service.extras, kind, appid)
    async def set_setting(self, kind: str, appid: str, setting: str, enabled: bool): return await asyncio.to_thread(self.service.set_setting, kind, appid, setting, enabled)
    async def diagnose(self, kind: str, appid: str): return await asyncio.to_thread(self.service.diagnose, kind, appid)
    async def log_error(self, error: str): decky.logger.error(f"UI: {error}")
