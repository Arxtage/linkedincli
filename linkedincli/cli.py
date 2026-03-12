from __future__ import annotations

import sys
from pathlib import Path

import click

from linkedincli import __version__
from linkedincli.browser import LinkedInBrowserClient
from linkedincli.config import load_cached_pages, load_settings, remember_browser, save_cached_pages
from linkedincli.cookies import available_browsers
from linkedincli.exceptions import AuthenticationError, LinkedInCliError
from linkedincli.models import PageIdentity
from linkedincli.session import LinkedInSession

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
MAX_IMAGES = 4


@click.group()
def cli() -> None:
    """LinkedIn CLI."""


@cli.command()
def version() -> None:
    """Print the current version."""
    click.echo(f"linkedincli {__version__}")


@cli.command()
@click.option("--browser", type=click.Choice(available_browsers()), help="Cookie source browser.")
def whoami(browser: str | None) -> None:
    """Show the currently authenticated LinkedIn member."""
    session = _build_session(browser)
    try:
        me = session.whoami()
    except LinkedInCliError as exc:
        try:
            with LinkedInBrowserClient(session.cookie_bundle) as browser_client:
                me = browser_client.read_identity()
        except LinkedInCliError as browser_exc:
            raise click.ClickException(
                "LinkedIn session lookup failed via API and browser fallback. "
                f"API: {exc} Browser: {browser_exc}"
            ) from browser_exc
    click.echo(me.name)
    click.echo(f"handle: {me.public_identifier}")
    click.echo(f"profile: {me.profile_url}")
    if me.headline:
        click.echo(f"headline: {me.headline}")
    click.echo(f"browser: {session.browser_name}")


@cli.command()
@click.option("--refresh", is_flag=True, help="Refresh the managed-page cache from LinkedIn.")
@click.option("--browser", type=click.Choice(available_browsers()), help="Cookie source browser.")
@click.option(
    "--debug-browser",
    is_flag=True,
    help="Show the automation browser if a browser fallback is needed.",
)
def pages(refresh: bool, browser: str | None, debug_browser: bool) -> None:
    """List the company pages you can post as."""
    session = _build_session(browser)
    try:
        cached_pages = load_cached_pages(browser_name=session.browser_name)
        if refresh or not cached_pages:
            cached_pages = []
            try:
                cached_pages = session.discover_pages_from_admin_html()
            except LinkedInCliError:
                cached_pages = []
            if not cached_pages:
                with LinkedInBrowserClient(
                    session.cookie_bundle, headless=not debug_browser
                ) as browser_client:
                    cached_pages = browser_client.discover_pages()
            save_cached_pages(cached_pages, browser_name=session.browser_name)
        if not cached_pages:
            click.echo("No managed company pages found for this browser session.")
            return
        for page in cached_pages:
            click.echo(f"{page.alias}\t{page.name}\t{page.admin_url}")
    except LinkedInCliError as exc:
        raise click.ClickException(str(exc)) from exc


@cli.command()
@click.argument("text")
@click.option(
    "--image",
    "images",
    multiple=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Attach an image. Repeat up to 4 times.",
)
@click.option("--as", "target", default="me", help="Post as yourself or a cached page alias.")
@click.option("--browser", type=click.Choice(available_browsers()), help="Cookie source browser.")
@click.option("--debug-browser", is_flag=True, help="Show the automation browser window.")
def post(
    text: str,
    images: tuple[Path, ...],
    target: str,
    browser: str | None,
    debug_browser: bool,
) -> None:
    """Publish a LinkedIn post using your current browser session."""
    if text == "-":
        text = sys.stdin.read().strip()
    text = text.strip()
    if not text:
        raise click.ClickException("Post text cannot be empty.")
    image_paths = _validate_images(list(images))
    try:
        session = _build_session(browser)
        target_page = _resolve_target_page(target, session) if target.lower() != "me" else None
        with LinkedInBrowserClient(
            session.cookie_bundle, headless=not debug_browser
        ) as browser_client:
            post_url = browser_client.post(text, image_paths, target_page=target_page)
    except LinkedInCliError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"Posted successfully as {'you' if target_page is None else target_page.name}.")
    if post_url:
        click.echo(post_url)
    else:
        click.echo("LinkedIn did not expose a post URL, but the composer finished successfully.")



def _build_session(browser: str | None) -> LinkedInSession:
    candidates: list[str] = []
    if browser:
        candidates.append(browser)
    else:
        remembered_browser = load_settings().get("last_browser")
        if remembered_browser:
            candidates.append(remembered_browser)
        candidates.extend(name for name in available_browsers() if name not in candidates)

    last_error: LinkedInCliError | None = None
    for candidate in candidates:
        try:
            session = LinkedInSession(browser_name=candidate)
            remember_browser(session.browser_name)
            return session
        except LinkedInCliError as exc:
            last_error = exc

    raise AuthenticationError(
        "No working LinkedIn browser session was found. "
        "Try `--browser safari` or sign in to linkedin.com in Safari first."
    ) from last_error



def _validate_images(images: list[Path]) -> list[Path]:
    if len(images) > MAX_IMAGES:
        raise click.ClickException(f"A maximum of {MAX_IMAGES} images is supported in v1.")
    normalized: list[Path] = []
    for image in images:
        suffix = image.suffix.lower()
        if suffix not in IMAGE_EXTENSIONS:
            allowed = ", ".join(sorted(IMAGE_EXTENSIONS))
            raise click.ClickException(f"Unsupported image type '{suffix}'. Allowed: {allowed}")
        normalized.append(image.resolve())
    return normalized



def _resolve_target_page(target: str, session: LinkedInSession) -> PageIdentity:
    pages = load_cached_pages(browser_name=session.browser_name)
    page = _match_page(target, pages)
    if page is not None:
        return page
    try:
        refreshed_pages = session.discover_pages_from_admin_html()
    except LinkedInCliError:
        refreshed_pages = []
    if not refreshed_pages:
        with LinkedInBrowserClient(session.cookie_bundle) as browser_client:
            refreshed_pages = browser_client.discover_pages()
    save_cached_pages(refreshed_pages, browser_name=session.browser_name)
    page = _match_page(target, refreshed_pages)
    if page is None:
        raise click.ClickException(
            f"Unknown page alias '{target}'. "
            "Run `linkedincli pages --refresh` to refresh the page cache."
        )
    return page



def _match_page(target: str, pages: list[PageIdentity]) -> PageIdentity | None:
    lowered = target.lower()
    for page in pages:
        if lowered in {page.alias.lower(), page.slug.lower(), page.name.lower()}:
            return page
    return None
