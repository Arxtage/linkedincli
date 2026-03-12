# linkedincli

Post to LinkedIn from the terminal using your existing browser session.

`linkedincli` is a cookie-backed, unofficial CLI for:

- posting as yourself
- posting as a company page you manage
- attaching up to 4 images
- reusing the LinkedIn session already open in your browser

It does **not** use LinkedIn developer API credentials.

## Status

v0.1 is macOS-first and intentionally narrow:

- text posts
- 1–4 images
- member posts
- company page posts
- browser session discovery from Safari, Arc, Brave, Chrome, or Firefox

LinkedIn changes its UI often, so browser automation is inherently brittle. When a run fails, `linkedincli` saves debug artifacts in `~/.linkedincli/debug/`.

## Install

From the repo:

```bash
pip install .
python -m playwright install chromium webkit
```

Or with `uv`:

```bash
uv pip install --system .
python -m playwright install chromium webkit
```

## Usage

Show the current signed-in member:

```bash
linkedincli whoami
linkedincli whoami --browser safari
```

Discover company pages you can post as:

```bash
linkedincli pages --refresh
linkedincli pages --refresh --browser safari
```

Post as yourself:

```bash
linkedincli post "hello linkedin"
echo "hello from stdin" | linkedincli post -
```

Post with images:

```bash
linkedincli post "launch day" --image one.png --image two.jpg
```

Post as a company page:

```bash
linkedincli pages --refresh
linkedincli post "we shipped it" --as paperclip
```

Show the automation browser while debugging:

```bash
linkedincli post "debug me" --debug-browser
```

## How it works

- `browser-cookie3` reads your LinkedIn cookies from a local browser profile.
- Lightweight HTTP requests are used for session checks and page discovery when possible.
- Playwright drives the actual LinkedIn composer for publishing.
- Managed pages are cached in `~/.linkedincli/pages.json` and scoped to the browser that discovered them.

## Development

Install dev dependencies and run checks:

```bash
uv pip install --system '.[dev]'
python -m playwright install chromium webkit
ruff check .
pytest
```

## Notes

- This is for personal/private use.
- Live posting tests are intentionally manual because they create real LinkedIn content.
- If LinkedIn sends you to login or checkpoint flows, refresh the session in your browser first.

## License

MIT
