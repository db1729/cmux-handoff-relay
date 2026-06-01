import io
import json

from cmux_handoff_relay.cli import run
from cmux_handoff_relay.errors import CmuxCommandError


def handoff_contract(
    *,
    source: str,
    target: str,
    roles: str = "main, review, qa",
    nonce: str | None = None,
) -> str:
    nonce_line = (
        f"- Future handoff headers from this worker must include `nonce={nonce}`.\n"
        if nonce
        else ""
    )
    return (
        "CHR handoff contract:\n"
        f"- Current role: {target}; source role: {source}; "
        f"available target roles: {roles}.\n"
        f"{nonce_line}"
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


class SequencedCmuxClient:
    def __init__(self, screens: dict[str, list[str]]) -> None:
        self.screens = screens
        self.read_counts: dict[str, int] = {}
        self.reads: list[tuple[str, int]] = []
        self.sent: list[tuple[str, str]] = []
        self.entered: list[str] = []

    def read_screen(self, surface: str, lines: int) -> str:
        self.reads.append((surface, lines))
        count = self.read_counts.get(surface, 0)
        self.read_counts[surface] = count + 1
        sequence = self.screens.get(surface, [""])
        if count < len(sequence):
            return sequence[count]
        return sequence[-1]

    def send_text(self, surface: str, text: str) -> None:
        self.sent.append((surface, text))

    def send_enter(self, surface: str) -> None:
        self.entered.append(surface)


class FailingReadCmuxClient(SequencedCmuxClient):
    def __init__(self, screens: dict[str, list[str]], fail_surfaces: set[str]) -> None:
        super().__init__(screens)
        self.fail_surfaces = fail_surfaces

    def read_screen(self, surface: str, lines: int) -> str:
        if surface in self.fail_surfaces:
            raise CmuxCommandError("temporary read error")
        return super().read_screen(surface, lines)


class FailingSendCmuxClient(SequencedCmuxClient):
    def send_text(self, surface: str, text: str) -> None:
        raise CmuxCommandError("temporary send error")


class FailingEnterCmuxClient(SequencedCmuxClient):
    def send_enter(self, surface: str) -> None:
        raise CmuxCommandError("temporary enter error")


def write_config(tmp_path):
    path = tmp_path / ".cmux-handoff.json"
    path.write_text(
        json.dumps(
            {
                "roles": {
                    "main": "surface:1",
                    "review": "surface:2",
                    "qa": "surface:3",
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
                    "qa": {
                        "surface": "surface:3",
                        "agent": "gemini",
                        "ce_default": "/ce-debug",
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
                    "qa": {
                        "surface": "surface:3",
                        "agent": "gemini",
                        "ce_default": "/ce-debug",
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
                        "allow_targets": ["qa"],
                    },
                    "qa": {"surface": "surface:3", "agent": "gemini"},
                }
            }
        ),
        encoding="utf-8",
    )
    return path


def write_target_hint_config(tmp_path):
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
                    "qa": {"surface": "surface:3"},
                }
            }
        ),
        encoding="utf-8",
    )
    return path


def handoff(
    target: str, body: str, *, submit: bool = False, nonce: str | None = None
) -> str:
    nonce_part = f" nonce={nonce}" if nonce else ""
    return (
        f"<<<HANDOFF target={target} submit={str(submit).lower()}{nonce_part}>>>\n"
        f"{body}\n"
        "<<<END_HANDOFF>>>\n"
    )


def malformed_handoff() -> str:
    return """<<<HANDOFF target=review submit=false>>>
Partial prompt without an end marker.
"""


