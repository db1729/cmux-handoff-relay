## Summary

-

## Safety checklist

- [ ] Does not add clipboard, GUI, AppleScript, or background watcher automation.
- [ ] Does not auto-approve, auto-merge, auto-commit, or submit without explicit user intent.
- [ ] Uses documented cmux CLI commands or clearly documents why not.
- [ ] Includes tests for parser, config, CLI, or cmux wrapper behavior when changed.

## Testing

```bash
python -m pytest
```
