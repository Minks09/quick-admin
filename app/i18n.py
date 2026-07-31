"""i18n minimaliste : dictionnaires JSON par langue, helper t()."""
import json
from pathlib import Path

LOCALES_DIR = Path(__file__).parent / "locales"
LANGS = ["fr", "de", "it"]
DEFAULT = "fr"

_translations: dict[str, dict] = {}
for lang in LANGS:
    with open(LOCALES_DIR / f"{lang}.json", encoding="utf-8") as f:
        _translations[lang] = json.load(f)


def t(lang: str, key: str) -> str:
    lang = lang if lang in LANGS else DEFAULT
    return _translations[lang].get(key) or _translations[DEFAULT].get(key, key)


def make_t(lang: str):
    return lambda key: t(lang, key)
