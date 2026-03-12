from __future__ import annotations

from pathlib import Path

import linkedincli.config as config
from linkedincli.models import PageIdentity


def test_save_and_load_cached_pages(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(config, "APP_DIR", tmp_path)
    monkeypatch.setattr(config, "SETTINGS_FILE", tmp_path / "settings.json")
    monkeypatch.setattr(config, "PAGES_FILE", tmp_path / "pages.json")
    monkeypatch.setattr(config, "DEBUG_DIR", tmp_path / "debug")

    pages = [
        PageIdentity(
            alias="paperclip",
            name="Paperclip",
            slug="paperclip",
            admin_url="https://www.linkedin.com/company/paperclip/admin/",
            public_url="https://www.linkedin.com/company/paperclip/",
        )
    ]

    config.save_cached_pages(pages, browser_name="safari")
    loaded = config.load_cached_pages(browser_name="safari")

    assert len(loaded) == 1
    assert loaded[0].alias == "paperclip"
    assert loaded[0].public_url.endswith("/paperclip/")
    assert config.load_cached_pages(browser_name="arc") == []
