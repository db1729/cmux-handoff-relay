# GEMINI.md

## CHR Workflow Contract

For CHR-routed tasks in this repo, follow `AGENTS.md`.

Do not stop for routine option selection. Choose a safe, reversible default and
continue. Stop only at the user-input boundaries listed in `AGENTS.md`.

At the end of the final response, choose exactly one:

- Print one real CHR handoff block if another worker should continue.
- End with `NO HANDOFF` if no next worker is needed.
- End with `NO HANDOFF`, `BLOCKED:`, `RECOMMENDED:`, and `WHY:` if a required
  user decision blocks progress.

A real block uses the marker lines documented in `AGENTS.md`, with the marker
lines starting at the beginning of the line. Do not print sample handoff blocks
unless they are the real final handoff.