def test_watch_relays_agent_directed_targets_without_fixed_order(tmp_path) -> None:
    config_path = write_config(tmp_path)
    client = SequencedCmuxClient(
        {
            "surface:1": [handoff("review", "Review this diff.", nonce="n1")],
            "surface:2": [
                handoff("qa", "Run the verification commands.", nonce="n1")
            ],
        }
    )
    stdout = io.StringIO()
    stderr = io.StringIO()

    result = run(
        [
            "watch",
            "--config",
            str(config_path),
            "--roles",
            "main,review",
            "--relay-existing",
            "--yes",
            "--nonce",
            "n1",
            "--interval",
            "0",
            "--no-handoff-contract",
            "--max-turns",
            "2",
        ],
        stdout=stdout,
        stderr=stderr,
        cmux_client=client,
    )

    assert result == 0
    assert stderr.getvalue() == ""
    assert client.sent == [
        ("surface:2", "Review this diff."),
        ("surface:3", "Run the verification commands."),
    ]
    assert client.entered == []
    assert "Watch stopped: max turns reached." in stdout.getvalue()


def test_watch_applies_ce_prefix_to_target_role(tmp_path) -> None:
    config_path = write_ce_config(tmp_path)
    client = SequencedCmuxClient(
        {"surface:1": [handoff("review", "Review this diff.", nonce="n1")]}
    )
    stdout = io.StringIO()
    stderr = io.StringIO()

    result = run(
        [
            "watch",
            "--config",
            str(config_path),
            "--roles",
            "main",
            "--relay-existing",
            "--yes",
            "--nonce",
            "n1",
            "--interval",
            "0",
            "--max-turns",
            "1",
        ],
        stdout=stdout,
        stderr=stderr,
        cmux_client=client,
    )

    assert result == 0
    assert stderr.getvalue() == ""
    assert client.sent == [
        (
            "surface:2",
            "/ce-code-review\n\nReview this diff.\n\n"
            + handoff_contract(source="main", target="review", nonce="n1"),
        )
    ]
    assert "Workflow prefix: /ce-code-review" in stdout.getvalue()
    assert "Handoff contract: enabled" in stdout.getvalue()


def test_watch_no_handoff_contract_disables_contract(tmp_path) -> None:
    config_path = write_ce_config(tmp_path)
    client = SequencedCmuxClient(
        {"surface:1": [handoff("review", "Review this diff.", nonce="n1")]}
    )
    stdout = io.StringIO()
    stderr = io.StringIO()

    result = run(
        [
            "watch",
            "--config",
            str(config_path),
            "--roles",
            "main",
            "--relay-existing",
            "--yes",
            "--nonce",
            "n1",
            "--interval",
            "0",
            "--no-handoff-contract",
            "--max-turns",
            "1",
        ],
        stdout=stdout,
        stderr=stderr,
        cmux_client=client,
    )

    assert result == 0
    assert stderr.getvalue() == ""
    assert client.sent == [("surface:2", "/ce-code-review\n\nReview this diff.")]
    assert "Handoff contract: disabled" in stdout.getvalue()


def test_watch_profile_adds_context_budget_guidance(tmp_path) -> None:
    config_path = write_profile_config(tmp_path)
    client = SequencedCmuxClient(
        {"surface:1": [handoff("review", "Review this diff.", nonce="n1")]}
    )
    stdout = io.StringIO()
    stderr = io.StringIO()

    result = run(
        [
            "watch",
            "--config",
            str(config_path),
            "--roles",
            "main",
            "--relay-existing",
            "--yes",
            "--nonce",
            "n1",
            "--interval",
            "0",
            "--max-turns",
            "1",
        ],
        stdout=stdout,
        stderr=stderr,
        cmux_client=client,
    )

    assert result == 0
    assert stderr.getvalue() == ""
    sent_payload = client.sent[0][1]
    assert "- Workflow profile: light. Keep context lean;" in sent_payload
    assert "directly relevant files" in sent_payload
    assert "Workflow profile: light" in stdout.getvalue()


