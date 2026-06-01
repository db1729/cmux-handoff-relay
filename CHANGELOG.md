# Changelog

## 0.2.0 - Unreleased

- Initial safe manual handoff relay.
- Parse latest `HANDOFF` block from cmux scrollback.
- Preview and confirm before sending.
- Send via documented cmux CLI commands.
- Submit only with explicit CLI `--submit`.
- Support `--cmux-bin` for bundled or non-PATH cmux CLI installs.
- Add `cmux-handoff` console alias.
- Add `doctor`, `discover`, and `init` onboarding commands.
- Add bounded `watch` mode for agent-directed handoffs across configured roles.
- Add `--workspace` for relaying panes outside the caller's current cmux workspace.
- Add CE-first role objects with target-role workflow prefix prepending.
- Add `--no-ce` / `--no-workflow-prefix` to bypass configured workflow prefixes.
- Add automatic CHR continuation contracts plus `--no-handoff-contract`.
- Add repo-local agent rule files to ground final handoff output.
- Isolate malformed blocks and unknown targets per source role in watch mode.
- Reject unbounded `--yes` / `--confirm never` watch runs.
- Validate configured cmux surface IDs and add cmux command timeouts.
- Harden parsing against trailing terminal padding and nested handoff headers.
- Accept known terminal UI gutters around handoff marker lines.
- Add source-role `allow_targets` routing controls.
- Add optional handoff nonce arming and require nonce for automatic relay.
- Add optional `surface_hint` drift checks before non-dry-run sends.
- Add no-routine-choice decision policy to CHR contracts and agent rules.
- Add `--submit-delay` to let target TUIs settle before pressing Enter.
- Add per-role `submit_delay` profile support with CLI override.
- Add per-role `workflow_profile` context-budget hints for CE-shaped handoffs.
- Add per-role `reasoning_profile` advisory effort hints across
  `minimal`/`low`/`medium`/`high`, plus `--reasoning-profile` run override.
- Add agent-specific effort cues for known `agent` values while keeping them
  plain-text advisory prompts.
- Add `--mode ce|smoke`; CE remains the default, while smoke disables CE prefixes
  and CHR contracts for transport validation.
- Document watch exit codes: `1` hard failure, `2` argparse usage error, `3` sent text but Enter failed.
- Make `init` generate a CE-first config by default, with `init --classic` for surface-only configs.
- Add parser, config, dry-run, send-path, onboarding, and watch-mode tests.
- Add OSS governance files.
