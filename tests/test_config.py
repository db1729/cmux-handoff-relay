import json

import pytest

from cmux_handoff_relay.config import load_config
from cmux_handoff_relay.errors import HandoffConfigError


def test_string_role_config_remains_backward_compatible(tmp_path) -> None:
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

    config = load_config(path)

    assert config.roles == {"main": "surface:1", "review": "surface:2"}
    assert config.surface_for("main") == "surface:1"
    assert config.surface_for("review") == "surface:2"
    assert config.role_for("main").ce_default is None


def test_object_role_config_parses_agent_and_ce_default(tmp_path) -> None:
    path = tmp_path / ".cmux-handoff.json"
    path.write_text(
        json.dumps(
            {
                "roles": {
                    "main": {
                        "surface": "surface:1",
                        "agent": "codex",
                        "ce_default": "/ce-work",
                        "workflow_profile": "standard",
                        "reasoning_profile": "high",
                        "submit_delay": 0.5,
                        "allow_targets": ["review"],
                        "surface_hint": "OpenAI Codex",
                    },
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

    config = load_config(path)

    assert config.surface_for("main") == "surface:1"
    assert config.role_for("main").agent == "codex"
    assert config.role_for("main").ce_default == "/ce-work"
    assert config.role_for("main").workflow_profile == "standard"
    assert config.role_for("main").reasoning_profile == "high"
    assert config.role_for("main").submit_delay == 0.5
    assert config.role_for("main").allow_targets == ("review",)
    assert config.role_for("main").surface_hint == "OpenAI Codex"
    assert config.allowed_targets_for("main") == ("review",)
    assert config.surface_for("review") == "surface:2"
    assert config.role_for("review").agent == "claude"
    assert config.role_for("review").ce_default == "/ce-code-review"
    assert config.allowed_targets_for("review") == ("main", "review")


def test_allow_targets_reject_unknown_roles(tmp_path) -> None:
    path = tmp_path / ".cmux-handoff.json"
    path.write_text(
        json.dumps(
            {
                "roles": {
                    "main": {
                        "surface": "surface:1",
                        "allow_targets": ["review", "missing"],
                    },
                    "review": "surface:2",
                }
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(HandoffConfigError, match="unknown roles: missing"):
        load_config(path)


def test_submit_delay_rejects_negative_values(tmp_path) -> None:
    path = tmp_path / ".cmux-handoff.json"
    path.write_text(
        json.dumps(
            {
                "roles": {
                    "main": {"surface": "surface:1", "submit_delay": -0.1},
                    "review": "surface:2",
                }
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(HandoffConfigError, match="submit_delay"):
        load_config(path)


def test_workflow_profile_rejects_unknown_values(tmp_path) -> None:
    path = tmp_path / ".cmux-handoff.json"
    path.write_text(
        json.dumps(
            {
                "roles": {
                    "main": {
                        "surface": "surface:1",
                        "workflow_profile": "everything",
                    },
                    "review": "surface:2",
                }
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(HandoffConfigError, match="workflow_profile"):
        load_config(path)


def test_reasoning_profile_rejects_unknown_values(tmp_path) -> None:
    path = tmp_path / ".cmux-handoff.json"
    path.write_text(
        json.dumps(
            {
                "roles": {
                    "main": {
                        "surface": "surface:1",
                        "reasoning_profile": "max",
                    },
                    "review": "surface:2",
                }
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(HandoffConfigError, match="reasoning_profile"):
        load_config(path)


@pytest.mark.parametrize("profile", ["minimal", "low", "medium", "high"])
def test_reasoning_profile_accepts_all_supported_values(tmp_path, profile) -> None:
    path = tmp_path / ".cmux-handoff.json"
    path.write_text(
        json.dumps(
            {
                "roles": {
                    "main": {
                        "surface": "surface:1",
                        "reasoning_profile": profile,
                    },
                    "review": "surface:2",
                }
            }
        ),
        encoding="utf-8",
    )

    config = load_config(path)

    assert config.role_for("main").reasoning_profile == profile


def test_allow_targets_reject_empty_list(tmp_path) -> None:
    path = tmp_path / ".cmux-handoff.json"
    path.write_text(
        json.dumps(
            {
                "roles": {
                    "main": {"surface": "surface:1", "allow_targets": []},
                    "review": "surface:2",
                }
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(HandoffConfigError, match="must not be empty"):
        load_config(path)


def test_allow_targets_reject_self_target(tmp_path) -> None:
    path = tmp_path / ".cmux-handoff.json"
    path.write_text(
        json.dumps(
            {
                "roles": {
                    "main": {
                        "surface": "surface:1",
                        "allow_targets": ["main", "review"],
                    },
                    "review": "surface:2",
                }
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(HandoffConfigError, match="must not include itself"):
        load_config(path)


def test_disallowed_target_rejected(tmp_path) -> None:
    path = tmp_path / ".cmux-handoff.json"
    path.write_text(
        json.dumps(
            {
                "roles": {
                    "main": {"surface": "surface:1", "allow_targets": ["review"]},
                    "review": "surface:2",
                    "qa": "surface:3",
                }
            }
        ),
        encoding="utf-8",
    )

    config = load_config(path)

    with pytest.raises(HandoffConfigError, match="may not target 'qa'"):
        config.ensure_target_allowed("main", "qa")


def test_missing_roles_rejected(tmp_path) -> None:
    path = tmp_path / ".cmux-handoff.json"
    path.write_text("{}", encoding="utf-8")

    with pytest.raises(HandoffConfigError, match="roles"):
        load_config(path)


def test_unknown_role_rejected(tmp_path) -> None:
    path = tmp_path / ".cmux-handoff.json"
    path.write_text(
        json.dumps({"roles": {"main": "surface:1"}}),
        encoding="utf-8",
    )

    config = load_config(path)

    with pytest.raises(HandoffConfigError, match="Unknown role 'review'"):
        config.surface_for("review")


def test_surface_must_match_cmux_surface_id_shape(tmp_path) -> None:
    path = tmp_path / ".cmux-handoff.json"
    path.write_text(
        json.dumps({"roles": {"main": "--bad-surface"}}),
        encoding="utf-8",
    )

    with pytest.raises(HandoffConfigError, match="surface:<id>"):
        load_config(path)


def test_surface_allows_non_numeric_cmux_id_suffix(tmp_path) -> None:
    path = tmp_path / ".cmux-handoff.json"
    path.write_text(
        json.dumps({"roles": {"main": "surface:workspace-1.2"}}),
        encoding="utf-8",
    )

    config = load_config(path)

    assert config.surface_for("main") == "surface:workspace-1.2"
