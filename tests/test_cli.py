from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from linkedincli.cli import cli
from linkedincli.models import MemberIdentity, PageIdentity


class FakeSession:
    browser_name = "arc"
    cookie_bundle = object()

    def whoami(self) -> MemberIdentity:
        return MemberIdentity(name="Alex Example", public_identifier="alex-example")

    def discover_pages_from_admin_html(self) -> list[PageIdentity]:
        return [
            PageIdentity(
                alias="paperclip",
                name="Paperclip",
                slug="paperclip",
                admin_url="https://www.linkedin.com/company/paperclip/admin/",
                public_url="https://www.linkedin.com/company/paperclip/",
            )
        ]

    def hydrate_pages(self, slugs: list[str]) -> list[PageIdentity]:
        return []


class FakeBrowserClient:
    def __init__(self, *args, **kwargs) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def discover_page_slugs(self) -> list[str]:
        return []

    def discover_pages(self) -> list[PageIdentity]:
        return [
            PageIdentity(
                alias="paperclip",
                name="Paperclip",
                slug="paperclip",
                admin_url="https://www.linkedin.com/company/paperclip/admin/",
                public_url="https://www.linkedin.com/company/paperclip/",
            )
        ]

    def post(
        self,
        text: str,
        image_paths: list[Path],
        target_page: PageIdentity | None = None,
    ) -> str | None:
        assert text == "hello linkedin"
        assert image_paths == []
        assert target_page is None
        return "https://www.linkedin.com/feed/update/urn:li:activity:1/"



def test_whoami_command(monkeypatch, tmp_path: Path) -> None:
    import linkedincli.cli as cli_module
    import linkedincli.config as config

    monkeypatch.setattr(cli_module, "_build_session", lambda browser: FakeSession())
    monkeypatch.setattr(config, "APP_DIR", tmp_path)
    monkeypatch.setattr(config, "SETTINGS_FILE", tmp_path / "settings.json")
    monkeypatch.setattr(config, "PAGES_FILE", tmp_path / "pages.json")
    monkeypatch.setattr(config, "DEBUG_DIR", tmp_path / "debug")

    result = CliRunner().invoke(cli, ["whoami"])

    assert result.exit_code == 0
    assert "Alex Example" in result.output
    assert "alex-example" in result.output



def test_pages_command(monkeypatch, tmp_path: Path) -> None:
    import linkedincli.cli as cli_module
    import linkedincli.config as config

    monkeypatch.setattr(cli_module, "_build_session", lambda browser: FakeSession())
    monkeypatch.setattr(cli_module, "LinkedInBrowserClient", FakeBrowserClient)
    monkeypatch.setattr(config, "APP_DIR", tmp_path)
    monkeypatch.setattr(config, "SETTINGS_FILE", tmp_path / "settings.json")
    monkeypatch.setattr(config, "PAGES_FILE", tmp_path / "pages.json")
    monkeypatch.setattr(config, "DEBUG_DIR", tmp_path / "debug")

    result = CliRunner().invoke(cli, ["pages", "--refresh"])

    assert result.exit_code == 0
    assert "paperclip\tPaperclip\t" in result.output



def test_post_command(monkeypatch, tmp_path: Path) -> None:
    import linkedincli.cli as cli_module
    import linkedincli.config as config

    monkeypatch.setattr(cli_module, "_build_session", lambda browser: FakeSession())
    monkeypatch.setattr(cli_module, "LinkedInBrowserClient", FakeBrowserClient)
    monkeypatch.setattr(config, "APP_DIR", tmp_path)
    monkeypatch.setattr(config, "SETTINGS_FILE", tmp_path / "settings.json")
    monkeypatch.setattr(config, "PAGES_FILE", tmp_path / "pages.json")
    monkeypatch.setattr(config, "DEBUG_DIR", tmp_path / "debug")

    result = CliRunner().invoke(cli, ["post", "hello linkedin"])

    assert result.exit_code == 0
    assert "Posted successfully as you." in result.output
