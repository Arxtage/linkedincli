from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from http.cookiejar import Cookie

import browser_cookie3

from linkedincli.exceptions import AuthenticationError

CookieLoader = Callable[..., object]
REQUIRED_COOKIES = {"li_at", "JSESSIONID"}
COOKIE_DOMAINS = (".linkedin.com", "www.linkedin.com", "linkedin.com")
BROWSER_LOADERS: dict[str, CookieLoader] = {
    "safari": browser_cookie3.safari,
    "arc": browser_cookie3.arc,
    "brave": browser_cookie3.brave,
    "chrome": browser_cookie3.chrome,
    "firefox": browser_cookie3.firefox,
}


@dataclass(slots=True)
class CookieBundle:
    browser_name: str
    cookies: list[Cookie]

    @property
    def cookie_map(self) -> dict[str, str]:
        mapping: dict[str, str] = {}
        for cookie in self.cookies:
            mapping[cookie.name] = cookie.value
        return mapping

    @property
    def csrf_token(self) -> str:
        return self.cookie_map["JSESSIONID"].strip('"')

    def to_playwright_cookies(self) -> list[dict]:
        playwright_cookies: list[dict] = []
        seen: set[tuple[str, str, str]] = set()
        for cookie in self.cookies:
            if "linkedin.com" not in cookie.domain:
                continue
            key = (cookie.name, cookie.domain, cookie.path)
            if key in seen:
                continue
            seen.add(key)
            payload = {
                "name": cookie.name,
                "value": cookie.value,
                "domain": cookie.domain,
                "path": cookie.path,
                "secure": bool(cookie.secure),
                "httpOnly": bool(
                    cookie.has_nonstandard_attr("HttpOnly") or cookie._rest.get("HttpOnly")
                ),
            }
            same_site = (cookie._rest.get("SameSite") or "").lower()
            if same_site in {"lax", "strict", "none"}:
                payload["sameSite"] = same_site.capitalize()
            if cookie.expires:
                payload["expires"] = cookie.expires
            playwright_cookies.append(payload)
        return playwright_cookies



def available_browsers() -> tuple[str, ...]:
    return tuple(BROWSER_LOADERS)



def _extract_cookies(loader: CookieLoader) -> list[Cookie]:
    collected: list[Cookie] = []
    seen: set[tuple[str, str, str]] = set()
    for domain in COOKIE_DOMAINS:
        try:
            jar = loader(domain_name=domain)
        except TypeError:
            try:
                jar = loader()
            except Exception:
                continue
        except Exception:
            continue
        for cookie in jar:
            if "linkedin.com" not in cookie.domain:
                continue
            key = (cookie.name, cookie.domain, cookie.path)
            if key in seen:
                continue
            seen.add(key)
            collected.append(cookie)
    return collected



def load_cookie_bundle(preferred_browser: str | None = None) -> CookieBundle:
    candidates = [preferred_browser.lower()] if preferred_browser else list(BROWSER_LOADERS)
    for browser_name in candidates:
        loader = BROWSER_LOADERS.get(browser_name)
        if loader is None:
            raise AuthenticationError(
                f"Unsupported browser '{preferred_browser}'. "
                f"Choose one of: {', '.join(BROWSER_LOADERS)}."
            )
        cookies = _extract_cookies(loader)
        if REQUIRED_COOKIES.issubset({cookie.name for cookie in cookies}):
            return CookieBundle(browser_name=browser_name, cookies=cookies)
    if preferred_browser:
        raise AuthenticationError(
            f"Could not find LinkedIn cookies in {preferred_browser}. "
            "Make sure you're logged into linkedin.com."
        )
    raise AuthenticationError(
        "Could not find a logged-in LinkedIn browser session in "
        "Arc, Chrome, Brave, Safari, or Firefox."
    )
