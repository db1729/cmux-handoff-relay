import io
from cmux_handoff_relay.cli import run


def write_fake_cmux(tmp_path, *, ping_ok: bool = True, list_panels_ok: bool = True):
    path = tmp_path / "cmux"
    ping_case = "echo pong" if ping_ok else "echo broken >&2; exit 1"
    list_panels_case = (
        'echo "pane:1"\n    echo "pane:2"'
        if list_panels_ok
        else "echo no panels >&2; exit 1"
    )
    path.write_text(
        f"""#!/bin/sh
case "$1" in
  version)
    echo "cmux 0.64.10"
    ;;
  ping)
    {ping_case}
    ;;
  list-panels)
    {list_panels_case}
    ;;
  list-pane-surfaces)
    echo "surface:1"
    echo "surface:2"
    ;;
  read-screen)
    echo "OpenAI Codex"
    ;;
  *)
    echo "unknown command: $1" >&2
    exit 1
    ;;
esac
""",
        encoding="utf-8",
    )
    path.chmod(0o755)
    return path


def test_doctor_ok_with_fake_cmux(tmp_path) -> None:
    cmux_bin = write_fake_cmux(tmp_path)
    config = tmp_path / ".cmux-handoff.json"
    config.write_text('{"roles":{"main":"surface:1","review":"surface:2"}}', encoding="utf-8")
    stdout = io.StringIO()
    stderr = io.StringIO()

    result = run(
        ["doctor", "--cmux-bin", str(cmux_bin), "--config", str(config)],
        stdout=stdout,
        stderr=stderr,
    )

    assert result == 0
    assert stderr.getvalue() == ""
    assert "cmux version: cmux 0.64.10" in stdout.getvalue()
    assert "cmux socket: ok" in stdout.getvalue()
    assert "doctor result: ok" in stdout.getvalue()


def test_doctor_checks_configured_surface_hints(tmp_path) -> None:
    cmux_bin = write_fake_cmux(tmp_path)
    config = tmp_path / ".cmux-handoff.json"
    config.write_text(
        '{"roles":{"main":{"surface":"surface:1","surface_hint":"OpenAI Codex"}}}',
        encoding="utf-8",
    )
    stdout = io.StringIO()
    stderr = io.StringIO()

    result = run(
        ["doctor", "--cmux-bin", str(cmux_bin), "--config", str(config)],
        stdout=stdout,
        stderr=stderr,
    )

    assert result == 0
    assert stderr.getvalue() == ""
    assert "surface hints: ok (1 checked)" in stdout.getvalue()


def test_doctor_reports_socket_failure_without_repairing(tmp_path) -> None:
    cmux_bin = write_fake_cmux(tmp_path, ping_ok=False)
    stdout = io.StringIO()
    stderr = io.StringIO()

    result = run(
        ["doctor", "--cmux-bin", str(cmux_bin)],
        stdout=stdout,
        stderr=stderr,
    )

    assert result == 1
    assert "cmux socket: failed" in stdout.getvalue()
    assert "doctor result: attention needed" in stdout.getvalue()
    assert "broken" in stderr.getvalue()


def test_doctor_reports_missing_config_as_attention(tmp_path) -> None:
    cmux_bin = write_fake_cmux(tmp_path)
    missing_config = tmp_path / ".cmux-handoff.json"
    stdout = io.StringIO()
    stderr = io.StringIO()

    result = run(
        ["doctor", "--cmux-bin", str(cmux_bin), "--config", str(missing_config)],
        stdout=stdout,
        stderr=stderr,
    )

    assert result == 1
    assert stderr.getvalue() == ""
    assert "cmux socket: ok" in stdout.getvalue()
    assert f"config: missing ({missing_config})" in stdout.getvalue()
    assert "doctor result: attention needed" in stdout.getvalue()


