# Roadmap

## v0.1 / v0.2 - Safe Manual Relay

- Parse explicit handoff blocks.
- Preview before sending.
- Require confirmation before manual sends and make automatic watch mode explicit.
- Use documented cmux CLI commands only.
- Support DMG-installed cmux via app-bundle CLI auto-detection.
- Add `doctor`, `discover`, and `init` commands for first-run setup.
- Add bounded `watch` mode for agent-directed handoffs.

## v0.3 - Public Distribution

- Publish to PyPI for `pipx install cmux-handoff-relay`.
- Add a Homebrew tap formula.
- Add release artifacts and signed checksums.
- Add smoke-test instructions for fresh macOS machines.
- Collect early public feedback from cmux users.

## v0.4 - Maintainer Workflow Polish

- Improve config validation and diagnostics.
- Add structured `--json` output for `doctor` and `discover`.
- Add examples for reviewer, QA, and docs-worker handoffs.
- Add structured event output for `watch`.
- Evaluate an upstream cmux PR if the workflow proves useful.
- Add optional machine-readable handoff logs without recording prompt bodies.

## Non-goals

- No background daemon or hidden watcher.
- No auto-approval of agent actions.
- No auto-merge or auto-commit behavior.
- No GUI, clipboard, or AppleScript automation.
