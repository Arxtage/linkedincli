from __future__ import annotations

from http.cookiejar import Cookie

import responses

from linkedincli.cookies import CookieBundle
from linkedincli.session import LinkedInSession, parse_company_slugs_from_html


def make_cookie(name: str, value: str) -> Cookie:
    return Cookie(
        version=0,
        name=name,
        value=value,
        port=None,
        port_specified=False,
        domain='.linkedin.com',
        domain_specified=True,
        domain_initial_dot=True,
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


@responses.activate
def test_whoami_parses_me_response() -> None:
    responses.get(
        "https://www.linkedin.com/voyager/api/me",
        json={
            "data": {"plainId": 123, "*miniProfile": "urn:li:fs_miniProfile:abc"},
            "included": [
                {
                    "$type": "com.linkedin.voyager.identity.shared.MiniProfile",
                    "entityUrn": "urn:li:fs_miniProfile:abc",
                    "firstName": "Alex",
                    "lastName": "Example",
                    "publicIdentifier": "alex-example",
                    "occupation": "builder",
                }
            ],
        },
        status=200,
    )

    session = LinkedInSession(
        cookie_bundle=CookieBundle(
            browser_name="arc",
            cookies=[make_cookie("li_at", "token"), make_cookie("JSESSIONID", '"ajax:1"')],
        )
    )
    me = session.whoami()

    assert me.name == "Alex Example"
    assert me.public_identifier == "alex-example"
    assert me.profile_url.endswith("/alex-example/")


@responses.activate
def test_whoami_raises_on_bounced_redirect() -> None:
    responses.get(
        "https://www.linkedin.com/voyager/api/me",
        status=302,
        headers={"location": "https://www.linkedin.com/voyager/api/me"},
    )

    session = LinkedInSession(
        cookie_bundle=CookieBundle(
            browser_name="arc",
            cookies=[make_cookie("li_at", "token"), make_cookie("JSESSIONID", '"ajax:1"')],
        )
    )

    try:
        session.whoami()
    except Exception as exc:
        assert "bounced the request" in str(exc)
    else:
        raise AssertionError("Expected bounced redirect to raise an auth error.")


@responses.activate
def test_admin_html_raises_on_rate_limit() -> None:
    responses.get(
        "https://www.linkedin.com/company/setup/admin/",
        status=429,
    )

    session = LinkedInSession(
        cookie_bundle=CookieBundle(
            browser_name="arc",
            cookies=[make_cookie("li_at", "token"), make_cookie("JSESSIONID", '"ajax:1"')],
        )
    )

    try:
        session.get_admin_setup_html()
    except Exception as exc:
        assert "rate-limiting" in str(exc)
    else:
        raise AssertionError("Expected rate limit to raise an auth error.")


@responses.activate
def test_discover_pages_from_admin_html() -> None:
    responses.get(
        "https://www.linkedin.com/company/setup/admin/",
        body='''
        <a href="https://www.linkedin.com/company/paperclip/admin/">Paperclip</a>
        <a href="/company/brutents/admin/">Brutents</a>
        ''',
        status=200,
        content_type="text/html",
    )
    responses.get(
        "https://www.linkedin.com/voyager/api/organization/companies",
        json={
            "data": {"*elements": ["urn:li:fs_normalized_company:1"]},
            "included": [
                {
                    "$type": "com.linkedin.voyager.organization.Company",
                    "entityUrn": "urn:li:fs_normalized_company:1",
                    "name": "Paperclip",
                    "universalName": "paperclip",
                    "url": "https://www.linkedin.com/company/paperclip/",
                }
            ],
        },
        match=[responses.matchers.query_param_matcher({
            "decorationId": "com.linkedin.voyager.deco.organization.web.WebFullCompanyMain-12",
            "q": "universalName",
            "universalName": "paperclip",
        })],
        status=200,
    )
    responses.get(
        "https://www.linkedin.com/voyager/api/organization/companies",
        json={
            "data": {"*elements": ["urn:li:fs_normalized_company:2"]},
            "included": [
                {
                    "$type": "com.linkedin.voyager.organization.Company",
                    "entityUrn": "urn:li:fs_normalized_company:2",
                    "name": "Brutents",
                    "universalName": "brutents",
                    "url": "https://www.linkedin.com/company/brutents/",
                }
            ],
        },
        match=[responses.matchers.query_param_matcher({
            "decorationId": "com.linkedin.voyager.deco.organization.web.WebFullCompanyMain-12",
            "q": "universalName",
            "universalName": "brutents",
        })],
        status=200,
    )

    session = LinkedInSession(
        cookie_bundle=CookieBundle(
            browser_name="arc",
            cookies=[make_cookie("li_at", "token"), make_cookie("JSESSIONID", '"ajax:1"')],
        )
    )
    pages = session.discover_pages_from_admin_html()

    assert [page.slug for page in pages] == ["paperclip", "brutents"]
    assert [page.alias for page in pages] == ["paperclip", "brutents"]



def test_parse_company_slugs_from_html_dedupes_links() -> None:
    html = '''
    <a href="https://www.linkedin.com/company/paperclip/admin/">Paperclip</a>
    <a href="/company/paperclip/admin/posts/">Paperclip again</a>
    <a href="/company/brutents/admin/">Brutents</a>
    '''

    assert parse_company_slugs_from_html(html) == ["paperclip", "brutents"]


def test_parse_company_slugs_from_html_accepts_public_company_links() -> None:
    html = '''
    <a href="https://www.linkedin.com/company/paperclip/">Paperclip</a>
    <a href="/company/setup/admin/">Setup</a>
    <a href="/company/brutents/?viewAsMember=true">Brutents</a>
    '''

    assert parse_company_slugs_from_html(html) == ["paperclip", "brutents"]


def test_parse_company_slugs_from_html_ignores_asset_paths() -> None:
    html = '''
    <img src="/company/large.svg" />
    <img src="/company/small-on-dark.svg" />
    <a href="/company/paperclip/admin/">Paperclip</a>
    '''

    assert parse_company_slugs_from_html(html) == ["paperclip"]
