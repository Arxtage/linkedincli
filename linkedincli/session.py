from __future__ import annotations

import html as html_lib
import re
from collections.abc import Iterable
from urllib.parse import unquote, urlparse

import requests

from linkedincli.cookies import CookieBundle, load_cookie_bundle
from linkedincli.exceptions import AuthenticationError, DiscoveryError
from linkedincli.models import MemberIdentity, PageIdentity
from linkedincli.utils import assign_page_aliases, slugify_alias

VOYAGER_BASE = "https://www.linkedin.com/voyager/api"
LINKEDIN_BASE = "https://www.linkedin.com"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"
)
REQUEST_COOKIE_NAMES = ("li_at", "JSESSIONID")
COMPANY_LINK_PATTERN = re.compile(
    r"(?:https?://www\.linkedin\.com)?/company/[^\"'\s<]+",
    re.I,
)
RESERVED_COMPANY_SLUGS = {"setup"}


class LinkedInSession:
    def __init__(
        self,
        browser_name: str | None = None,
        *,
        cookie_bundle: CookieBundle | None = None,
        timeout: int = 20,
    ) -> None:
        self.cookie_bundle = cookie_bundle or load_cookie_bundle(browser_name)
        self.browser_name = self.cookie_bundle.browser_name
        self.timeout = timeout
        self.session = requests.Session()
        cookie_map = self.cookie_bundle.cookie_map
        self.session.cookies.update(
            {name: cookie_map[name] for name in REQUEST_COOKIE_NAMES if name in cookie_map}
        )

    @property
    def headers(self) -> dict[str, str]:
        return {
            "csrf-token": self.cookie_bundle.csrf_token,
            "x-restli-protocol-version": "2.0.0",
            "accept": "application/vnd.linkedin.normalized+json+2.1",
            "user-agent": USER_AGENT,
        }

    def _request(self, method: str, url: str, **kwargs) -> requests.Response:
        try:
            response = self.session.request(
                method,
                url,
                headers={**self.headers, **kwargs.pop("headers", {})},
                timeout=kwargs.pop("timeout", self.timeout),
                allow_redirects=kwargs.pop("allow_redirects", False),
                **kwargs,
            )
        except requests.RequestException as exc:
            raise AuthenticationError(
                "LinkedIn request failed. Open linkedin.com in your browser and retry."
            ) from exc
        self._raise_for_auth(response)
        return response

    def _raise_for_auth(self, response: requests.Response) -> None:
        location = response.headers.get("location", "")
        if response.status_code in {401, 403}:
            raise AuthenticationError(
                "LinkedIn rejected your browser session. Log in again and retry."
            )
        if "/login" in location or "/checkpoint/" in location:
            raise AuthenticationError(
                "LinkedIn redirected to login/checkpoint. Refresh your browser session and retry."
            )
        if response.url.startswith(f"{LINKEDIN_BASE}/checkpoint/"):
            raise AuthenticationError(
                "LinkedIn is asking for an interactive checkpoint verification."
            )
        if response.headers.get("content-type", "").startswith("text/html"):
            snippet = response.text[:4000].lower()
            if "sign in" in snippet and "password" in snippet:
                raise AuthenticationError(
                    "LinkedIn appears to be showing the sign-in page instead of the requested page."
                )

    def whoami(self) -> MemberIdentity:
        response = self._request("GET", f"{VOYAGER_BASE}/me")
        try:
            payload = response.json()
        except ValueError as exc:
            raise AuthenticationError(
                "LinkedIn returned a non-API response for /me. "
                "Open linkedin.com in your browser and try again."
            ) from exc
        mini_profile_urn = payload["data"].get("*miniProfile")
        mini_profile = _find_included(payload, mini_profile_urn)
        if not mini_profile:
            raise DiscoveryError("LinkedIn returned /me but did not include the profile payload.")
        name = " ".join(
            filter(None, [mini_profile.get("firstName"), mini_profile.get("lastName")])
        ).strip()
        return MemberIdentity(
            name=name,
            public_identifier=mini_profile["publicIdentifier"],
            plain_id=payload["data"].get("plainId"),
            profile_urn=mini_profile.get("entityUrn"),
            headline=mini_profile.get("occupation"),
        )

    def fetch_company(self, slug: str) -> PageIdentity:
        response = self._request(
            "GET",
            f"{VOYAGER_BASE}/organization/companies",
            params={
                "decorationId": "com.linkedin.voyager.deco.organization.web.WebFullCompanyMain-12",
                "q": "universalName",
                "universalName": slug,
            },
        )
        try:
            payload = response.json()
        except ValueError as exc:
            raise DiscoveryError(
                f"LinkedIn returned a non-API response while loading company '{slug}'."
            ) from exc
        company = _extract_company(payload, slug)
        if not company:
            raise DiscoveryError(f"LinkedIn did not return metadata for company page '{slug}'.")
        public_url = company.get("url") or f"https://www.linkedin.com/company/{slug}/"
        return PageIdentity(
            alias=slugify_alias(company.get("name") or slug),
            name=company.get("name") or slug.replace("-", " ").title(),
            slug=company.get("universalName") or slug,
            admin_url=f"https://www.linkedin.com/company/{slug}/admin/",
            public_url=public_url,
            entity_urn=company.get("entityUrn"),
        )

    def get_admin_setup_html(self) -> str:
        response = self._request(
            "GET",
            f"{LINKEDIN_BASE}/company/setup/admin/",
            headers={
                "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
            allow_redirects=True,
        )
        return response.text

    def discover_pages_from_admin_html(self) -> list[PageIdentity]:
        slugs = parse_company_slugs_from_html(self.get_admin_setup_html())
        return self.hydrate_pages(slugs)

    def hydrate_pages(self, slugs: Iterable[str]) -> list[PageIdentity]:
        pages: list[PageIdentity] = []
        for slug in slugs:
            try:
                pages.append(self.fetch_company(slug))
            except DiscoveryError:
                pages.append(
                    PageIdentity(
                        alias=slugify_alias(slug),
                        name=slug.replace("-", " ").title(),
                        slug=slug,
                        admin_url=f"https://www.linkedin.com/company/{slug}/admin/",
                        public_url=f"https://www.linkedin.com/company/{slug}/",
                    )
                )
        return assign_page_aliases(pages)



def parse_company_slugs_from_html(page_html: str) -> list[str]:
    decoded = html_lib.unescape(page_html)
    slugs: list[str] = []
    seen: set[str] = set()
    for match in COMPANY_LINK_PATTERN.findall(decoded):
        slug = extract_company_slug(match)
        if not slug or slug in seen:
            continue
        seen.add(slug)
        slugs.append(slug)
    return slugs


def extract_company_slug(value: str) -> str | None:
    decoded = html_lib.unescape(value).strip()
    if not decoded:
        return None
    if decoded.startswith("/"):
        decoded = f"{LINKEDIN_BASE}{decoded}"

    parsed = urlparse(decoded)
    if parsed.netloc and parsed.netloc not in {"linkedin.com", "www.linkedin.com"}:
        return None

    segments = [unquote(segment).strip().lower() for segment in parsed.path.split("/") if segment]
    if len(segments) < 2 or segments[0] != "company":
        return None

    slug = segments[1]
    if not slug or slug in RESERVED_COMPANY_SLUGS:
        return None

    if len(segments) == 2:
        return slug
    if segments[2] == "admin":
        return slug
    return None



def _find_included(payload: dict, entity_urn: str | None) -> dict | None:
    if not entity_urn:
        return None
    for item in payload.get("included", []):
        if item.get("entityUrn") == entity_urn:
            return item
    return None



def _extract_company(payload: dict, slug: str) -> dict | None:
    included = payload.get("included", [])
    wanted_urns = payload.get("data", {}).get("*elements", [])
    for item in included:
        if item.get("entityUrn") in wanted_urns and item.get("$type", "").endswith("Company"):
            return item
    for item in included:
        if item.get("$type", "").endswith("Company") and item.get("universalName") == slug:
            return item
    return None