def test_discover_prints_panels_and_surfaces(tmp_path) -> None:
    cmux_bin = write_fake_cmux(tmp_path)
    stdout = io.StringIO()
    stderr = io.StringIO()

    result = run(
        ["discover", "--cmux-bin", str(cmux_bin), "--pane", "pane:1"],
        stdout=stdout,
        stderr=stderr,
    )

    assert result == 0
    assert stderr.getvalue() == ""
    output = stdout.getvalue()
    assert "pane:1" in output
    assert "surface:1" in output
    assert "--- BEGIN PANELS ---" in output
    assert "--- BEGIN SURFACES ---" in output


def test_discover_failure_does_not_print_partial_sections(tmp_path) -> None:
    cmux_bin = write_fake_cmux(tmp_path, list_panels_ok=False)
    stdout = io.StringIO()
    stderr = io.StringIO()

    result = run(
        ["discover", "--cmux-bin", str(cmux_bin)],
        stdout=stdout,
        stderr=stderr,
    )

    assert result == 1
    assert stdout.getvalue() == ""
    assert "no panels" in stderr.getvalue()


def test_init_creates_config_without_overwriting(tmp_path) -> None:
    config = tmp_path / ".cmux-handoff.json"
    stdout = io.StringIO()
    stderr = io.StringIO()

    result = run(
        ["init", "--config", str(config)],
        stdout=stdout,
        stderr=stderr,
    )

    assert result == 0
    assert stderr.getvalue() == ""
    assert config.exists()
    config_text = config.read_text(encoding="utf-8")
    assert '"main": {' in config_text
    assert '"ce_default": "/ce-work"' in config_text
    assert '"ce_default": "/ce-code-review"' in config_text
    assert '"workflow_profile": "standard"' in config_text
    assert '"workflow_profile": "light"' in config_text
    assert '"reasoning_profile": "high"' in config_text
    assert '"reasoning_profile": "medium"' in config_text
    assert '"reasoning_profile": "low"' in config_text
    assert '"reasoning_profile": "minimal"' in config_text
    assert "cmux-handoff discover" in stdout.getvalue()
    assert "Template: CE-first workflow prefixes" in stdout.getvalue()

    second_stdout = io.StringIO()
    second_stderr = io.StringIO()
    second = run(
        ["init", "--config", str(config)],
        stdout=second_stdout,
        stderr=second_stderr,
    )

    assert second == 1
    assert "already exists" in second_stderr.getvalue()


def test_init_classic_creates_surface_only_config(tmp_path) -> None:
    config = tmp_path / ".cmux-handoff.json"
    stdout = io.StringIO()
    stderr = io.StringIO()

    result = run(
        ["init", "--config", str(config), "--classic"],
        stdout=stdout,
        stderr=stderr,
    )

    assert result == 0
    assert stderr.getvalue() == ""
    config_text = config.read_text(encoding="utf-8")
    assert '"main": "surface:1"' in config_text
    assert "ce_default" not in config_text
    assert "Template: classic surface-only" in stdout.getvalue()


def test_init_force_requires_yes(tmp_path) -> None:
    config = tmp_path / ".cmux-handoff.json"
    config.write_text('{"roles":{"main":"surface:old"}}', encoding="utf-8")
    stdout = io.StringIO()
    stderr = io.StringIO()
    stdin = io.StringIO("no\n")

    result = run(
        ["init", "--config", str(config), "--force"],
        stdout=stdout,
        stderr=stderr,
        stdin=stdin,
    )

    assert result == 1
    assert "Aborted by user" in stderr.getvalue()
    assert "surface:old" in config.read_text(encoding="utf-8")


def test_cmux_bin_can_come_from_environment(monkeypatch, tmp_path) -> None:
    cmux_bin = write_fake_cmux(tmp_path)
    config = tmp_path / ".cmux-handoff.json"
    config.write_text('{"roles":{"main":"surface:1","review":"surface:2"}}', encoding="utf-8")
    monkeypatch.setenv("CMUX_HANDOFF_CMUX_BIN", str(cmux_bin))
    stdout = io.StringIO()
    stderr = io.StringIO()

    result = run(["doctor", "--config", str(config)], stdout=stdout, stderr=stderr)

    assert result == 0
    assert str(cmux_bin) in stdout.getvalue()
