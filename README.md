# cmux-handoff-relay

`cmux-handoff-relay` is a CE-first local CLI for safely relaying explicit
handoff prompts between AI coding workers running in a 4-pane cmux workflow.

CE means Compound Engineering workflow prompts such as `/ce-work`,
`/ce-code-review`, `/ce-debug`, and `/ce-compound`. The relay does not install
or execute Compound Engineering. It prepends configured workflow text and, by
default, appends a short CHR continuation contract to the target worker's
prompt.

It is not an approval system, auto-merge tool, or autonomous code manager. It
does relay agent-directed prompts between configured cmux surfaces, and its
default continuation contract asks workers to continue or hand off again. The
operator still controls confirmation, automatic mode, nonce arming, and turn
limits.

## Why this exists

Maintainers increasingly split work across focused AI coding workers: one pane
executes, another reviews, another checks tests, and another writes docs. The
unsafe part is usually not the model. It is the manual glue between panes:
copying the wrong prompt, pasting into the wrong surface, or accidentally
submitting before the human has reviewed the handoff.

This tool makes that glue explicit and auditable:

- workers must emit a structured `HANDOFF` block
- the relay resolves the configured target surface
- the relay can prepend the target role's CE workflow prefix
- the relay appends a CHR continuation contract so the next worker knows how to
  hand off again
- the exact payload is previewed before sending
- `submit=true` in the block is metadata only
- Enter is pressed only when the human passes `--submit`
- watch mode can relay agent-directed handoffs without imposing a fixed cycle

## Project status

`0.2.0` is an alpha release for local cmux users and maintainers who already
run multi-pane AI coding workflows. The project is dependency-light, tested,
and intentionally narrow so security-sensitive behavior stays easy to review.

## MVP behavior

The relay detects the latest block shaped like this:

```text
<<<HANDOFF target=review submit=false>>>
Prompt text for the next worker goes here.
<<<END_HANDOFF>>>
```

For armed automatic watch runs, include the session nonce:

```text
<<<HANDOFF target=review submit=false nonce=<session_nonce>>>
Prompt text for the next worker goes here.
<<<END_HANDOFF>>>
```

It parses:

- `target`: role name from your local config
- `submit`: metadata only; it never submits by itself
- `nonce`: optional session nonce required when watch is armed with `--nonce`
- body: prompt text to send

Only the CLI `--submit` flag can press Enter.

## Install for local development

```bash
python -m pip install -e ".[test]"
```

This installs two equivalent commands:

```bash
cmux-handoff --help
cmux-handoff-relay --help
```

## Quick start

Check your local cmux setup without changing cmux state:

```bash
cmux-handoff doctor
```

Create a CE-first starter config:

```bash
cmux-handoff init
```

Discover panes and surfaces:

```bash
cmux-handoff discover
cmux-handoff discover --pane <pane_id>
```

Run a dry preview from a source role:

```bash
cmux-handoff --from main --dry-run
```

Relay after preview and confirmation:

```bash
cmux-handoff --from main
```

Watch all configured roles for new agent-directed handoffs:

```bash
cmux-handoff watch
```

Run an intentionally automatic watch loop:

```bash
cmux-handoff watch --yes --submit --max-turns 12 --nonce auto
```

## cmux CLI path

If cmux was installed from a DMG, the CLI may exist inside the app bundle even
when `cmux` is not on `PATH`:

```bash
/Applications/cmux.app/Contents/Resources/bin/cmux version
```

You can either pass that path directly:

```bash
cmux-handoff --cmux-bin /Applications/cmux.app/Contents/Resources/bin/cmux --from main --dry-run
```

Or create a symlink somewhere already on `PATH`:

```bash
ln -s /Applications/cmux.app/Contents/Resources/bin/cmux /opt/homebrew/bin/cmux
```

Use `ln -sf` only when you have intentionally verified the existing destination.

## Config

Default config path:

```text
.cmux-handoff.json
```

`cmux-handoff init` creates a CE-first object config by default:

```json
{
  "roles": {
    "main": {
      "surface": "surface:1",
      "agent": "codex",
      "ce_default": "/ce-work",
      "workflow_profile": "standard",
      "reasoning_profile": "high",
      "allow_targets": ["review", "qa", "docs"]
    },
    "review": {
      "surface": "surface:2",
      "agent": "claude",
      "ce_default": "/ce-code-review",
      "workflow_profile": "light",
      "reasoning_profile": "medium",
      "allow_targets": ["main", "qa", "docs"]
    },
    "qa": {
      "surface": "surface:3",
      "agent": "gemini",
      "ce_default": "/ce-debug",
      "workflow_profile": "light",
      "reasoning_profile": "low",
      "allow_targets": ["main", "review", "docs"]
    },
    "docs": {
      "surface": "surface:4",
      "agent": "cursor",
      "ce_default": "/ce-compound",
      "workflow_profile": "light",
      "reasoning_profile": "minimal",
      "allow_targets": ["review"]
    }
  }
}
```

`allow_targets` is an optional per-source allowlist. When present, the source
role can hand off only to those roles. Surface-only legacy configs keep the
old permissive behavior for compatibility.

Object role configs may also include `surface_hint`, a non-secret text snippet
expected to appear in that role's cmux screen. `doctor` checks configured hints,
and non-dry-run sends verify the target hint before sending.

Object role configs may include `workflow_profile` to give the target worker a
small context-budget hint without embedding full CE instructions. Supported
values are `light`, `standard`, and `deep`.

Object role configs may include `reasoning_profile` to give the target worker an
advisory reasoning-effort hint. Supported values are `minimal`, `low`,
`medium`, and `high`. This is plain text, not an API-level model setting.
Use `minimal` for formatting or smoke-like continuation, `low` for narrow
edits, `medium` for normal review/debug, and `high` for planning or risky
cross-module work.

When `agent` is known, CHR also renders an agent-specific effort cue in the same
contract line:

- `codex`/`openai`: `model_reasoning_effort="minimal|low|medium|high"`
- `claude`: `think`, `think hard`, `think harder`, `ultrathink`
- `gemini`/`agy`/`antigravity`: Gemini/Antigravity thinking levels or fast mode
- `cursor`: normal, Thinking model, or Max Mode cues

These cues are still plain text. CHR does not change the target app's model,
toggle Thinking/Max Mode, or set native CLI flags, but the target agent may
interpret the wording through its own conventions.

Object role configs may also include `submit_delay` when one target TUI needs a
longer paste-settle window before Enter is pressed:

```json
{
  "roles": {
    "review": {
      "surface": "surface:2",
      "agent": "claude",
      "ce_default": "/ce-code-review",
      "workflow_profile": "light",
      "reasoning_profile": "medium",
      "submit_delay": 0.4
    }
  }
}
```

With that config, a `target=review` handoff sends this plain text payload:

```text
/ce-code-review

<original handoff body>

CHR handoff contract:
<allowed next targets, workflow/reasoning profiles, and continuation instructions>
```

Disable configured workflow prefixes when needed:

```bash
cmux-handoff --from main --no-ce
cmux-handoff watch --no-ce
```

Disable the appended CHR continuation contract when you intentionally want the
raw body:

```bash
cmux-handoff --from main --no-handoff-contract
cmux-handoff watch --no-handoff-contract
```

Override the advisory reasoning profile for one run:

```bash
cmux-handoff --from main --reasoning-profile high
cmux-handoff watch --reasoning-profile medium
```

For transport-only smoke tests, use `--mode smoke`. This disables both CE
prefixes and the CHR continuation contract, including workflow/reasoning
profile hints, for that run. The default mode is still `ce`.

```bash
cmux-handoff watch --mode smoke --yes --submit --max-turns 12 --nonce auto
```

Surface-only configs remain supported:

```json
{
  "roles": {
    "main": "surface:1",
    "review": "surface:2",
    "qa": "surface:3",
    "docs": "surface:4"
  }
}
```

Create that legacy template explicitly:

```bash
cmux-handoff init --classic
```

Do not put secrets in this config. It should only contain local role names and
cmux surface IDs shaped like `surface:<id>` plus non-secret workflow labels.

## Discover cmux surfaces

Use documented cmux commands:

```bash
cmux list-panels
cmux list-pane-surfaces --pane <pane_id>
```

Then copy the surface IDs into `.cmux-handoff.json`.

## Usage

Preview only:

