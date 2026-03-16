from __future__ import annotations

import re
import time
from pathlib import Path
from urllib.parse import urljoin

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Locator, Page, TimeoutError, sync_playwright

from linkedincli.config import create_debug_run_dir
from linkedincli.cookies import CookieBundle
from linkedincli.exceptions import AuthenticationError, BrowserAutomationError
from linkedincli.models import MemberIdentity, PageIdentity
from linkedincli.session import LINKEDIN_BASE, extract_company_slug, parse_company_slugs_from_html
from linkedincli.utils import assign_page_aliases, slugify_alias

POST_TRIGGER_PATTERNS = [re.compile(r"start a post", re.I), re.compile(r"create post", re.I)]
POST_BUTTON_PATTERNS = [re.compile(r"^post$", re.I), re.compile(r"^publish$", re.I)]
ADVANCE_BUTTON_PATTERNS = [re.compile(r"^next$", re.I), re.compile(r"^done$", re.I)]
MEDIA_BUTTON_PATTERNS = [
    re.compile(r"add media", re.I),
    re.compile(r"add a photo", re.I),
    re.compile(r"photo", re.I),
    re.compile(r"image", re.I),
]
TEXTBOX_SELECTORS = [
    "[contenteditable='true'][role='textbox']",
    "div[contenteditable='true']",
    "textarea",
]
FILE_INPUT_SELECTORS = [
    "input[type='file'][accept*='image']",
    "input[type='file']",
]
BROWSER_LINK_SCRIPT = """
(anchors, leftRailOnly) => anchors.map((anchor) => {
  const rect = anchor.getBoundingClientRect();
  const text = (anchor.innerText || anchor.textContent || '')
    .replace(/\\s+/g, ' ')
    .trim();
  return {
    href: anchor.href || anchor.getAttribute('href') || '',
    text,
    x: rect.x,
    y: rect.y
  };
}).filter((item) => {
  if (!item.href || !item.text) return false;
  if (!leftRailOnly) return true;
  return item.x >= 0 && item.x < 460 && item.y >= 0 && item.y < 1600;
});
"""
BROWSER_ENGINES = {
    "safari": "webkit",
    "arc": "chromium",
    "brave": "chromium",
    "chrome": "chromium",
    "firefox": "firefox",
}