def test_watch_reasoning_profile_override_adds_advisory_guidance(tmp_path) -> None:
    config_path = write_profile_config(tmp_path)
    client = SequencedCmuxClient(
        {"surface:1": [handoff("review", "Review this diff.", nonce="n1")]}
    )
    stdout = io.StringIO()
    stderr = io.StringIO()

    result = run(
        [
            "watch",
            "--config",
            str(config_path),
            "--roles",
            "main",
            "--relay-existing",
            "--yes",
            "--nonce",
            "n1",
            "--reasoning-profile",
            "minimal",
            "--interval",
            "0",
            "--max-turns",
            "1",
        ],
        stdout=stdout,
        stderr=stderr,
        cmux_client=client,
    )

    assert result == 0
    assert stderr.getvalue() == ""
    sent_payload = client.sent[0][1]
    assert (
        "- Reasoning profile: minimal. Use the smallest useful amount of "
        "internal reasoning"
    ) in sent_payload
    assert 'Agent effort cue: Claude Code "think"' in sent_payload
    assert (
        "plain-text hint; CHR does not change app settings, but the target "
        "agent may interpret it"
    ) in sent_payload
    assert "- Reasoning profile: medium" not in sent_payload
    assert "Reasoning profile: minimal" in stdout.getvalue()
    assert 'Agent effort cue: Claude Code "think"' in stdout.getvalue()


def test_watch_mode_smoke_disables_ce_prefix_and_contract(tmp_path) -> None:
    config_path = write_profile_config(tmp_path)
    client = SequencedCmuxClient(
        {"surface:1": [handoff("review", "Smoke transport only.", nonce="n1")]}
    )
    stdout = io.StringIO()
    stderr = io.StringIO()

    result = run(
        [
            "watch",
            "--config",
            str(config_path),
            "--roles",
            "main",
            "--relay-existing",
            "--yes",
            "--nonce",
            "n1",
            "--interval",
            "0",
            "--mode",
            "smoke",
            "--max-turns",
            "1",
        ],
        stdout=stdout,
        stderr=stderr,
        cmux_client=client,
    )

    assert result == 0
    assert stderr.getvalue() == ""
    assert client.sent == [("surface:2", "Smoke transport only.")]
    assert "Workflow prefix: disabled (configured: /ce-code-review)" in stdout.getvalue()
    assert "Workflow profile: disabled (configured: light)" in stdout.getvalue()
    assert "Reasoning profile: disabled (requested: medium)" in stdout.getvalue()
    assert "Agent effort cue: disabled" in stdout.getvalue()
    assert "Handoff contract: disabled" in stdout.getvalue()


def test_watch_baselines_existing_handoffs_by_default(tmp_path) -> None:
    config_path = write_config(tmp_path)
    client = SequencedCmuxClient({"surface:1": [handoff("review", "Old handoff.")]})
    stdout = io.StringIO()
    stderr = io.StringIO()

    result = run(
        [
            "watch",
            "--config",
            str(config_path),
            "--roles",
            "main",
            "--interval",
            "0",
            "--max-turns",
            "1",
            "--idle-polls",
            "1",
        ],
        stdout=stdout,
        stderr=stderr,
        cmux_client=client,
    )

    assert result == 0
    assert stderr.getvalue() == ""
    assert client.sent == []
    assert "Existing handoffs baselined" in stdout.getvalue()
    assert "Watch stopped: idle poll limit reached." in stdout.getvalue()


def test_watch_submit_flag_is_required_for_enter(tmp_path) -> None:
    config_path = write_config(tmp_path)
    client = SequencedCmuxClient(
        {
            "surface:1": [
                handoff("review", "Review and continue.", submit=True, nonce="n1")
            ]
        }
    )
    stdout = io.StringIO()
    stderr = io.StringIO()

    result = run(
        [
            "watch",
            "--config",
            str(config_path),
            "--roles",
            "main",
            "--relay-existing",
            "--yes",
            "--submit",
            "--nonce",
            "n1",
            "--interval",
            "0",
            "--no-handoff-contract",
            "--max-turns",
            "1",
        ],
        stdout=stdout,
        stderr=stderr,
        cmux_client=client,
    )

    assert result == 0
    assert stderr.getvalue() == ""
    assert client.sent == [("surface:2", "Review and continue.")]
    assert client.entered == ["surface:2"]
    assert "Block submit metadata: true (parsed only)" in stdout.getvalue()


