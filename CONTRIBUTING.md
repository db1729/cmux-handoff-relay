# Contributing

This project intentionally stays small and auditable.

## Local checks

```bash
python -m pip install -e ".[test]"
python -m pytest
```

## Design constraints

- Use documented cmux CLI commands.
- Keep dependencies minimal.
- Do not add clipboard, GUI, AppleScript, or mouse/keyboard automation.
- Do not add automatic approval, merge, commit, or background watcher behavior
  without a clear design discussion.
- Preserve the manual-trigger safety model.

## Pull requests

Keep changes scoped. Include tests for parser, config, and CLI behavior when
changing those surfaces.

## Maintainer review checklist

- Does the change preserve preview-before-send behavior?
- Does it keep `submit=true` metadata separate from the `--submit` action?
- Does it avoid printing secrets or config values beyond local surface IDs?
- Does it avoid cmux restart, reload, kill, GUI, clipboard, or AppleScript
  automation?
- Does it include a test for any new failure boundary?
