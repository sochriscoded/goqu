import json
from pathlib import Path

_CONFIG_DIR = Path.home() / ".config" / "goqu"
_DATASOURCE_FILE = _CONFIG_DIR / "datasource.json"
_UI_FILE = _CONFIG_DIR / "ui.json"

# Appearance preference: "dark" | "light" | "system".
THEME_MODES = ["dark", "light", "system"]
_DEFAULT_THEME = "dark"

_DEFAULTS: dict = {
    "source": "yfinance",
    "api_key": "",
    "proxy": "",
    # Optional per-data-type provider overrides, e.g.
    #   {"options": "Polygon.io", "dividends": "Alpha Vantage"}
    # Anything unspecified falls back to "source".
    "routes": {},
    # Optional per-provider settings (api keys etc.) keyed by provider name.
    "providers": {},
}

SOURCES = ["yfinance", "Alpha Vantage", "Polygon.io"]

# Routable data types (must match data.providers.base.DataType values).
DATA_TYPES = ["daily", "quote", "dividends", "options"]


def load_datasource_config() -> dict:
    if not _DATASOURCE_FILE.exists():
        return _DEFAULTS.copy()
    with open(_DATASOURCE_FILE) as f:
        data = json.load(f)
    return {**_DEFAULTS, **data}


def save_datasource_config(config: dict) -> None:
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(_DATASOURCE_FILE, "w") as f:
        json.dump(config, f, indent=2)


def get_routes() -> dict:
    """Map each data type -> provider name. Unspecified types use `source`."""
    cfg = load_datasource_config()
    source = cfg.get("source", "yfinance")
    overrides = cfg.get("routes") or {}
    return {dt: overrides.get(dt, source) for dt in DATA_TYPES}


def get_theme_pref() -> str:
    """Stored appearance preference; defaults to 'dark'. See ui/theme.py."""
    if not _UI_FILE.exists():
        return _DEFAULT_THEME
    try:
        with open(_UI_FILE) as f:
            mode = json.load(f).get("theme", _DEFAULT_THEME)
    except (json.JSONDecodeError, OSError):
        return _DEFAULT_THEME
    return mode if mode in THEME_MODES else _DEFAULT_THEME


def set_theme_pref(mode: str) -> None:
    """Persist the appearance preference ('dark' | 'light' | 'system')."""
    if mode not in THEME_MODES:
        mode = _DEFAULT_THEME
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(_UI_FILE, "w") as f:
        json.dump({"theme": mode}, f, indent=2)


def get_provider_config(name: str) -> dict:
    """Settings for a named provider (api_key, proxy, …).

    Reads the `providers` map first; for the currently-selected `source` it also
    falls back to the top-level api_key/proxy fields so the existing settings
    dialog keeps working without change.
    """
    cfg = load_datasource_config()
    provider_cfg = dict((cfg.get("providers") or {}).get(name, {}))
    if name == cfg.get("source"):
        provider_cfg.setdefault("api_key", cfg.get("api_key", ""))
        provider_cfg.setdefault("proxy", cfg.get("proxy", ""))
    return provider_cfg