class LinkedInBrowserClient:
    def __init__(
        self,
        cookie_bundle: CookieBundle,
        *,
        headless: bool = True,
        viewport: tuple[int, int] = (1440, 1080),
    ) -> None:
        self.cookie_bundle = cookie_bundle
        self.headless = headless
        self.viewport = viewport
        self._playwright = None
        self._browser = None
        self._context = None
        self.page: Page | None = None

    def __enter__(self) -> LinkedInBrowserClient:
        try:
            self._playwright = sync_playwright().start()
            engine_name = BROWSER_ENGINES.get(self.cookie_bundle.browser_name, "chromium")
            browser_type = getattr(self._playwright, engine_name)
            self._browser = browser_type.launch(headless=self.headless)
        except PlaywrightError as exc:
            raise BrowserAutomationError(
                "Playwright browser runtime is not installed. "
                "Run `python -m playwright install chromium webkit` and retry."
            ) from exc
        self._context = self._browser.new_context(
            viewport={"width": self.viewport[0], "height": self.viewport[1]}
        )
        self._context.add_cookies(self.cookie_bundle.to_playwright_cookies())
        self.page = self._context.new_page()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._context is not None:
            self._context.close()
        if self._browser is not None:
            self._browser.close()
        if self._playwright is not None:
            self._playwright.stop()

    def goto_logged_in(self, url: str) -> Page:
        assert self.page is not None
        self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
        try:
            self.page.wait_for_load_state("networkidle", timeout=5000)
        except TimeoutError:
            self.page.wait_for_timeout(1500)
        self._ensure_logged_in()
        return self.page

    def discover_page_slugs(self) -> list[str]:
        page = self.goto_logged_in(f"{LINKEDIN_BASE}/company/setup/admin/")
        hrefs = page.locator("a").evaluate_all(
            "(anchors) => anchors"
            ".map((anchor) => anchor.href || anchor.getAttribute('href') || '')"
            ".filter(Boolean)"
        )
        slugs = collect_company_slugs_from_hrefs(hrefs)
        if slugs:
            return slugs
        return parse_company_slugs_from_html(page.content())

    def discover_pages(self) -> list[PageIdentity]:
        discovered: list[PageIdentity] = []
        for url, left_rail_only in (
            (f"{LINKEDIN_BASE}/company/setup/admin/", False),
            (f"{LINKEDIN_BASE}/feed/", True),
        ):
            page = self.goto_logged_in(url)
            candidates = page.locator("a[href*='/company/']").evaluate_all(
                BROWSER_LINK_SCRIPT,
                left_rail_only,
            )
            discovered.extend(build_pages_from_link_candidates(candidates))
        deduped: dict[str, PageIdentity] = {}
        for page in discovered:
            deduped.setdefault(page.slug, page)
        return assign_page_aliases(deduped.values())

    def read_identity(self) -> MemberIdentity:
        page = self.goto_logged_in(f"{LINKEDIN_BASE}/feed/")
        candidates = page.locator("a[href*='/in/']").evaluate_all(BROWSER_LINK_SCRIPT, True)
        member = extract_member_from_link_candidates(candidates)
        if member is None:
            raise BrowserAutomationError(
                "Couldn't find the signed-in member card on the LinkedIn feed."
            )
        return member

    def post(
        self,
        text: str,
        image_paths: list[Path],
        target_page: PageIdentity | None = None,
    ) -> str | None:
        try:
            if target_page is None:
                page = self.goto_logged_in(f"{LINKEDIN_BASE}/feed/")
            else:
                page = self._open_page_post_surface(target_page)
            open_post_composer(page)
            set_post_text(page, text)
            if image_paths:
                attach_images(page, image_paths)
            return publish_post(page)
        except Exception as exc:  # noqa: BLE001
            if isinstance(exc, (BrowserAutomationError, AuthenticationError)):
                raise self._decorate_error(exc) from exc
            raise self._decorate_error(BrowserAutomationError(str(exc))) from exc

    def _open_page_post_surface(self, target_page: PageIdentity) -> Page:
        candidate_urls = [
            f"{LINKEDIN_BASE}/company/{target_page.slug}/admin/feed/posts?share=true",
            f"{LINKEDIN_BASE}/company/{target_page.slug}/admin/page-posts/published/?share=true",
            target_page.admin_url,
            target_page.public_url,
        ]
        seen_urls: set[str] = set()
        for url in candidate_urls:
            if url in seen_urls:
                continue
            seen_urls.add(url)
            page = self.goto_logged_in(url)
            if composer_is_open(page) or has_post_trigger(page):
                return page
            if _first_visible_locator(_company_create_trigger_locators(page)) is not None:
                return page
        raise BrowserAutomationError(
            f"Couldn't find a page post composer for '{target_page.name}'."
        )

    def _ensure_logged_in(self) -> None:
        assert self.page is not None
        if "/login" in self.page.url or "/checkpoint/" in self.page.url:
            raise AuthenticationError(
                "LinkedIn redirected the automation browser to login/checkpoint."
            )
        page_text = self.page.locator("body").inner_text(timeout=5000).lower()
        if "sign in" in page_text and "join now" in page_text:
            raise AuthenticationError(
                "Automation browser is not landing on an authenticated LinkedIn page."
            )

    def _decorate_error(self, exc: Exception) -> BrowserAutomationError:
        artifact_dir = create_debug_run_dir()
        if self.page is not None:
            try:
                self.page.screenshot(path=str(artifact_dir / "failure.png"), full_page=True)
            except Exception:  # noqa: BLE001
                pass
            try:
                (artifact_dir / "failure.html").write_text(self.page.content())
            except Exception:  # noqa: BLE001
                pass
            try:
                (artifact_dir / "url.txt").write_text(self.page.url)
            except Exception:  # noqa: BLE001
                pass
        return BrowserAutomationError(f"{exc} Debug artifacts: {artifact_dir}")



def collect_company_slugs_from_hrefs(hrefs: list[str]) -> list[str]:
    slugs: list[str] = []
    seen: set[str] = set()
    for href in hrefs:
        slug = extract_company_slug(href)
        if not slug or slug in seen:
            continue
        seen.add(slug)
        slugs.append(slug)
    return slugs



def build_pages_from_link_candidates(candidates: list[dict]) -> list[PageIdentity]:
    pages: list[PageIdentity] = []
    seen: set[str] = set()
    for candidate in candidates:
        slug = extract_company_slug(candidate.get("href", ""))
        if not slug:
            continue
        if slug in seen:
            continue
        seen.add(slug)
        name = candidate.get("text", "").strip() or slug.replace("-", " ").title()
        pages.append(
            PageIdentity(
                alias=slugify_alias(name),
                name=name,
                slug=slug,
                admin_url=f"https://www.linkedin.com/company/{slug}/admin/",
                public_url=f"https://www.linkedin.com/company/{slug}/",
            )
        )
    return assign_page_aliases(pages)