```bash
cmux-handoff --from main --dry-run
```

Read from cmux, preview, ask for confirmation, then send without Enter:

```bash
cmux-handoff --from main
```

Send and explicitly press Enter:

```bash
cmux-handoff --from main --submit
```

Use a custom config:

```bash
cmux-handoff --config .cmux-handoff.json --from review
```

Read more scrollback:

```bash
cmux-handoff --from main --lines 200
```

Replace internal newlines with spaces before sending:

```bash
cmux-handoff --from main --single-line
```

Run a cmux-free dry run from a file:

```bash
cmux-handoff --config examples/cmux-handoff.json --from main --dry-run --input-file examples/handoff-blocks.txt
```

Treat `--input-file` contents as untrusted captured text, the same as cmux
scrollback.

Preview the CE-first example config:

```bash
cmux-handoff --config examples/cmux-handoff-ce.json --from main --dry-run --input-file examples/handoff-blocks.txt
```

Use a bundled cmux CLI path:

```bash
cmux-handoff --cmux-bin /Applications/cmux.app/Contents/Resources/bin/cmux --from main
```

## Watch mode

Watch mode is for the workflow where each worker decides the next target role.
The config is an address book, not a fixed pipeline.

```bash
cmux-handoff watch --roles main,review,qa,docs
```

By default, watch mode:

- watches every configured role unless `--roles` is passed
- baselines handoff blocks already visible at startup
- relays only new handoff blocks
- appends a continuation contract to each payload
- asks for confirmation before each send
- stops after `--max-turns 12`
- never presses Enter unless `--submit` is passed

Process latest existing blocks at startup:

```bash
cmux-handoff watch --relay-existing
```

Run without per-handoff confirmation:

```bash
cmux-handoff watch --yes --max-turns 12 --nonce auto
```

Run a bounded fully automatic loop that submits each prompt:

```bash
cmux-handoff watch --yes --submit --max-turns 12 --nonce auto
```

In this mode, the operator is intentionally choosing a bounded automatic
relay-and-submit loop. Use `--max-turns` to keep the run finite. Automatic
relay requires `--nonce`; `--nonce auto` prints a one-time session nonce that
must appear in watched handoff headers. `--max-turns 0` is rejected when
combined with `--yes`/`--confirm never`.

If you run CHR from a different cmux workspace than the panes being watched,
pass the workspace explicitly:

```bash
cmux-handoff watch --workspace workspace:7 --roles main,review,qa,docs
```

Run a deterministic transport smoke without CE prefixes or continuation
contracts:

```bash
cmux-handoff watch --mode smoke --workspace workspace:7 --roles main,review,qa,docs --yes --submit --max-turns 12 --nonce auto
```

Stop after quiet polling cycles, useful for scripts and tests:

```bash
cmux-handoff watch --idle-polls 3
```

Watch mode treats any valid latest `HANDOFF` block as actionable. Avoid printing
example handoff blocks in watched panes unless you intend the relay to process
them.

Some terminal UIs render assistant output with a small gutter such as `• ` or
two leading spaces. The parser accepts that known gutter around marker lines so
Codex-style panes can still emit real handoff blocks.
Those guttered marker lines are actionable in watch mode; avoid printing
bulleted or indented example handoffs in watched panes unless you intend them to
be relayed.

Malformed blocks and unknown targets are isolated to the source role in watch
mode: the relay warns, skips that role for the current poll, and keeps checking
the other watched roles.

Example transcript. Payload character counts below use the literal
`<generated>` placeholder; real `--nonce auto` counts vary with the generated
nonce length.

