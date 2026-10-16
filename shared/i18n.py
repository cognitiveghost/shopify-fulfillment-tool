"""On-screen text in this PC's language (ADR 0021).

English source text is the key: `_("Save")`. English has no catalogue, and a
key with no entry shows its English. Only text handed to the screen is wrapped;
identity values, files, logs and exception text stay English.

`set_language` runs in each app's main(), after modules are imported, so `_()`
must not run at import time: a module-level constant is `N_("...")` and is
wrapped where it is shown.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

LANGUAGES = {"en": "English", "bg": "Български"}
DEFAULT_LANGUAGE = "en"
SHARED_LOCALES = Path(__file__).resolve().parent / "assets" / "locales"


def N_(text: str) -> str:
    """Marks a constant for the key scanner; returns it unchanged."""
    return text


_MONTHS = (
    N_("Jan"), N_("Feb"), N_("Mar"), N_("Apr"), N_("May"), N_("Jun"),
    N_("Jul"), N_("Aug"), N_("Sep"), N_("Oct"), N_("Nov"), N_("Dec"),
)

_log = logging.getLogger(__name__)
_language = DEFAULT_LANGUAGE
_catalogue: dict = {}


def catalogue_files(app_root: Path, code: str) -> list[Path]:
    """The shared catalogue, then the app's: later files win."""
    return [SHARED_LOCALES / f"{code}.json", Path(app_root) / "locales" / f"{code}.json"]


def set_language(code: str, files: list[Path]) -> None:
    global _language, _catalogue
    if code not in LANGUAGES:
        _log.warning("Unknown language %r; using %s", code, DEFAULT_LANGUAGE)
        code = DEFAULT_LANGUAGE
    merged: dict = {}
    if code != DEFAULT_LANGUAGE:
        for path in files:
            if not path.is_file():
                continue
            try:
                merged.update(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, ValueError) as exc:
                _log.warning("Skipping catalogue %s: %s", path, exc)
    _language, _catalogue = code, merged


def language() -> str:
    return _language


def catalogue() -> dict:
    return _catalogue


def _(text: str, **values) -> str:
    found = _catalogue.get(text)
    out = found if isinstance(found, str) else text
    return out.format(**values) if values else out


def _n(one: str, other: str, n: int, **values) -> str:
    # ponytail: two plural forms; a language with more (ru, pl) needs a plural rule per language.
    found = _catalogue.get(one)
    forms = found if isinstance(found, list) and len(found) == 2 else [one, other]
    return forms[0 if n == 1 else 1].format(n=n, **values)


def month_abbr(month: int) -> str:
    """Replaces strftime("%b"), which is English whatever the language."""
    return _(_MONTHS[month - 1])