def extract_member_from_link_candidates(candidates: list[dict]) -> MemberIdentity | None:
    for candidate in candidates:
        match = re.search(r"/in/([^/?#]+)/?", candidate.get("href", ""))
        if not match:
            continue
        text = candidate.get("text", "").strip()
        if not text:
            continue
        parts = [part.strip() for part in text.split("  ") if part.strip()]
        if not parts:
            continue
        return MemberIdentity(
            name=parts[0],
            public_identifier=match.group(1),
            headline=parts[1] if len(parts) > 1 else None,
        )
    return None



def has_post_trigger(page: Page) -> bool:
    return _first_visible_locator(_post_trigger_locators(page)) is not None



def open_post_composer(page: Page) -> None:
    if composer_is_open(page):
        return

    trigger = _first_visible_locator(_post_trigger_locators(page))
    if trigger is None:
        trigger = _first_visible_locator(_company_create_trigger_locators(page))
    if trigger is None:
        raise BrowserAutomationError(
            "Couldn't find a visible 'Start a post' or 'Create post' button."
        )
    tag = trigger.evaluate("el => el.tagName.toLowerCase()")
    if tag == "a":
        with page.expect_navigation(wait_until="domcontentloaded", timeout=15000):
            trigger.click(timeout=5000)
        try:
            page.wait_for_load_state("networkidle", timeout=5000)
        except TimeoutError:
            page.wait_for_timeout(1500)
    else:
        trigger.click(timeout=5000)
    try:
        page.locator("[role='dialog']").first.wait_for(state="visible", timeout=8000)
    except TimeoutError as exc:
        textbox = _first_visible_locator(_dialog_textbox_locators(page))
        if textbox is None:
            textbox = _first_visible_locator(_textbox_locators(page))
        if textbox is None:
            raise BrowserAutomationError(
                "LinkedIn opened no obvious post composer dialog."
            ) from exc
        return

    if composer_is_open(page):
        return

    post_entry = _first_visible_locator(_company_page_post_menu_locators(page))
    if post_entry is not None:
        _open_company_page_post_entry(page, post_entry)
        if composer_is_open(page):
            return
        textbox = _first_visible_locator(_textbox_locators(page))
        if textbox is not None:
            return

    textbox = _first_visible_locator(_dialog_textbox_locators(page))
    if textbox is not None:
        return

    raise BrowserAutomationError("LinkedIn opened no obvious post composer dialog.")



def set_post_text(page: Page, text: str) -> None:
    textbox = _first_visible_locator(_textbox_locators(page))
    if textbox is None:
        raise BrowserAutomationError("Couldn't find the LinkedIn post editor.")
    textbox.click(timeout=5000)
    try:
        page.keyboard.press("Meta+A")
    except PlaywrightError:
        try:
            page.keyboard.press("Control+A")
        except PlaywrightError:
            pass
    page.keyboard.insert_text(text)



def attach_images(page: Page, image_paths: list[Path]) -> None:
    file_input = _first_present_locator(_file_input_locators(page))
    if file_input is None:
        media_button = _first_visible_locator(_media_button_locators(page))
        if media_button is not None:
            media_button.click(timeout=5000)
            page.wait_for_timeout(500)
        file_input = _first_present_locator(_file_input_locators(page))
    if file_input is None:
        raise BrowserAutomationError("Couldn't find an image upload control in the composer.")
    file_input.set_input_files([str(path) for path in image_paths])



def publish_post(page: Page) -> str | None:
    _advance_post_flow(page)
    post_button = _first_visible_locator(_post_button_locators(page))
    if post_button is None:
        raise BrowserAutomationError("Couldn't find the final LinkedIn Post button.")
    post_button.click(timeout=5000)
    deadline = time.monotonic() + 15
    dialog = page.locator("[role='dialog']")
    while time.monotonic() < deadline:
        if _post_was_published(page):
            return _extract_post_url(page)
        dialog_visible = False
        try:
            dialog_visible = dialog.count() > 0 and dialog.first.is_visible()
        except PlaywrightError:
            dialog_visible = False
        if not dialog_visible:
            return _extract_post_url(page)
        page.wait_for_timeout(250)
    raise BrowserAutomationError("LinkedIn never confirmed that the post was published.")



