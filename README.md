# linkedincli

Cookie-backed LinkedIn posting from the terminal.

## Status

In progress. The goal is a free CLI that:

- uses your existing LinkedIn browser session
- posts as you or as a company page you manage
- supports text posts and image attachments
- works without LinkedIn developer API credentials

## Planned commands

```bash
linkedincli whoami
linkedincli pages --refresh
linkedincli post "hello linkedin"
linkedincli post - --image photo.png --as my-company
```
