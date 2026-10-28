"""Readers for the two Valve formats we need: text KeyValues and binary shortcuts.vdf."""

import re
import struct
import zlib

_TOKEN = re.compile(r'"((?:[^"\\]|\\.)*)"|([{}])')
_ESCAPES = re.compile(r"\\(.)")


def _unescape(text: str) -> str:
    return _ESCAPES.sub(lambda m: {"n": "\n", "t": "\t"}.get(m.group(1), m.group(1)), text)


def parse_text_vdf(text: str) -> dict:
    """Parse Valve's text KeyValues (libraryfolders.vdf, appmanifest_*.acf, config.vdf)."""
    text = re.sub(r"(?m)^\s*//.*$", "", text)
    tokens = _TOKEN.findall(text)
    position = 0

    def read_map(depth: int = 0) -> dict:
        nonlocal position
        if depth > 32:
            raise ValueError("Text VDF nested too deeply")
        result: dict = {}
        while position < len(tokens):
            quoted, brace = tokens[position]
            if brace == "}":
                position += 1
                return result
            if brace == "{":
                position += 1  # stray block, skip its content
                read_map(depth + 1)
                continue
            key = _unescape(quoted)
            position += 1
            if position >= len(tokens):
                break
            value, opening = tokens[position]
            if opening == "{":
                position += 1
                result[key] = read_map(depth + 1)
            elif opening == "}":
                break
            else:
                result[key] = _unescape(value)
                position += 1
        return result

    return read_map()


def get_ci(mapping: dict, key: str, default=None):
    """Case-insensitive key lookup (Steam is not consistent about key case)."""
    for name, value in mapping.items():
        if name.lower() == key.lower():
            return value
    return default


def parse_binary_vdf(data: bytes) -> dict:
    """Parse Valve's binary KeyValues format (userdata/*/config/shortcuts.vdf)."""
    position = 0
    length = len(data)

    def read_string() -> str:
        nonlocal position
        end = data.find(b"\x00", position)
        if end < 0:
            raise ValueError("Unterminated string in binary VDF")
        text = data[position:end].decode("utf-8", errors="replace")
        position = end + 1
        return text

    def read_map(depth: int = 0) -> dict:
        nonlocal position
        if depth > 16:
            raise ValueError("Binary VDF nested too deeply")
        result: dict = {}
        while position < length:
            kind = data[position]
            position += 1
            if kind == 0x08:
                return result
            key = read_string()
            if kind == 0x00:
                result[key] = read_map(depth + 1)
            elif kind == 0x01:
                result[key] = read_string()
            elif kind == 0x02:
                if position + 4 > length:
                    raise ValueError("Truncated integer in binary VDF")
                result[key] = struct.unpack_from("<i", data, position)[0]
                position += 4
            else:
                raise ValueError(f"Unsupported binary VDF value type {kind:#x}")
        return result

    return read_map()


def shortcut_appid(entry: dict):
    """The unsigned 32-bit app id Steam's UI uses for a non-Steam shortcut."""
    raw = get_ci(entry, "appid")
    if isinstance(raw, int):
        return raw & 0xFFFFFFFF
    exe, name = get_ci(entry, "exe"), get_ci(entry, "appname")
    if not isinstance(exe, str) or not isinstance(name, str):
        return None
    return (zlib.crc32((exe + name).encode("utf-8")) & 0xFFFFFFFF) | 0x80000000
