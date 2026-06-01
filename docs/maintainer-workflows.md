# Maintainer Workflows

`cmux-handoff-relay` is designed for maintainers who keep several AI coding
workers visible in cmux and want handoffs to stay explicit, local, and
human-reviewed.

The default model is CE-first and agent-directed. There is no required cycle. A
worker names the next target role, and the relay sends only to that configured
role, optionally with that target role's `ce_default` prefix. The relay also
appends a CHR continuation contract by default so the target worker knows how to
hand off again.

## CE-first role map

Use object role mappings when each cmux pane has a default workflow command:

```bash
cmux-handoff init
```

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
      "submit_delay": 0.4,
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

`allow_targets` keeps low-trust or narrow roles from jumping directly into a
more privileged pane. The default CE-first template routes `docs` back through
`review` before it can reach `main`.

Add `surface_hint` only when a role has stable, non-secret screen text. The
relay checks hints before non-dry-run sends and in `doctor`, but they are drift
detectors rather than identity proof.

Add `submit_delay` when a specific target TUI needs more time between text
insertion and Enter. A CLI `--submit-delay` value overrides role config for that
run.

Add `workflow_profile` as an advisory context-pressure hint. `light` tells the
worker to stay narrow, `standard` keeps the normal CE loop scoped, and `deep` is
reserved for higher-risk work that warrants broader planning or review.

Add `reasoning_profile` as an advisory reasoning-effort hint. `minimal` is for
formatting or very narrow continuation, `low` keeps work short, `medium` asks
for balanced evidence checking, and `high` asks for deeper internal reasoning
while keeping visible output concise. Use `--reasoning-profile` to override it
for one run.
Known `agent` values also get effort wording in that same contract line:
Codex uses `model_reasoning_effort`, Claude Code uses `think`/`think hard`/
`think harder`/`ultrathink`, Gemini or Antigravity uses `thinking_level`/fast
mode wording, and Cursor uses normal/Thinking/Max Mode wording. These are still
plain-text cues; CHR does not toggle those app settings, though the target
agent may interpret the wording through its own conventions.

The relay sends CE prefixes as plain text only. It does not execute or install
Compound Engineering.

Use `cmux-handoff init --classic` only when you want a surface-only config.

## PR review split

Use `main` for implementation and `review` for a second-pass code review.

```text
<<<HANDOFF target=review submit=false>>>
Review the staged diff for behavior regressions, missing tests, and unclear
error handling. Return findings first, with file and line references.
<<<END_HANDOFF>>>
```

```bash
cmux-handoff --from main --dry-run
cmux-handoff --from main
```

With `review.ce_default` set, the target payload begins with:

```text
/ce-code-review
```

Or keep all roles under watch:

```bash
cmux-handoff watch --roles main,review,qa,docs --max-turns 12
```

For a hands-off bounded run after the first manual prompt:

```bash
cmux-handoff watch --roles main,review,qa,docs --yes --submit --max-turns 12 --nonce auto
```

The first prompt to `main` should ask it to follow the repo-local CHR workflow
contract and include the printed session nonce in any handoff header. After
that, each relayed payload repeats the continuation contract and nonce.

## QA verification split

Use `qa` to re-run checks and inspect failure boundaries without giving it
write authority by default.

```text
<<<HANDOFF target=qa submit=false>>>
Run the documented verification commands. Confirm the CLI never restarts cmux,
does not print secrets, and fails safely when the cmux socket is missing.
<<<END_HANDOFF>>>
```

With `qa.ce_default` set, this is delivered under `/ce-debug`.

## Release notes split

Use `docs` to draft release notes after tests pass.

```text
<<<HANDOFF target=docs submit=false>>>
Draft release notes from CHANGELOG.md, README.md, and the final git diff.
Do not invent adoption metrics or claim package publication before release.
<<<END_HANDOFF>>>
```

With `docs.ce_default` set, this is delivered under `/ce-compound`.

## Temporarily bypass CE prefixes

Use this when a target agent should receive the raw handoff body:

```bash
cmux-handoff --from main --no-ce
cmux-handoff watch --roles main,review,qa,docs --no-ce
```

Use this when a target agent should not receive the automatic continuation
contract:

```bash
cmux-handoff --from main --no-handoff-contract
cmux-handoff watch --roles main,review,qa,docs --no-handoff-contract
```

## Workflow modes

The default mode is `ce`: configured CE prefixes are prepended and the CHR
continuation contract is appended.

Use `smoke` only for transport validation, such as a 12-hop directed-pair test:

```bash
cmux-handoff watch --mode smoke --roles main,review,qa,docs --yes --submit --max-turns 12 --nonce auto
```

`smoke` disables CE prefixes and the continuation contract, including
workflow/reasoning profile hints, for that run. It does not remove CE support
from the config or default workflow.

When you intentionally run CE-mode live smoke to exercise workflow and effort
cues, use a short nonce so the HANDOFF header stays on one terminal line.

## Safety properties

- Handoffs are visible text blocks, not hidden background messages.
- Role-to-surface routing lives in a local config file.
- Watch mode deduplicates latest handoff blocks per source role.
- Watch mode baselines existing handoffs by default to avoid replaying stale
  blocks at startup.
- Watch mode skips malformed blocks and unknown targets per source role instead
  of stopping the whole multi-role loop.
- Unbounded auto-submit is rejected.
- Automatic relay with `--yes` requires a handoff nonce.
- Configured surface hints are checked before sending.
- CE prefixes are visible in preview before sending.
- CHR continuation contracts are visible in preview before sending.
- The relay previews the exact payload before sending.
- Confirmation is required before non-dry-run sends.
- The relay does not approve, merge, commit, restart cmux, or control the GUI.
