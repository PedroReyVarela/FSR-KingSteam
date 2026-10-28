import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "py_modules"))

from kingsteam.util import sha256_bytes  # noqa: E402


def binary_vdf(shortcuts: list[dict]) -> bytes:
    """Build a shortcuts.vdf the way Steam writes it."""
    def text(key, value):
        return b"\x01" + key.encode() + b"\x00" + value.encode() + b"\x00"

    def number(key, value):
        return b"\x02" + key.encode() + b"\x00" + struct.pack("<i", value)

    out = b"\x00shortcuts\x00"
    for index, entry in enumerate(shortcuts):
        out += b"\x00" + str(index).encode() + b"\x00"
        for key, value in entry.items():
            out += number(key, value) if isinstance(value, int) else text(key, value)
        out += b"\x08"
    return out + b"\x08\x08"


def make_runtime(root: Path, extra_upscaler: bytes = b"U" * 2048) -> Path:
    """A small fake runtime with the same layout as the real one."""
    files = {
        "OptiScaler.dll": b"injector",
        "OptiScaler.ini": b"[Upscalers]\nDx12Upscaler=auto\n[FSR]\nFsr4Model=auto\n[Log]\nLogToFile=auto\n",
        "OptiScaler/amd_fidelityfx_upscaler_dx12.dll": extra_upscaler,
        "OptiScaler/plugins/OptiPatcher.asi": b"patcher",
        "OptiScaler/amd_fidelityfx_loader_dx12.dll": b"l",
        "OptiScaler/amd_fidelityfx_framegeneration_dx12.dll": b"f",
        "OptiScaler/amdxcffx64.dll": b"x",
        "OptiScaler/amdvkffx64.dll": b"v",
    }
    for name, data in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    (root / "runtime.json").write_text(json.dumps({
        "version": "test-1", "default_variant": "fsr4-lite",
        "files": {name: sha256_bytes(data) for name, data in files.items()}}))
    return root
