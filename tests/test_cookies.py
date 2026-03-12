from __future__ import annotations

from http.cookiejar import Cookie

import linkedincli.cookies as cookies


def make_cookie(name: str, value: str, domain: str = ".linkedin.com") -> Cookie:
    return Cookie(
        version=0,
        name=name,
        value=value,
        port=None,
        port_specified=False,
        domain=domain,
        domain_specified=True,
        domain_initial_dot=domain.startswith('.'),
        path='/',
        path_specified=True,
        secure=True,
        expires=None,
        discard=True,
        comment=None,
        comment_url=None,
        rest={"HttpOnly": True},
        rfc2109=False,
    )


class FakeJar(list):
    pass



def test_load_cookie_bundle_uses_first_browser_with_required_cookies(monkeypatch) -> None:
    monkeypatch.setattr(
        cookies,
        "BROWSER_LOADERS",
        {
            "arc": lambda **_: FakeJar([make_cookie("li_at", "token-only")]),
            "chrome": lambda **_: FakeJar([
                make_cookie("li_at", "token"),
                make_cookie("JSESSIONID", '"ajax:123"'),
                make_cookie("bscookie", "other"),
            ]),
        },
    )

    bundle = cookies.load_cookie_bundle()

    assert bundle.browser_name == "chrome"
    assert bundle.csrf_token == "ajax:123"
    playwright_names = {item["name"] for item in bundle.to_playwright_cookies()}
    assert {"li_at", "JSESSIONID", "bscookie"} <= playwright_names