def test_watch_send_enter_error_marks_payload_seen(tmp_path) -> None:
    config_path = write_config(tmp_path)
    repeated_handoff = handoff(
        "review", "Review and continue.", submit=True, nonce="n1"
    )
    client = FailingEnterCmuxClient(
        {"surface:1": [repeated_handoff, repeated_handoff, ""]}
    )
    stdout = io.StringIO()
    stderr = io.StringIO()

    result = run(
        [
            "watch",
            "--config",
            str(config_path),
            "--roles",
            "main",
            "--relay-existing",
            "--yes",
            "--submit",
            "--nonce",
            "n1",
            "--interval",
            "0",
            "--no-handoff-contract",
            "--max-turns",
            "1",
            "--idle-polls",
            "1",
        ],
        stdout=stdout,
        stderr=stderr,
        cmux_client=client,
    )

    assert result == 3
    assert client.sent == [("surface:2", "Review and continue.")]
    assert client.entered == []
    assert "temporary enter error" in stderr.getvalue()
    assert "failed to press Enter" in stderr.getvalue()
    assert "1 payload(s) were sent but Enter failed" in stderr.getvalue()
    assert "payload will not be resent" in stdout.getvalue()
    assert "Watch stopped: max turns reached." in stdout.getvalue()


def test_watch_auto_submit_requires_nonce(tmp_path) -> None:
    config_path = write_config(tmp_path)
    client = SequencedCmuxClient({"surface:1": [handoff("review", "Review.")]})
    stdout = io.StringIO()
    stderr = io.StringIO()

    result = run(
        [
            "watch",
            "--config",
            str(config_path),
            "--roles",
            "main",
            "--relay-existing",
            "--yes",
            "--submit",
            "--interval",
            "0",
            "--max-turns",
            "1",
        ],
        stdout=stdout,
        stderr=stderr,
        cmux_client=client,
    )

    assert result == 1
    assert client.sent == []
    assert "Automatic relay requires --nonce" in stderr.getvalue()


def test_watch_confirm_never_requires_nonce_without_yes(tmp_path) -> None:
    config_path = write_config(tmp_path)
    client = SequencedCmuxClient({"surface:1": [handoff("review", "Review.")]})
    stdout = io.StringIO()
    stderr = io.StringIO()

    result = run(
        [
            "watch",
            "--config",
            str(config_path),
            "--roles",
            "main",
            "--relay-existing",
            "--confirm",
            "never",
            "--interval",
            "0",
            "--max-turns",
            "1",
        ],
        stdout=stdout,
        stderr=stderr,
        cmux_client=client,
    )

    assert result == 1
    assert client.sent == []
    assert "Automatic relay requires --nonce" in stderr.getvalue()


def test_watch_nonce_mismatch_isolated_to_source_role(tmp_path) -> None:
    config_path = write_config(tmp_path)
    client = SequencedCmuxClient(
        {
            "surface:1": [handoff("review", "Wrong nonce.", nonce="wrong")],
            "surface:2": [handoff("qa", "Run QA.", nonce="n1")],
        }
    )
    stdout = io.StringIO()
    stderr = io.StringIO()

    result = run(
        [
            "watch",
            "--config",
            str(config_path),
            "--roles",
            "main,review",
            "--relay-existing",
            "--yes",
            "--interval",
            "0",
            "--nonce",
            "n1",
            "--no-handoff-contract",
            "--max-turns",
            "1",
        ],
        stdout=stdout,
        stderr=stderr,
        cmux_client=client,
    )

    assert result == 0
    assert client.sent == [("surface:3", "Run QA.")]
    assert "skipping role 'main'" in stderr.getvalue()
    assert "nonce missing or mismatched" in stderr.getvalue()


