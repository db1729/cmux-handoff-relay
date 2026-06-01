# Security Policy

`cmux-handoff-relay` is designed to be conservative local automation.

## Supported versions

The project is pre-1.0. Security fixes target the latest released version.

## Reporting a vulnerability

Open a private security advisory on GitHub if available. If not, open a minimal
public issue that describes the affected behavior without sharing secrets,
tokens, private prompts, or sensitive terminal output.

## Security boundaries

- The config must not contain secrets.
- The tool previews payloads before sending.
- The tool asks for explicit confirmation before every send.
- The tool does not press Enter unless `--submit` is passed.
- The tool does not restart, reload, or repair cmux.
- The tool does not automate clipboard, GUI, AppleScript, git commits, or merges.
