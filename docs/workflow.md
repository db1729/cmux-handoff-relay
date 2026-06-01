# 4-pane Workflow

This project targets a cmux setup with several AI coding workers visible at
once. Roles are an address book, not a fixed pipeline: each worker can choose
the next target role in its own `HANDOFF` block.

Example roles:

- `main`: primary executor
- `review`: code reviewer
- `qa`: test checker
- `docs`: handoff or documentation writer

## 1. Discover cmux surfaces

Use documented cmux commands:

```bash
cmux list-panels
cmux list-pane-surfaces --pane <pane_id>
```

Pick the surface ID for each role.

You can also use the relay helper:

```bash
cmux-handoff discover
cmux-handoff discover --pane <pane_id>
```

## 2. Create local config

Create `.cmux-handoff.json` manually or with:

```bash
cmux-handoff init
```

The default generated config is CE-first and includes `allow_targets` so each
source role can hand off only to approved next roles. Surface-only configs are
still supported for compatibility:

You can add `surface_hint` to object role configs when a pane has stable,
non-secret screen text that should be checked before sending.

You can add `workflow_profile` to object role configs as an advisory
context-pressure hint without sending full CE instructions. Use `light` for
narrow review or QA hops, `standard` for normal work, and `deep` only for
high-risk work.

You can add `reasoning_profile` to object role configs as an advisory
reasoning-effort hint. Use `minimal`, `low`, `medium`, or `high`;
`--reasoning-profile` overrides the role value for one run.
When `agent` is known, the same line includes an agent-specific effort cue such
as Codex `model_reasoning_effort`, Claude Code `think harder`,
Gemini/Antigravity `thinking_level`, or Cursor Thinking/Max Mode. These cues
are advisory text only; CHR does not change the target app's native model
setting. The target agent may still interpret the wording through its own
conventions.

You can add `submit_delay` to object role configs when a specific target TUI
needs more time between receiving text and pressing Enter. `--submit-delay`
overrides that role value for one run.

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

This file should contain only local role-to-surface mappings, not secrets.
Surface IDs must use the `surface:<id>` shape.

## 3. Ask workers to emit explicit handoff blocks

For uninterrupted watch-mode flow, each CHR-routed worker must end with either
one real handoff block or `NO HANDOFF`.

When a worker wants another role to continue, it should print:

```text
<<<HANDOFF target=review submit=false>>>
Prompt text for the next worker goes here.
<<<END_HANDOFF>>>
```

When watch is armed with `--nonce`, the header must include that nonce:

```text
<<<HANDOFF target=review submit=false nonce=<session_nonce>>>
Prompt text for the next worker goes here.
<<<END_HANDOFF>>>
```

The relay uses the latest candidate block. If the latest candidate is malformed,
it fails instead of falling back to an older block.

Repo-local rule files ground this contract for common agents:

- `AGENTS.md`
- `CLAUDE.md`
- `GEMINI.md`
- `.cursor/rules/cmux-handoff-relay.mdc`

## 4. Preview the handoff

```bash
cmux-handoff --from main --dry-run
```

## 5. Send manually

```bash
cmux-handoff --from main
```

The relay asks for `yes` before sending.

## 6. Submit only when intentional

```bash
cmux-handoff --from main --submit
```

`--submit` sends the payload and then calls:

```bash
cmux send-key --surface <surface_id> enter
```

The block's `submit=true` metadata is never enough to submit.

## 7. Watch agent-directed handoffs

Once the role-to-surface config is correct, watch all roles:

```bash
cmux-handoff watch --roles main,review,qa,docs
```

Watch mode polls each source role, parses its latest `HANDOFF` block, appends a
short continuation contract, and sends the payload to the block's `target` role
when a new block appears. It does not impose a fixed order such as
`main -> review -> qa`. The workers decide the next target.

By default, watch mode baselines handoffs already visible at startup and waits
for new ones. To process the latest existing handoffs immediately:

```bash
cmux-handoff watch --relay-existing
```

For a bounded automatic run:

```bash
cmux-handoff watch --yes --submit --max-turns 12 --nonce auto
```

For transport-only smoke validation, keep CE installed/configured but disable
CE prefixes and continuation contracts, including workflow/reasoning profile
hints, for the run:

```bash
cmux-handoff watch --mode smoke --yes --submit --max-turns 12 --nonce auto
```

For CE-mode live smoke where you intentionally want workflow and effort cues in
the payload, keep the nonce short enough that terminal soft-wrap does not split
the HANDOFF header.

Start the workflow manually by sending the first prompt to the first worker,
then leave watch running. The first prompt should ask that worker to follow the
repo-local CHR workflow contract and include the printed session nonce in any
handoff header.

Use `--max-turns 0` only when you intentionally want an unlimited watch loop.
It cannot be combined with `--yes`/`--confirm never`. Automatic relay with
`--yes` requires `--nonce` or `--nonce auto`.
When confirmation is enabled and you decline a handoff, the watch command stops
instead of skipping that block.

Malformed blocks, partial blocks, and unknown targets are skipped per source
role in watch mode. The relay writes a warning and keeps checking the other
watched roles.