def test_watch_cmux_read_error_isolated_to_source_role(tmp_path) -> None:
    config_path = write_config(tmp_path)
    client = FailingReadCmuxClient(
        {"surface:2": [handoff("qa", "Run QA.", nonce="n1")]},
        fail_surfaces={"surface:1"},
    )
    stdout = io.StringIO()
    stderr = io.StringIO()

    result = run(
        [
            "watch",
            "--config",
            str(config_path),
            "--roles",
            "main,review",
            "--relay-existing",
            "--yes",
            "--nonce",
            "n1",
            "--interval",
            "0",
            "--no-handoff-contract",
            "--max-turns",
            "1",
        ],
        stdout=stdout,
        stderr=stderr,
        cmux_client=client,
    )

    assert result == 0
    assert client.sent == [("surface:3", "Run QA.")]
    assert "temporary read error" in stderr.getvalue()


def test_watch_target_surface_hint_mismatch_isolated(tmp_path) -> None:
    config_path = write_target_hint_config(tmp_path)
    client = SequencedCmuxClient(
        {
            "surface:1": [handoff("review", "Review.", nonce="n1")],
            "surface:2": ["wrong pane"],
        }
    )
    stdout = io.StringIO()
    stderr = io.StringIO()

    result = run(
        [
            "watch",
            "--config",
            str(config_path),
            "--roles",
            "main",
            "--relay-existing",
            "--yes",
            "--nonce",
            "n1",
            "--interval",
            "0",
            "--no-handoff-contract",
            "--max-turns",
            "1",
            "--idle-polls",
            "1",
        ],
        stdout=stdout,
        stderr=stderr,
        cmux_client=client,
    )

    assert result == 0
    assert client.sent == []
    assert "Surface hint mismatch" in stderr.getvalue()


def test_watch_cmux_send_error_does_not_mark_seen(tmp_path) -> None:
    config_path = write_config(tmp_path)
    client = FailingSendCmuxClient(
        {"surface:1": [handoff("review", "Review.", nonce="n1")]}
    )
    stdout = io.StringIO()
    stderr = io.StringIO()

    result = run(
        [
            "watch",
            "--config",
            str(config_path),
            "--roles",
            "main",
            "--relay-existing",
            "--yes",
            "--nonce",
            "n1",
            "--interval",
            "0",
            "--no-handoff-contract",
            "--max-turns",
            "1",
            "--idle-polls",
            "1",
        ],
        stdout=stdout,
        stderr=stderr,
        cmux_client=client,
    )

    assert result == 0
    assert client.sent == []
    assert "temporary send error" in stderr.getvalue()


def test_watch_unknown_target_isolated_to_source_role(tmp_path) -> None:
    config_path = write_config(tmp_path)
    client = SequencedCmuxClient(
        {
            "surface:1": [handoff("security", "Review this.", nonce="n1")],
            "surface:2": [handoff("qa", "Run QA.", nonce="n1")],
        }
    )
    stdout = io.StringIO()
    stderr = io.StringIO()

    result = run(
        [
            "watch",
            "--config",
            str(config_path),
            "--roles",
            "main,review",
            "--relay-existing",
            "--yes",
            "--nonce",
            "n1",
            "--interval",
            "0",
            "--no-handoff-contract",
            "--max-turns",
            "1",
        ],
        stdout=stdout,
        stderr=stderr,
        cmux_client=client,
    )

    assert result == 0
    assert client.sent == [("surface:3", "Run QA.")]
    assert "skipping role 'main'" in stderr.getvalue()
    assert "Unknown role 'security'" in stderr.getvalue()


