import io
import json

import pytest

import cmux_handoff_relay.cli as cli_module
from cmux_handoff_relay.cli import run


def handoff_contract(
    *, source: str = "main", target: str = "review", roles: str = "main, review"
) -> str:
    return (
        "CHR handoff contract:\n"
        f"- Current role: {target}; source role: {source}; "
        f"available target roles: {roles}.\n"
        "- Default to choosing a safe, reversible option and continue without "
        "asking the user to choose.\n"
        "- Stop for user input only when secrets, external login, payment, DNS, "
        "production config, destructive actions, git stage/commit/push, or an "
        "irreversible product decision is required.\n"
        "- If blocked, do not hand off. End with `NO HANDOFF`, then `BLOCKED:`, "
        "`RECOMMENDED:`, and `WHY:`.\n"
        "- When finished, either hand off by printing one valid CHR handoff "
        "block as the final output, or end with `NO HANDOFF` if no next "
        "worker is needed.\n"
        "- Follow the exact handoff block format from the repo-local agent "
        "rules. Do not print sample handoff blocks."
    )


class RecordingCmuxClient:
    def __init__(self, screen_text: str = "") -> None:
        self.screen_text = screen_text
        self.reads: list[tuple[str, int]] = []
        self.sent: list[tuple[str, str]] = []
        self.entered: list[str] = []

    def read_screen(self, surface: str, lines: int) -> str:
        self.reads.append((surface, lines))
        return self.screen_text

    def send_text(self, surface: str, text: str) -> None:
        self.sent.append((surface, text))

    def send_enter(self, surface: str) -> None:
        self.entered.append(surface)


class OrderedCmuxClient(RecordingCmuxClient):
    def __init__(self, screen_text: str = "") -> None:
        super().__init__(screen_text)
        self.events: list[str] = []

    def send_text(self, surface: str, text: str) -> None:
        self.events.append("send_text")
        super().send_text(surface, text)

    def send_enter(self, surface: str) -> None:
        self.events.append("send_enter")
        super().send_enter(surface)


def write_config(tmp_path):
    path = tmp_path / ".cmux-handoff.json"
    path.write_text(
        json.dumps(
            {
                "roles": {
                    "main": "surface:1",
                    "review": "surface:2",
                }
            }
        ),
        encoding="utf-8",
    )
    return path


