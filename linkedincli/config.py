from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from linkedincli.models import PageIdentity

APP_DIR = Path.home() / ".linkedincli"
SETTINGS_FILE = APP_DIR / "settings.json"
PAGES_FILE = APP_DIR / "pages.json"
DEBUG_DIR = APP_DIR / "debug"



def _ensure_app_dir() -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)



def _write_json(path: Path, payload: dict[str, Any]) -> None:
    _ensure_app_dir()
    path.write_text(json.dumps(payload, indent=2, sort_keys=True))



def _read_json(path: Path, default: dict[str, Any] | None = None) -> dict[str, Any]:
    if not path.exists():
        return {} if default is None else default
    return json.loads(path.read_text())



def load_settings() -> dict[str, Any]:
    return _read_json(SETTINGS_FILE, {})



def save_settings(settings: dict[str, Any]) -> None:
    _write_json(SETTINGS_FILE, settings)



def remember_browser(browser_name: str) -> None:
    settings = load_settings()
    settings["last_browser"] = browser_name
    save_settings(settings)



def load_cached_pages(*, browser_name: str | None = None) -> list[PageIdentity]:
    payload = _read_json(PAGES_FILE, {"pages": []})
    saved_browser = payload.get("browser")
    if browser_name and saved_browser and saved_browser != browser_name:
        return []
    return [PageIdentity.from_dict(item) for item in payload.get("pages", [])]



def save_cached_pages(pages: list[PageIdentity], *, browser_name: str | None = None) -> None:
    payload = {
        "saved_at": datetime.now(tz=UTC).isoformat(),
        "browser": browser_name,
        "pages": [page.to_dict() for page in pages],
    }
    _write_json(PAGES_FILE, payload)



def create_debug_run_dir() -> Path:
    _ensure_app_dir()
    stamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    run_dir = DEBUG_DIR / stamp
    counter = 2
    while run_dir.exists():
        run_dir = DEBUG_DIR / f"{stamp}-{counter}"
        counter += 1
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir
