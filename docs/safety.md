# Safety Boundaries

`cmux-handoff-relay` is intentionally operator-controlled and narrow.

## What it does

- Reads recent text from one or more configured cmux surfaces.
- Finds the latest explicit `HANDOFF` block.
- Optionally prepends the target role's configured CE/workflow prefix as plain
  text.
- Appends a plain-text CHR continuation contract by default.
- Enforces any configured source-role `allow_targets` allowlist.
- Enforces a handoff nonce when `--nonce` is set.
- Verifies configured `surface_hint` snippets before non-dry-run sends.
- Previews the extracted payload.
- Asks for explicit confirmation unless the operator passes `--yes` or
  `--confirm never` in watch mode.
- Sends the payload to the configured target surface.
- Presses Enter only when the user passes CLI `--submit`.

## What it does not do

- No cmux app restart, quit, reload, or process kill.
- No clipboard automation.
- No GUI automation.
- No AppleScript mouse or keyboard automation.
- No automatic approval of AI agent actions.
- No automatic code merging.
- No automatic git commits.
- No background daemon or hidden watcher.
- No socket or JSON-RPC cmux API.
- No fixed workflow orchestration or task scheduling.
- No Compound Engineering command execution, installation, or plugin management.
- No enforcement that a model obeys the continuation contract.

`watch` is an explicit foreground command. When the operator passes `--yes`,
the tool relays without per-handoff confirmation and requires a nonce. When the
operator also passes `--submit`, it sends Enter after each payload within the
configured turn limit. The tool rejects unbounded automatic relay:
`--max-turns 0` cannot be combined with `--yes` or `--confirm never`. Use
`--nonce auto` to generate a one-time local session nonce.

## CE workflow prefixes

Role configs may include a `ce_default` value such as `/ce-code-review`. The
relay only prepends that text to the outgoing prompt:

```text
/ce-code-review

<original handoff body>
```

The target agent may interpret that text if its own environment supports
Compound Engineering. The relay itself does not run CE commands, install CE
plugins, inspect CE state, or approve any CE action.

Use `--no-ce` or `--no-workflow-prefix` to send the original handoff body
without the configured prefix.

Use `--mode smoke` only for transport tests. It disables CE prefixes and the
CHR continuation contract for that run, but the default workflow mode remains
CE-first.

## CHR continuation contract

By default, the relay appends a short plain-text contract to every outgoing
payload. It tells the target worker its current role, source role, configured
allowed target roles, and that the final response should either hand off again
or end with `NO HANDOFF`.

This improves workflow continuity but is still prompt text. The relay does not
force the target model to comply, inspect task completion, or decide the next
role itself.

The continuation contract also tells workers not to stop for routine option
selection. They should choose a safe, reversible default and continue. They
should stop only for boundaries such as secrets, external login, payment, DNS,
production config, destructive actions, git stage/commit/push, or irreversible
product decisions.

When a target role has `workflow_profile`, the continuation contract includes a
single context-budget hint. This is intentionally short: CHR does not embed full
CE skill text or broad project context in every handoff.
The hint is advisory and has the same model-compliance limits as the rest of the
plain-text contract.

When a target role has `reasoning_profile`, or the operator passes
`--reasoning-profile`, the continuation contract includes a single advisory
reasoning-effort hint (`minimal`, `low`, `medium`, or `high`). It is plain text
for the target agent, not an API-level model setting, and it must not be treated
as a guarantee that the target will use or expose any particular reasoning
process.
For known `agent` values, CHR may include agent-specific effort wording such as
Codex `model_reasoning_effort`, Claude Code `think harder`,
Gemini/Antigravity `thinking_level`, or Cursor Thinking/Max Mode. This is still
only text inserted into the prompt; CHR does not toggle model selectors, app
modes, or CLI flags. The target agent may still interpret those words through
its own prompt or tool conventions.

Use `--no-handoff-contract` to send without that appended contract.

`--mode smoke` also disables this contract and any profile hints for
transport-only validation. Do not use smoke mode as the normal work mode when
you want workers to continue the handoff chain.

## Nonce arming

`--nonce <value>` makes the relay ignore handoff blocks that do not include the
matching `nonce=<value>` header field. `--nonce auto` generates a one-time local
session nonce and prints it at watch startup.

The nonce is a relay routing token, not a package dependency or CE feature. It
reduces accidental or echoed handoff blocks in watched panes. It does not make
untrusted agent output safe by itself.

When the CHR continuation contract is enabled, the nonce is sent in plain text
to target panes so workers can continue the chain. Any process or prompt that
can read that pane can learn the nonce. Treat it as an accidental-trigger guard,
not a secret authentication boundary.

## Target allowlists

Object role configs may include `allow_targets`. When present, a source role can
handoff only to those targets. This prevents a narrow or low-trust pane from
jumping directly into a more privileged pane.

Surface-only legacy configs remain permissive for compatibility.
An explicit empty `allow_targets` list is invalid, and a role cannot explicitly
target itself.

## Surface hints

Object role configs may include `surface_hint`, a non-secret text snippet that
should appear in the role's cmux screen. `doctor` checks these hints, source
roles are checked while reading, and target roles are checked before sending.

Surface hints are a drift detector, not identity proof. Keep hints stable and
non-secret.

## Submit safety

The handoff block has `submit=true|false` metadata, but metadata alone never
presses Enter. It is parsed and shown in the preview only.

Only this CLI flag can press Enter:

```bash
--submit
```

Without `--submit`, the relay only sends the text payload.

## Multiline risk

cmux `send` may pass newline characters in a way that the target AI TUI treats
as real terminal newlines. That behavior depends on cmux and the target TUI.

The relay mitigates this by:

- previewing the exact payload before sending
- requiring confirmation before every send unless explicitly disabled for watch
  mode
- not pressing Enter by default
- offering `--single-line` to replace internal newlines with spaces
- avoiding parseable example `HANDOFF` blocks inside the automatic continuation
  contract

Do not include secrets in handoff prompts. The payload is previewed on screen and
sent to another local surface.

`--input-file` content is treated like captured scrollback: useful for tests and
dry runs, but still untrusted input.

## Watch mode cautions

Watch mode treats any valid latest `HANDOFF` block in a watched surface as
actionable. Do not print example handoff blocks in watched panes unless you
intend the relay to process them.

Known terminal UI gutters around marker lines, currently `• ` and two leading
spaces, are also actionable. Keep real handoff markers and their matching
`END_HANDOFF` marker consistently rendered, and avoid printing indented or
bulleted examples in watched panes.

Any text visible in a watched surface is untrusted input. Avoid watching panes
that are printing raw web pages, logs, code fences, or example handoff blocks
unless you intentionally want valid latest blocks from that pane to be relayed.

Malformed blocks, partial blocks, and unknown targets are isolated to the source
role in watch mode. The relay warns and keeps polling other roles. This prevents
one bad pane from stopping the whole multi-role watch loop.

If confirmation is enabled and the operator declines a handoff, watch mode stops
instead of silently skipping that handoff. This keeps the failure mode visible.

Each cmux command is bounded by a subprocess timeout. A timeout is reported as a
cmux command error; the relay does not try to repair cmux state.

## cmux app state

The relay does not try to repair cmux socket state by restarting the app. If
cmux CLI commands return socket errors, stop and inspect cmux manually.

Restarting cmux can restore windows, workspaces, panes, working directories, and
some supported agent sessions, but it is not a guarantee that every live process
continues exactly where it was. Treat restart as a separate operator decision,
outside this tool.
