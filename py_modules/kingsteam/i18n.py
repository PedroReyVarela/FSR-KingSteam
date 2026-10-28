"""Backend messages in English or Spanish; the UI sends Steam's language once at startup."""

_lang = "en"


def set_language(code: str) -> str:
    global _lang
    _lang = "es" if str(code or "").lower().startswith("es") else "en"
    return _lang


def language() -> str:
    return _lang


def tr(en: str, es: str) -> str:
    return es if _lang == "es" else en


def pick(text) -> str:
    """Choose from an {"en": ..., "es": ...} mapping (used by the catalog data file)."""
    if isinstance(text, dict):
        return text.get(_lang) or text.get("en") or ""
    return str(text or "")