def _extract_post_url(page: Page) -> str | None:
    locator = page.locator("a[href*='/feed/update/'], a[href*='/posts/']")
    if locator.count() == 0:
        return None
    href = locator.first.get_attribute("href")
    if not href:
        return None
    return urljoin(LINKEDIN_BASE, href)



def _post_trigger_locators(page: Page) -> list[Locator]:
    locators = [page.get_by_role("button", name=pattern) for pattern in POST_TRIGGER_PATTERNS]
    locators.extend(
        [
            page.locator("button[aria-label*='Start a post' i]"),
            page.locator("button[aria-label*='Create post' i]"),
        ]
    )
    locators.extend(page.get_by_role("link", name=pattern) for pattern in POST_TRIGGER_PATTERNS)
    locators.append(page.locator("a.artdeco-button:has-text('Start a post')"))
    locators.append(page.locator("a.artdeco-button:has-text('Create post')"))
    return locators



def _company_create_trigger_locators(page: Page) -> list[Locator]:
    create_pattern = re.compile(r"^create$", re.I)
    return [
        page.get_by_role("button", name=create_pattern),
        page.get_by_role("link", name=create_pattern),
        page.locator("button:has-text('Create')"),
        page.locator("a:has-text('Create')"),
    ]



def _post_button_locators(page: Page) -> list[Locator]:
    return [page.get_by_role("button", name=pattern) for pattern in POST_BUTTON_PATTERNS]



def _advance_button_locators(page: Page) -> list[Locator]:
    return [page.get_by_role("button", name=pattern) for pattern in ADVANCE_BUTTON_PATTERNS]



def _media_button_locators(page: Page) -> list[Locator]:
    return [page.get_by_role("button", name=pattern) for pattern in MEDIA_BUTTON_PATTERNS]



def _textbox_locators(page: Page) -> list[Locator]:
    return [page.locator(selector) for selector in TEXTBOX_SELECTORS]



def _dialog_textbox_locators(page: Page) -> list[Locator]:
    return [page.locator(f"[role='dialog'] {selector}") for selector in TEXTBOX_SELECTORS]



def _file_input_locators(page: Page) -> list[Locator]:
    return [page.locator(selector) for selector in FILE_INPUT_SELECTORS]



def _company_page_post_menu_locators(page: Page) -> list[Locator]:
    return [
        page.locator("a[data-test-org-menu-item='POSTS']"),
        page.locator("a[href*='/admin/feed/posts'][href*='share=true']"),
        page.get_by_role("link", name=re.compile(r"start a post", re.I)),
        page.locator("a:has-text('Start a post')"),
    ]



def _first_visible_locator(locators: list[Locator]) -> Locator | None:
    for locator in locators:
        if locator.count() == 0:
            continue
        try:
            candidate = locator.first
            if candidate.is_visible():
                return candidate
        except PlaywrightError:
            continue
    return None



def _first_present_locator(locators: list[Locator]) -> Locator | None:
    for locator in locators:
        if locator.count() == 0:
            continue
        return locator.first
    return None



def _advance_post_flow(page: Page) -> None:
    for _ in range(3):
        advance_button = _first_visible_locator(_advance_button_locators(page))
        if advance_button is None:
            return
        advance_button.click(timeout=5000)
        page.wait_for_timeout(500)



def composer_is_open(page: Page) -> bool:
    return _first_visible_locator(_dialog_textbox_locators(page)) is not None



def _open_company_page_post_entry(page: Page, post_entry: Locator) -> None:
    href = post_entry.get_attribute("href")
    if href:
        page.goto(urljoin(LINKEDIN_BASE, href), wait_until="domcontentloaded", timeout=30000)
        try:
            page.wait_for_load_state("networkidle", timeout=5000)
        except TimeoutError:
            page.wait_for_timeout(1500)
        return

    post_entry.click(timeout=5000)
    try:
        page.wait_for_load_state("networkidle", timeout=5000)
    except TimeoutError:
        page.wait_for_timeout(1500)



def _post_was_published(page: Page) -> bool:
    candidates = [
        page.locator("text=/post successful/i"),
        page.locator("text=/posted successfully/i"),
        page.locator(".sharing-nba-framework__success-toast-v2"),
    ]
    for locator in candidates:
        try:
            if locator.count() == 0:
                continue
            try:
                if locator.first.is_visible():
                    return True
            except PlaywrightError:
                pass
            return True
        except PlaywrightError:
            continue
    return False