def write_ce_config(tmp_path):
    path = tmp_path / ".cmux-handoff.json"
    path.write_text(
        json.dumps(
            {
                "roles": {
                    "main": {"surface": "surface:1", "agent": "codex"},
                    "review": {
                        "surface": "surface:2",
                        "agent": "claude",
                        "ce_default": "/ce-code-review",
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    return path


def write_profile_config(tmp_path):
    path = tmp_path / ".cmux-handoff.json"
    path.write_text(
        json.dumps(
            {
                "roles": {
                    "main": {"surface": "surface:1", "agent": "codex"},
                    "review": {
                        "surface": "surface:2",
                        "agent": "claude",
                        "ce_default": "/ce-code-review",
                        "workflow_profile": "light",
                        "reasoning_profile": "medium",
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    return path


def write_restricted_config(tmp_path):
    path = tmp_path / ".cmux-handoff.json"
    path.write_text(
        json.dumps(
            {
                "roles": {
                    "main": {
                        "surface": "surface:1",
                        "agent": "codex",
                        "allow_targets": ["review"],
                    },
                    "review": {
                        "surface": "surface:2",
                        "agent": "claude",
                    },
                    "qa": {
                        "surface": "surface:3",
                        "agent": "gemini",
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    return path


def write_surface_hint_config(tmp_path):
    path = tmp_path / ".cmux-handoff.json"
    path.write_text(
        json.dumps(
            {
                "roles": {
                    "main": {"surface": "surface:1"},
                    "review": {
                        "surface": "surface:2",
                        "surface_hint": "Claude Code",
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    return path


def write_submit_delay_config(tmp_path):
    path = tmp_path / ".cmux-handoff.json"
    path.write_text(
        json.dumps(
            {
                "roles": {
                    "main": {"surface": "surface:1"},
                    "review": {"surface": "surface:2", "submit_delay": 0.7},
                }
            }
        ),
        encoding="utf-8",
    )
    return path


def write_input(
    tmp_path,
    body: str = "Review this change.",
    target: str = "review",
    nonce: str | None = None,
):
    path = tmp_path / "screen.txt"
    nonce_part = f" nonce={nonce}" if nonce else ""
    path.write_text(
        f"""noise
<<<HANDOFF target={target} submit=true{nonce_part}>>>
{body}
<<<END_HANDOFF>>>
""",
        encoding="utf-8",
    )
    return path


def test_dry_run_preview_works_without_cmux(tmp_path) -> None:
    config_path = write_config(tmp_path)
    input_path = write_input(tmp_path)
    stdout = io.StringIO()
    stderr = io.StringIO()
    client = RecordingCmuxClient()

    result = run(
        [
            "--config",
            str(config_path),
            "--from",
            "main",
            "--dry-run",
            "--input-file",
            str(input_path),
        ],
        stdout=stdout,
        stderr=stderr,
        cmux_client=client,
    )

    assert result == 0
    assert stderr.getvalue() == ""
    output = stdout.getvalue()
    assert "Handoff preview" in output
    assert "Review this change." in output
    assert "Handoff contract: enabled" in output
    assert "CHR handoff contract:" in output
    assert "CLI --submit: false" in output
    assert "Dry run: no cmux send performed." in output
    assert client.sent == []
    assert client.entered == []
    assert client.reads == []


def test_ce_prefix_is_applied_in_manual_dry_run(tmp_path) -> None:
    config_path = write_ce_config(tmp_path)
    input_path = write_input(tmp_path, body="Review this change.")
    stdout = io.StringIO()
    stderr = io.StringIO()

    result = run(
        [
            "--config",
            str(config_path),
            "--from",
            "main",
            "--dry-run",
            "--input-file",
            str(input_path),
        ],
        stdout=stdout,
        stderr=stderr,
    )

    assert result == 0
    assert stderr.getvalue() == ""
    output = stdout.getvalue()
    assert "Workflow prefix: /ce-code-review" in output
    assert (
        "--- BEGIN PAYLOAD ---\n/ce-code-review\n\nReview this change.\n\n"
        "CHR handoff contract:"
    ) in output


def test_workflow_profile_adds_context_budget_guidance(tmp_path) -> None:
    config_path = write_profile_config(tmp_path)
    input_path = write_input(tmp_path, body="Review this change.")
    stdout = io.StringIO()
    stderr = io.StringIO()

    result = run(
        [
            "--config",
            str(config_path),
            "--from",
            "main",
            "--dry-run",
            "--input-file",
            str(input_path),
        ],
        stdout=stdout,
        stderr=stderr,
    )

    output = stdout.getvalue()
    assert result == 0
    assert stderr.getvalue() == ""
    assert "Workflow profile: light" in output
    assert "- Workflow profile: light. Keep context lean;" in output
    assert "directly relevant files" in output


def test_reasoning_profile_adds_advisory_guidance(tmp_path) -> None:
    config_path = write_profile_config(tmp_path)
    input_path = write_input(tmp_path, body="Review this change.")
    stdout = io.StringIO()
    stderr = io.StringIO()

    result = run(
        [
            "--config",
            str(config_path),
            "--from",
            "main",
            "--dry-run",
            "--input-file",
            str(input_path),
        ],
        stdout=stdout,
        stderr=stderr,
    )

    output = stdout.getvalue()
    assert result == 0
    assert stderr.getvalue() == ""
    assert "Reasoning profile: medium" in output
    assert 'Agent effort cue: Claude Code "think harder"' in output
    assert "- Reasoning profile: medium. Use balanced internal reasoning;" in output
    assert "directly relevant evidence" in output
    assert 'Agent effort cue: Claude Code "think harder"' in output
    assert (
        "plain-text hint; CHR does not change app settings, but the target "
        "agent may interpret it"
    ) in output


@pytest.mark.parametrize(
    ("profile", "guidance"),
    [
        ("minimal", "Use the smallest useful amount of internal reasoning"),
        ("low", "Use concise internal reasoning"),
        ("medium", "Use balanced internal reasoning"),
        ("high", "Use deeper internal reasoning"),
    ],
)
def test_cli_reasoning_profile_accepts_all_supported_profiles(
    tmp_path, profile, guidance
) -> None:
    config_path = write_profile_config(tmp_path)
    input_path = write_input(tmp_path, body="Review this change.")
    stdout = io.StringIO()
    stderr = io.StringIO()

    result = run(
        [
            "--config",
            str(config_path),
            "--from",
            "main",
            "--reasoning-profile",
            profile,
            "--dry-run",
            "--input-file",
            str(input_path),
        ],
        stdout=stdout,
        stderr=stderr,
    )

    output = stdout.getvalue()
    assert result == 0
    assert stderr.getvalue() == ""
    assert f"Reasoning profile: {profile}" in output
    assert f"- Reasoning profile: {profile}. {guidance}" in output
    if profile != "medium":
        assert "- Reasoning profile: medium" not in output


def test_no_handoff_contract_disables_workflow_profile_hint(tmp_path) -> None:
    config_path = write_profile_config(tmp_path)
    input_path = write_input(tmp_path, body="Review this change.")
    stdout = io.StringIO()
    stderr = io.StringIO()

    result = run(
        [
            "--config",
            str(config_path),
            "--from",
            "main",
            "--no-handoff-contract",
            "--dry-run",
            "--input-file",
            str(input_path),
        ],
        stdout=stdout,
        stderr=stderr,
    )

    output = stdout.getvalue()
    assert result == 0
    assert stderr.getvalue() == ""
    assert "Workflow profile: disabled (configured: light)" in output
    assert "Keep context lean" not in output


def test_no_handoff_contract_disables_reasoning_profile_hint(tmp_path) -> None:
    config_path = write_profile_config(tmp_path)
    input_path = write_input(tmp_path, body="Review this change.")
    stdout = io.StringIO()
    stderr = io.StringIO()

    result = run(
        [
            "--config",
            str(config_path),
            "--from",
            "main",
            "--no-handoff-contract",
            "--dry-run",
            "--input-file",
            str(input_path),
        ],
        stdout=stdout,
        stderr=stderr,
    )

    output = stdout.getvalue()
    assert result == 0
    assert stderr.getvalue() == ""
    assert "Reasoning profile: disabled (requested: medium)" in output
    assert "Agent effort cue: disabled" in output
    assert "balanced internal reasoning" not in output


def test_agent_effort_cue_supports_agy_alias(tmp_path) -> None:
    config_path = tmp_path / ".cmux-handoff.json"
    config_path.write_text(
        json.dumps(
            {
                "roles": {
                    "main": {"surface": "surface:1", "agent": "codex"},
                    "qa": {
                        "surface": "surface:3",
                        "agent": "agy",
                        "ce_default": "/ce-debug",
                        "reasoning_profile": "high",
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    input_path = write_input(tmp_path, target="qa", body="Debug this failure.")
    stdout = io.StringIO()
    stderr = io.StringIO()

    result = run(
        [
            "--config",
            str(config_path),
            "--from",
            "main",
            "--dry-run",
            "--input-file",
            str(input_path),
        ],
        stdout=stdout,
        stderr=stderr,
    )

    output = stdout.getvalue()
    assert result == 0
    assert stderr.getvalue() == ""
    assert "Agent effort cue: Gemini/Antigravity thinking_level=HIGH" in output
    assert "Agent effort cue: Gemini/Antigravity thinking_level=HIGH" in output


def test_ce_prefix_is_applied_in_manual_send_without_auto_submit(tmp_path) -> None:
    config_path = write_ce_config(tmp_path)
    input_path = write_input(tmp_path, body="Review this change.")
    stdout = io.StringIO()
    stderr = io.StringIO()
    stdin = io.StringIO("yes\n")
    client = RecordingCmuxClient()

    result = run(
        [
            "--config",
            str(config_path),
            "--from",
            "main",
            "--input-file",
            str(input_path),
        ],
        stdout=stdout,
        stderr=stderr,
        stdin=stdin,
        cmux_client=client,
    )

    assert result == 0
    assert stderr.getvalue() == ""
    assert client.sent == [
        (
            "surface:2",
            "/ce-code-review\n\nReview this change.\n\n" + handoff_contract(),
        )
    ]
    assert client.entered == []
    assert "Block submit metadata: true (parsed only)" in stdout.getvalue()


def test_no_ce_disables_manual_prefix(tmp_path) -> None:
    config_path = write_ce_config(tmp_path)
    input_path = write_input(tmp_path, body="Review this change.")
    stdout = io.StringIO()
    stderr = io.StringIO()
    stdin = io.StringIO("yes\n")
    client = RecordingCmuxClient()

    result = run(
        [
            "--config",
            str(config_path),
            "--from",
            "main",
            "--no-ce",
            "--input-file",
            str(input_path),
        ],
        stdout=stdout,
        stderr=stderr,
        stdin=stdin,
        cmux_client=client,
    )

    assert result == 0
    assert stderr.getvalue() == ""
    assert client.sent == [
        ("surface:2", "Review this change.\n\n" + handoff_contract())
    ]
    assert "Workflow prefix: disabled (configured: /ce-code-review)" in stdout.getvalue()
    assert "Handoff contract: enabled" in stdout.getvalue()


def test_no_handoff_contract_disables_manual_contract(tmp_path) -> None:
    config_path = write_ce_config(tmp_path)
    input_path = write_input(tmp_path, body="Review this change.")
    stdout = io.StringIO()
    stderr = io.StringIO()
    stdin = io.StringIO("yes\n")
    client = RecordingCmuxClient()

    result = run(
        [
            "--config",
            str(config_path),
            "--from",
            "main",
            "--no-handoff-contract",
            "--input-file",
            str(input_path),
        ],
        stdout=stdout,
        stderr=stderr,
        stdin=stdin,
        cmux_client=client,
    )

    assert result == 0
    assert stderr.getvalue() == ""
    assert client.sent == [("surface:2", "/ce-code-review\n\nReview this change.")]
    assert "Handoff contract: disabled" in stdout.getvalue()


def test_manual_nonce_requires_matching_block_and_propagates_contract(tmp_path) -> None:
    config_path = write_ce_config(tmp_path)
    input_path = write_input(tmp_path, body="Review this change.", nonce="n1")
    stdout = io.StringIO()
    stderr = io.StringIO()

    result = run(
        [
            "--config",
            str(config_path),
            "--from",
            "main",
            "--nonce",
            "n1",
            "--dry-run",
            "--input-file",
            str(input_path),
        ],
        stdout=stdout,
        stderr=stderr,
    )

    assert result == 0
    assert stderr.getvalue() == ""
    assert "nonce=n1" in stdout.getvalue()


def test_manual_nonce_mismatch_is_rejected(tmp_path) -> None:
    config_path = write_ce_config(tmp_path)
    input_path = write_input(tmp_path, body="Review this change.", nonce="wrong")
    stdout = io.StringIO()
    stderr = io.StringIO()

    result = run(
        [
            "--config",
            str(config_path),
            "--from",
            "main",
            "--nonce",
            "n1",
            "--dry-run",
            "--input-file",
            str(input_path),
        ],
        stdout=stdout,
        stderr=stderr,
    )

    assert result == 1
    assert "nonce missing or mismatched" in stderr.getvalue()


def test_manual_send_rejects_target_surface_hint_mismatch(tmp_path) -> None:
    config_path = write_surface_hint_config(tmp_path)
    input_path = write_input(tmp_path, body="Review this change.")
    stdout = io.StringIO()
    stderr = io.StringIO()
    stdin = io.StringIO("yes\n")
    client = RecordingCmuxClient(screen_text="wrong pane")

    result = run(
        [
            "--config",
            str(config_path),
            "--from",
            "main",
            "--no-handoff-contract",
            "--input-file",
            str(input_path),
        ],
        stdout=stdout,
        stderr=stderr,
        stdin=stdin,
        cmux_client=client,
    )

    assert result == 1
    assert "Surface hint mismatch" in stderr.getvalue()
    assert client.sent == []


def test_manual_rejects_disallowed_target(tmp_path) -> None:
    config_path = write_restricted_config(tmp_path)
    input_path = write_input(tmp_path, body="Run QA.", target="qa")
    stdout = io.StringIO()
    stderr = io.StringIO()
    client = RecordingCmuxClient()

    result = run(
        [
            "--config",
            str(config_path),
            "--from",
            "main",
            "--input-file",
            str(input_path),
        ],
        stdout=stdout,
        stderr=stderr,
        cmux_client=client,
    )

    assert result == 1
    assert "may not target 'qa'" in stderr.getvalue()
    assert client.sent == []


def test_dry_run_single_line_preview(tmp_path) -> None:
    config_path = write_config(tmp_path)
    input_path = write_input(tmp_path, body="Line one\nLine two")
    stdout = io.StringIO()
    stderr = io.StringIO()

    result = run(
        [
            "--config",
            str(config_path),
            "--from",
            "main",
            "--dry-run",
            "--single-line",
            "--no-handoff-contract",
            "--input-file",
            str(input_path),
        ],
        stdout=stdout,
        stderr=stderr,
    )

    assert result == 0
    assert stderr.getvalue() == ""
    output = stdout.getvalue()
    assert "Payload transform" in output
    assert "Line one Line two" in output


def test_send_requires_confirmation_and_does_not_submit_from_metadata(tmp_path) -> None:
    config_path = write_config(tmp_path)
    input_path = write_input(tmp_path, body="Review this change.")
    stdout = io.StringIO()
    stderr = io.StringIO()
    stdin = io.StringIO("yes\n")
    client = RecordingCmuxClient()

    result = run(
        [
            "--config",
            str(config_path),
            "--from",
            "main",
            "--no-handoff-contract",
            "--input-file",
            str(input_path),
        ],
        stdout=stdout,
        stderr=stderr,
        stdin=stdin,
        cmux_client=client,
    )

    assert result == 0
    assert stderr.getvalue() == ""
    assert client.sent == [("surface:2", "Review this change.")]
    assert client.entered == []
    assert "Block submit metadata: true (parsed only)" in stdout.getvalue()
    assert "Sent payload. Enter was not pressed." in stdout.getvalue()


def test_submit_flag_sends_enter_after_payload(tmp_path) -> None:
    config_path = write_config(tmp_path)
    input_path = write_input(tmp_path, body="Run QA checks.")
    stdout = io.StringIO()
    stderr = io.StringIO()
    stdin = io.StringIO("yes\n")
    client = RecordingCmuxClient()

    result = run(
        [
            "--config",
            str(config_path),
            "--from",
            "main",
            "--submit",
            "--no-handoff-contract",
            "--input-file",
            str(input_path),
        ],
        stdout=stdout,
        stderr=stderr,
        stdin=stdin,
        cmux_client=client,
    )

    assert result == 0
    assert stderr.getvalue() == ""
    assert client.sent == [("surface:2", "Run QA checks.")]
    assert client.entered == ["surface:2"]
    assert "pressed Enter because --submit was passed" in stdout.getvalue()


def test_role_submit_delay_is_used_when_cli_delay_missing(
    tmp_path, monkeypatch
) -> None:
    config_path = write_submit_delay_config(tmp_path)
    input_path = write_input(tmp_path, body="Run QA checks.")
    stdout = io.StringIO()
    stderr = io.StringIO()
    stdin = io.StringIO("yes\n")
    client = RecordingCmuxClient()
    sleeps: list[float] = []
    monkeypatch.setattr(cli_module.time, "sleep", lambda seconds: sleeps.append(seconds))

    result = run(
        [
            "--config",
            str(config_path),
            "--from",
            "main",
            "--submit",
            "--no-handoff-contract",
            "--input-file",
            str(input_path),
        ],
        stdout=stdout,
        stderr=stderr,
        stdin=stdin,
        cmux_client=client,
    )

    assert result == 0
    assert sleeps == [0.7]
    assert client.entered == ["surface:2"]


def test_submit_delay_occurs_between_send_text_and_enter(tmp_path, monkeypatch) -> None:
    config_path = write_submit_delay_config(tmp_path)
    input_path = write_input(tmp_path, body="Run QA checks.")
    stdout = io.StringIO()
    stderr = io.StringIO()
    stdin = io.StringIO("yes\n")
    client = OrderedCmuxClient()

    def record_sleep(seconds: float) -> None:
        client.events.append(f"sleep:{seconds}")

    monkeypatch.setattr(cli_module.time, "sleep", record_sleep)

    result = run(
        [
            "--config",
            str(config_path),
            "--from",
            "main",
            "--submit",
            "--no-handoff-contract",
            "--input-file",
            str(input_path),
        ],
        stdout=stdout,
        stderr=stderr,
        stdin=stdin,
        cmux_client=client,
    )

    assert result == 0
    assert client.events == ["send_text", "sleep:0.7", "send_enter"]


def test_cli_submit_delay_overrides_role_submit_delay(tmp_path, monkeypatch) -> None:
    config_path = write_submit_delay_config(tmp_path)
    input_path = write_input(tmp_path, body="Run QA checks.")
    stdout = io.StringIO()
    stderr = io.StringIO()
    stdin = io.StringIO("yes\n")
    client = RecordingCmuxClient()
    sleeps: list[float] = []
    monkeypatch.setattr(cli_module.time, "sleep", lambda seconds: sleeps.append(seconds))

    result = run(
        [
            "--config",
            str(config_path),
            "--from",
            "main",
            "--submit",
            "--submit-delay",
            "0.1",
            "--no-handoff-contract",
            "--input-file",
            str(input_path),
        ],
        stdout=stdout,
        stderr=stderr,
        stdin=stdin,
        cmux_client=client,
    )

    assert result == 0
    assert sleeps == [0.1]
    assert client.entered == ["surface:2"]


def test_mode_smoke_disables_ce_prefix_and_contract(tmp_path) -> None:
    config_path = write_profile_config(tmp_path)
    input_path = write_input(tmp_path, body="Smoke transport only.")
    stdout = io.StringIO()
    stderr = io.StringIO()

    result = run(
        [
            "--config",
            str(config_path),
            "--from",
            "main",
            "--mode",
            "smoke",
            "--dry-run",
            "--input-file",
            str(input_path),
        ],
        stdout=stdout,
        stderr=stderr,
    )

    output = stdout.getvalue()
    assert result == 0
    assert stderr.getvalue() == ""
    assert "Workflow prefix: disabled (configured: /ce-code-review)" in output
    assert "Workflow profile: disabled (configured: light)" in output
    assert "Reasoning profile: disabled (requested: medium)" in output
    assert "Handoff contract: disabled" in output
    assert "--- BEGIN PAYLOAD ---\nSmoke transport only.\n--- END PAYLOAD ---" in output


def test_declined_confirmation_does_not_send(tmp_path) -> None:
    config_path = write_config(tmp_path)
    input_path = write_input(tmp_path)
    stdout = io.StringIO()
    stderr = io.StringIO()
    stdin = io.StringIO("no\n")
    client = RecordingCmuxClient()

    result = run(
        [
            "--config",
            str(config_path),
            "--from",
            "main",
            "--input-file",
            str(input_path),
        ],
        stdout=stdout,
        stderr=stderr,
        stdin=stdin,
        cmux_client=client,
    )

    assert result == 1
    assert "Aborted by user" in stderr.getvalue()
    assert client.sent == []
    assert client.entered == []


def test_missing_confirmation_input_reports_tty_hint(tmp_path) -> None:
    config_path = write_config(tmp_path)
    input_path = write_input(tmp_path)
    stdout = io.StringIO()
    stderr = io.StringIO()
    stdin = io.StringIO("")
    client = RecordingCmuxClient()

    result = run(
        [
            "--config",
            str(config_path),
            "--from",
            "main",
            "--input-file",
            str(input_path),
        ],
        stdout=stdout,
        stderr=stderr,
        stdin=stdin,
        cmux_client=client,
    )

    assert result == 1
    assert "No confirmation input available" in stderr.getvalue()
    assert client.sent == []
    assert client.entered == []


def test_single_line_transform_is_used_for_send(tmp_path) -> None:
    config_path = write_config(tmp_path)
    input_path = write_input(tmp_path, body="Line one\nLine two")
    stdout = io.StringIO()
    stderr = io.StringIO()
    stdin = io.StringIO("yes\n")
    client = RecordingCmuxClient()

    result = run(
        [
            "--config",
            str(config_path),
            "--from",
            "main",
            "--single-line",
            "--no-handoff-contract",
            "--input-file",
            str(input_path),
        ],
        stdout=stdout,
        stderr=stderr,
        stdin=stdin,
        cmux_client=client,
    )

    assert result == 0
    assert stderr.getvalue() == ""
    assert client.sent == [("surface:2", "Line one Line two")]
    assert client.entered == []


def test_manual_relay_rejects_invalid_workspace_before_input_file(tmp_path) -> None:
    config_path = write_config(tmp_path)
    input_path = write_input(tmp_path)
    stdout = io.StringIO()
    stderr = io.StringIO()
    client = RecordingCmuxClient()

    result = run(
        [
            "--config",
            str(config_path),
            "--from",
            "main",
            "--workspace",
            "workspace:7 --bad",
            "--dry-run",
            "--input-file",
            str(input_path),
        ],
        stdout=stdout,
        stderr=stderr,
        cmux_client=client,
    )

    assert result == 1
    assert client.reads == []
    assert client.sent == []
    assert "cmux workspace" in stderr.getvalue()
