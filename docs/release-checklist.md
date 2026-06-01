# Release Checklist

Use this checklist before publishing a public release.

## Local verification

```bash
python -m pip install -e ".[dev]"
python -m pytest
cmux-handoff --help
cmux-handoff --config examples/cmux-handoff.json --from main --dry-run --input-file examples/handoff-blocks.txt
python -m build
```

## cmux boundary checks

- With cmux running, `cmux-handoff doctor --config examples/cmux-handoff.json`
  should report socket and config status without changing cmux state.
- With cmux running, `cmux-handoff watch --config examples/cmux-handoff.json
  --roles main --idle-polls 1 --interval 0` should stop cleanly without
  changing cmux state when there is no new handoff.
- For local end-to-end transport validation, use a disposable cmux workspace
  and run a bounded `--mode smoke` watch such as 12 directed handoffs. Smoke
  mode is transport-only and should not replace normal CE-first workflow checks.
- With cmux stopped, `doctor` and `discover` should fail clearly and must not
  restart, kill, or reload cmux.
- A dry run with `--input-file` must not call cmux.
- Watch mode should baseline stale handoff blocks by default and stop cleanly
  when bounded with `--max-turns` or `--idle-polls`.

## Repository checks

- README describes the problem, safety model, install path, and examples.
- `docs/safety.md` and `docs/maintainer-workflows.md` match current behavior.
- Issue and PR templates are present.
- GitHub Actions CI passes on the public repository.
- No local config, secrets, virtualenvs, caches, `outputs/`, or `work/` files
  are committed.

## Release notes

- Update `CHANGELOG.md`.
- Tag the release after CI is green.
- Do not announce PyPI, Homebrew, or external adoption until those signals exist.
