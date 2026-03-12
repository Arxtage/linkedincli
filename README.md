# linkedincli

<p align="center">
  <strong>Post to LinkedIn from the terminal — or let your AI agent do it for you.</strong>
</p>

<p align="center">
  Cookie-backed LinkedIn posting for humans, shells, scripts, and agent runtimes.
</p>

<p align="center">
  <a href="https://claude.com/product/claude-code">
    <img alt="Claude Code" src="https://img.shields.io/badge/Claude%20Code-supported-111111?style=for-the-badge&logo=anthropic&logoColor=white" />
  </a>
  <a href="https://github.com/openai/codex">
    <img alt="Codex" src="https://img.shields.io/badge/Codex-supported-111111?style=for-the-badge&logo=openai&logoColor=white" />
  </a>
  <a href="https://github.com/anomalyco/opencode">
    <img alt="OpenCode" src="https://img.shields.io/badge/OpenCode-supported-111111?style=for-the-badge&logo=opencode&logoColor=white" />
  </a>
  <a href="https://github.com/openclaw/openclaw">
    <img alt="OpenClaw" src="https://img.shields.io/badge/OpenClaw-supported-111111?style=for-the-badge&logo=openclaw&logoColor=white" />
  </a>
</p>

`linkedincli` is a cookie-backed, unofficial CLI for:

- posting as yourself
- posting as a company page you manage
- attaching up to 4 images
- reusing the LinkedIn session already open in your browser
- acting as the final publish step inside AI-agent workflows

It does **not** use LinkedIn developer API credentials.

## Why this exists

Most agent tools are good at drafting and editing copy, but not great at the last mile of actually publishing through a real logged-in LinkedIn session.

`linkedincli` gives you that last mile:

- your agent writes or edits the post
- `linkedincli` handles cookies, page discovery, and browser automation
- the final publish step stays explicit, scriptable, and easy to review

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

## CLI usage

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
linkedincli post "we shipped it" --as page-alias
```

Show the automation browser while debugging:

```bash
linkedincli post "debug me" --debug-browser
```

## AI agent usage

`linkedincli` works especially well as the final action layer for coding agents that can call shell commands.

### Claude Code

```bash
claude -p "Draft a concise LinkedIn launch post, then publish it with linkedincli as my company page alias."
```

### Codex

```bash
codex exec "Use linkedincli pages --refresh, then post a short founder update as page-alias."
```

### OpenCode

```bash
opencode run "Write a polished LinkedIn post and publish it with linkedincli."
```

### OpenClaw

```bash
openclaw agent --message "Use linkedincli to publish today's LinkedIn update as page-alias."
```

### Generic agent pattern

If your agent can run shell commands, the pattern is simple:

```bash
linkedincli whoami
linkedincli pages --refresh
linkedincli post "final reviewed copy"
linkedincli post "final reviewed copy" --as page-alias
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
