from pathlib import Path
import subprocess

import pytest

from cmux_handoff_relay.cmux import (
    CmuxClient,
    detect_cmux_executable,
    validate_workspace_ref,
)
from cmux_handoff_relay.errors import CmuxCommandError


def test_detect_cmux_executable_uses_explicit_path() -> None:
    assert detect_cmux_executable("/custom/cmux") == "/custom/cmux"


def test_detect_cmux_executable_uses_path(monkeypatch, tmp_path) -> None:
    fake = tmp_path / "cmux"
    fake.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path))

    assert Path(detect_cmux_executable()).name == "cmux"


def test_send_text_separates_payload_from_options(tmp_path) -> None:
    log = tmp_path / "args.log"
    fake = tmp_path / "cmux"
    fake.write_text(
        f"""#!/bin/sh
for arg in "$@"; do
  printf '%s\\n' "$arg" >> {str(log)!r}
done
""",
        encoding="utf-8",
    )
    fake.chmod(0o755)

    CmuxClient(str(fake)).send_text("surface:2", "--looks-like-an-option")

    assert log.read_text(encoding="utf-8").splitlines() == [
        "send",
        "--surface",
        "surface:2",
        "--",
        "--looks-like-an-option",
    ]


def test_workspace_is_passed_before_surface_args(tmp_path) -> None:
    log = tmp_path / "args.log"
    fake = tmp_path / "cmux"
    fake.write_text(
        f"""#!/bin/sh
for arg in "$@"; do
  printf '%s\\n' "$arg" >> {str(log)!r}
done
""",
        encoding="utf-8",
    )
    fake.chmod(0o755)

    CmuxClient(str(fake), workspace="workspace:7").send_enter("surface:2")

    assert log.read_text(encoding="utf-8").splitlines() == [
        "send-key",
        "--workspace",
        "workspace:7",
        "--surface",
        "surface:2",
        "enter",
    ]


def test_workspace_ref_validation_rejects_option_like_values() -> None:
    with pytest.raises(CmuxCommandError, match="workspace"):
        validate_workspace_ref("-workspace:7")


def test_workspace_ref_validation_rejects_spaces() -> None:
    with pytest.raises(CmuxCommandError, match="workspace"):
        validate_workspace_ref("workspace:7 --bad")


def test_cmux_client_validates_workspace_on_init() -> None:
    with pytest.raises(CmuxCommandError, match="workspace"):
        CmuxClient("/fake/cmux", workspace="-workspace:7")


def test_cmux_command_timeout_is_reported(monkeypatch) -> None:
    def raise_timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args[0], timeout=kwargs["timeout"])

    monkeypatch.setattr(subprocess, "run", raise_timeout)

    with pytest.raises(CmuxCommandError, match="timed out"):
        CmuxClient("/fake/cmux").ping()