def test_watch_malformed_source_does_not_stop_other_roles(tmp_path) -> None:
    config_path = write_config(tmp_path)
    client = SequencedCmuxClient(
        {
            "surface:1": [malformed_handoff()],
            "surface:2": [handoff("qa", "Run QA.", nonce="n1")],
        }
    )
    stdout = io.StringIO()
    stderr = io.StringIO()

    result = run(
        [
            "watch",
            "--config",
            str(config_path),
            "--roles",
            "main,review",
            "--relay-existing",
            "--yes",
            "--nonce",
            "n1",
            "--interval",
            "0",
            "--no-handoff-contract",
            "--max-turns",
            "1",
        ],
        stdout=stdout,
        stderr=stderr,
        cmux_client=client,
    )

    assert result == 0
    assert client.sent == [("surface:3", "Run QA.")]
    assert "skipping role 'main'" in stderr.getvalue()
    assert "missing <<<END_HANDOFF>>>" in stderr.getvalue()


def test_watch_disallowed_target_isolated_to_source_role(tmp_path) -> None:
    config_path = write_restricted_config(tmp_path)
    client = SequencedCmuxClient(
        {
            "surface:1": [handoff("qa", "Main may not jump to QA.", nonce="n1")],
            "surface:2": [handoff("qa", "Review may send to QA.", nonce="n1")],
        }
    )
    stdout = io.StringIO()
    stderr = io.StringIO()

    result = run(
        [
            "watch",
            "--config",
            str(config_path),
            "--roles",
            "main,review",
            "--relay-existing",
            "--yes",
            "--nonce",
            "n1",
            "--interval",
            "0",
            "--no-handoff-contract",
            "--max-turns",
            "1",
        ],
        stdout=stdout,
        stderr=stderr,
        cmux_client=client,
    )

    assert result == 0
    assert client.sent == [("surface:3", "Review may send to QA.")]
    assert "skipping role 'main'" in stderr.getvalue()
    assert "may not target 'qa'" in stderr.getvalue()


def test_watch_rejects_unbounded_auto_submit(tmp_path) -> None:
    config_path = write_config(tmp_path)
    client = SequencedCmuxClient({"surface:1": [handoff("review", "Review.")]})
    stdout = io.StringIO()
    stderr = io.StringIO()

    result = run(
        [
            "watch",
            "--config",
            str(config_path),
            "--roles",
            "main",
            "--yes",
            "--submit",
            "--max-turns",
            "0",
        ],
        stdout=stdout,
        stderr=stderr,
        cmux_client=client,
    )

    assert result == 1
    assert client.sent == []
    assert "--max-turns 0 cannot be combined" in stderr.getvalue()


def test_watch_rejects_unbounded_auto_relay_without_submit(tmp_path) -> None:
    config_path = write_config(tmp_path)
    client = SequencedCmuxClient(
        {"surface:1": [handoff("review", "Review.", nonce="n1")]}
    )
    stdout = io.StringIO()
    stderr = io.StringIO()

    result = run(
        [
            "watch",
            "--config",
            str(config_path),
            "--roles",
            "main",
            "--yes",
            "--nonce",
            "n1",
            "--max-turns",
            "0",
        ],
        stdout=stdout,
        stderr=stderr,
        cmux_client=client,
    )

    assert result == 1
    assert client.sent == []
    assert "--max-turns 0 cannot be combined" in stderr.getvalue()


def test_watch_rejects_invalid_workspace_before_polling(tmp_path) -> None:
    config_path = write_config(tmp_path)
    client = SequencedCmuxClient({"surface:1": [handoff("review", "Review.")]})
    stdout = io.StringIO()
    stderr = io.StringIO()

    result = run(
        [
            "watch",
            "--config",
            str(config_path),
            "--workspace",
            "workspace:7 --bad",
            "--roles",
            "main",
            "--idle-polls",
            "1",
        ],
        stdout=stdout,
        stderr=stderr,
        cmux_client=client,
    )

    assert result == 1
    assert client.reads == []
    assert client.sent == []
    assert "cmux workspace" in stderr.getvalue()