```text
$ cmux-handoff watch --roles main,review,qa,docs --relay-existing --yes --max-turns 2 --nonce auto
Watching roles: main, review, qa, docs
Confirmation: none
Max turns: 2
Session nonce: <generated>
Watch turn: 1
Handoff preview
Source role: main
Source surface: surface:1
Target role: review
Target surface: surface:2
Workflow prefix: /ce-code-review
Workflow profile: light
Reasoning profile: medium
Agent effort cue: Claude Code "think harder"
Handoff contract: enabled
Block submit metadata: false (parsed only)
CLI --submit: false
Payload characters: 1262
--- BEGIN PAYLOAD ---
/ce-code-review

Review the current diff and return findings first.

CHR handoff contract:
- Current role: review; source role: main; available target roles: main, qa, docs.
- Workflow profile: light. Keep context lean; use the handoff body and directly relevant files, then summarize before handoff.
- Reasoning profile: medium. Use balanced internal reasoning; check the directly relevant evidence before acting. Agent effort cue: Claude Code "think harder" (plain-text hint; CHR does not change app settings, but the target agent may interpret it).
- Future handoff headers from this worker must include `nonce=<generated>`.
- Default to choosing a safe, reversible option and continue without asking the user to choose.
- Stop for user input only when secrets, external login, payment, DNS, production config, destructive actions, git stage/commit/push, or an irreversible product decision is required.
- If blocked, do not hand off. End with `NO HANDOFF`, then `BLOCKED:`, `RECOMMENDED:`, and `WHY:`.
- When finished, either hand off by printing one valid CHR handoff block as the final output, or end with `NO HANDOFF` if no next worker is needed.
- Follow the exact handoff block format from the repo-local agent rules. Do not print sample handoff blocks.
--- END PAYLOAD ---
Sent payload. Enter was not pressed.
Watch turn: 2
Handoff preview
Source role: review
Source surface: surface:2
Target role: qa
Target surface: surface:3
Workflow prefix: /ce-debug
Workflow profile: light
Reasoning profile: low
Agent effort cue: Gemini/Antigravity thinking_level=LOW
Handoff contract: enabled
Block submit metadata: false (parsed only)
CLI --submit: false
Payload characters: 1261
--- BEGIN PAYLOAD ---
/ce-debug

Run tests and report failing commands only.

CHR handoff contract:
- Current role: qa; source role: review; available target roles: main, review, docs.
- Workflow profile: light. Keep context lean; use the handoff body and directly relevant files, then summarize before handoff.
- Reasoning profile: low. Use concise internal reasoning and avoid broad exploration unless the task is blocked. Agent effort cue: Gemini/Antigravity thinking_level=LOW (plain-text hint; CHR does not change app settings, but the target agent may interpret it).
- Future handoff headers from this worker must include `nonce=<generated>`.
- Default to choosing a safe, reversible option and continue without asking the user to choose.
- Stop for user input only when secrets, external login, payment, DNS, production config, destructive actions, git stage/commit/push, or an irreversible product decision is required.
- If blocked, do not hand off. End with `NO HANDOFF`, then `BLOCKED:`, `RECOMMENDED:`, and `WHY:`.
- When finished, either hand off by printing one valid CHR handoff block as the final output, or end with `NO HANDOFF` if no next worker is needed.
- Follow the exact handoff block format from the repo-local agent rules. Do not print sample handoff blocks.
--- END PAYLOAD ---
Sent payload. Enter was not pressed.
Watch stopped: max turns reached.
```

## cmux commands used

Read source surface:

```bash
cmux read-screen --scrollback --lines <N> --surface <surface_id>
```

Send text:

```bash
cmux send --surface <surface_id> -- <text>
```

Submit only when `--submit` is passed:

```bash
cmux send-key --surface <surface_id> enter
```

CHR waits the target role's configured `submit_delay` between sending text and
pressing Enter, falling back to `0.2` seconds. Use
`--submit-delay <seconds>` to override that value for one run.

Each cmux CLI command has a 10 second timeout so a blocked cmux subprocess does
not silently hang a bounded watch run forever.

Watch exits with code `3` when text was sent but pressing Enter failed. This
distinguishes degraded completion from hard relay failures, which use code `1`,
and from argument usage errors, which argparse reports as code `2`.

## Multiline note

cmux `send` behavior for multiline text depends on cmux and the target agent
TUI. Some TUIs may treat newline characters as real terminal newlines. The relay
therefore always previews the exact payload before sending and asks for
confirmation. Use `--single-line` if you want internal newlines replaced with
spaces.

## Tests

```bash
python -m pytest
```

## Build

```bash
python -m pip install -e ".[dev]"
python -m build
```

## Safety

See [docs/safety.md](docs/safety.md), [docs/workflow.md](docs/workflow.md), and
[docs/maintainer-workflows.md](docs/maintainer-workflows.md).
