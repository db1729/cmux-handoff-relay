# AGENTS.md

## CHR Workflow Contract

This repository is designed to run under `cmux-handoff-relay` in a multi-agent
cmux workspace.

When a prompt is routed by CHR or asks for multi-agent continuation:

- Do the assigned work in the current repo.
- Do not expose secret values.
- Do not run git stage, commit, or push unless the user explicitly asks.
- Do not stop to ask the user to choose among routine implementation options.
- Choose a safe, reversible default and continue.
- Respect any CHR workflow profile. Keep context narrow for `light`, use the
  normal scoped CE loop for `standard`, and reserve broader context loading for
  `deep`.
- Respect any CHR reasoning profile as an advisory effort hint. Keep visible
  output concise; do not expose hidden reasoning.
- End the final response with exactly one continuation decision.

Stop for user input only when secrets, external login, payment, DNS, production
configuration, destructive actions, git stage/commit/push, or an irreversible
product decision is required.

Continuation decision:

- If another worker should continue, print one real CHR handoff block as the
  final output.
- If no next worker is needed, end with `NO HANDOFF`.
- If blocked on a required user decision, do not hand off. End with `NO HANDOFF`,
  then `BLOCKED:`, `RECOMMENDED:`, and `WHY:`.

Use configured target role names such as `main`, `review`, `qa`, and `docs`.
The local `.cmux-handoff.json` is the source of truth when it exists.
If the prompt or CHR contract gives a session nonce, include `nonce=<value>` in
the HANDOFF header.

A real CHR handoff block has this exact structure:

- first line: `<<<HANDOFF target=<role> submit=false>>>`
- middle lines: the prompt for the next worker
- final line: `<<<END_HANDOFF>>>`

When a session nonce is active, the first line is:

- `<<<HANDOFF target=<role> submit=false nonce=<session_nonce>>>`

The marker lines must start at the beginning of the line. Use `submit=false`
by default; `submit=true` is parsed as metadata only and does not press Enter.
Do not print sample handoff blocks in watched panes unless they are the real
final handoff.
