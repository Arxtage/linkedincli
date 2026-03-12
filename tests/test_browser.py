from __future__ import annotations

import base64
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

from linkedincli.browser import (
    attach_images,
    build_pages_from_link_candidates,
    collect_company_slugs_from_hrefs,
    extract_member_from_link_candidates,
    open_post_composer,
    publish_post,
    set_post_text,
)

PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO0M2XQAAAAASUVORK5CYII="
)


@pytest.fixture()
def playwright_page():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        yield page
        browser.close()


FIXTURE_HTML = '''
<html>
  <body>
    <button id="trigger" aria-label="Start a post">Start a post</button>
    <div id="dialog" role="dialog" hidden>
      <div id="editor" role="textbox" contenteditable="true"></div>
      <input id="upload" type="file" accept="image/*" multiple />
      <button id="post-btn">Post</button>
    </div>
    <script>
      const trigger = document.getElementById('trigger');
      const dialog = document.getElementById('dialog');
      const editor = document.getElementById('editor');
      const upload = document.getElementById('upload');
      const postBtn = document.getElementById('post-btn');
      trigger.addEventListener('click', () => { dialog.hidden = false; });
      postBtn.addEventListener('click', () => {
        window.__posted = {
          text: editor.textContent,
          files: upload.files.length,
        };
        dialog.hidden = true;
      });
    </script>
  </body>
</html>
'''



def test_post_helpers_work_on_fixture(playwright_page, tmp_path: Path) -> None:
    image = tmp_path / "image.png"
    image.write_bytes(PNG_BYTES)
    playwright_page.set_content(FIXTURE_HTML)

    open_post_composer(playwright_page)
    set_post_text(playwright_page, "Hello LinkedIn")
    attach_images(playwright_page, [image])
    publish_post(playwright_page)

    posted = playwright_page.evaluate("() => window.__posted")
    assert posted == {"text": "Hello LinkedIn", "files": 1}



def test_collect_company_slugs_from_hrefs() -> None:
    hrefs = [
        "https://www.linkedin.com/company/paperclip/admin/",
        "https://www.linkedin.com/company/paperclip/admin/posts/",
        "https://www.linkedin.com/company/brutents/admin/",
    ]

    assert collect_company_slugs_from_hrefs(hrefs) == ["paperclip", "brutents"]


def test_build_pages_from_link_candidates() -> None:
    pages = build_pages_from_link_candidates(
        [
            {
                "href": "https://www.linkedin.com/company/paperclip/",
                "text": "Paperclip",
                "x": 10,
                "y": 200,
            }
        ]
    )

    assert len(pages) == 1
    assert pages[0].slug == "paperclip"
    assert pages[0].alias == "paperclip"


def test_publish_post_advances_multistep_composer(playwright_page) -> None:
    playwright_page.set_content(
        '''
        <html>
          <body>
            <div role="dialog">
              <button id="next-btn">Next</button>
              <button id="post-btn" hidden>Post</button>
            </div>
            <script>
              const nextBtn = document.getElementById('next-btn');
              const postBtn = document.getElementById('post-btn');
              nextBtn.addEventListener('click', () => {
                nextBtn.hidden = true;
                postBtn.hidden = false;
              });
              postBtn.addEventListener('click', () => {
                window.__published = true;
                postBtn.closest('[role="dialog"]').remove();
              });
            </script>
          </body>
        </html>
        '''
    )

    publish_post(playwright_page)

    assert playwright_page.evaluate("() => window.__published") is True


def test_extract_member_from_link_candidates() -> None:
    member = extract_member_from_link_candidates(
        [
            {
                "href": "https://www.linkedin.com/in/alex-example/",
                "text": "Alex Example  engineer, entrepreneur",
                "x": 12,
                "y": 100,
            }
        ]
    )

    assert member is not None
    assert member.public_identifier == "alex-example"
    assert member.headline == "engineer, entrepreneur"
