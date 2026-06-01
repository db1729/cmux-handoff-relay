"""Config loading for role-to-surface and workflow-prefix mappings."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Mapping

from .errors import HandoffConfigError

DEFAULT_CONFIG_PATH = ".cmux-handoff.json"
SURFACE_RE = re.compile(r"^surface:[A-Za-z0-9_.:-]+$")
WORKFLOW_PROFILES = ("light", "standard", "deep")
REASONING_PROFILES = ("minimal", "low", "medium", "high")


@dataclass(frozen=True)
class RoleConfig:
    surface: str
    agent: str | None = None
    ce_default: str | None = None
    workflow_profile: str | None = None
    reasoning_profile: str | None = None
    submit_delay: float | None = None
    allow_targets: tuple[str, ...] | None = None
    surface_hint: str | None = None


@dataclass(frozen=True)
class RelayConfig:
    roles: Mapping[str, str]
    role_configs: Mapping[str, RoleConfig]

    def role_for(self, role: str) -> RoleConfig:
        try:
            return self.role_configs[role]
        except KeyError as exc:
            raise HandoffConfigError(
                f"Unknown role '{role}'. Known roles: {format_roles(self.roles)}"
            ) from exc

    def surface_for(self, role: str) -> str:
        return self.role_for(role).surface

    def allowed_targets_for(self, role: str) -> tuple[str, ...]:
        role_config = self.role_for(role)
        if role_config.allow_targets is None:
            return tuple(self.roles)
        return role_config.allow_targets

    def ensure_target_allowed(self, source_role: str, target_role: str) -> None:
        self.role_for(target_role)
        allowed_targets = self.allowed_targets_for(source_role)
        if target_role not in allowed_targets:
            allowed = format_roles({role: None for role in allowed_targets})
            raise HandoffConfigError(
                f"Role '{source_role}' may not target '{target_role}'. "
                f"Allowed targets: {allowed}."
            )


def load_config(path: str | Path = DEFAULT_CONFIG_PATH) -> RelayConfig:
    config_path = Path(path)
    try:
        raw = config_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise HandoffConfigError(f"Config file not found: {config_path}") from exc

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HandoffConfigError(
            f"Config file is not valid JSON: {config_path}: {exc.msg}"
        ) from exc

    if not isinstance(data, dict):
        raise HandoffConfigError("Config root must be a JSON object.")

    roles = data.get("roles")
    if not isinstance(roles, dict) or not roles:
        raise HandoffConfigError("Config must contain a non-empty 'roles' object.")

    role_configs: dict[str, RoleConfig] = {}
    surfaces: dict[str, str] = {}
    for role, role_value in roles.items():
        if not isinstance(role, str) or not role.strip():
            raise HandoffConfigError("Config role names must be non-empty strings.")
        role_config = parse_role_config(role, role_value)
        role_configs[role] = role_config
        surfaces[role] = role_config.surface

    known_roles = set(role_configs)
    for role, role_config in role_configs.items():
        if role_config.allow_targets is None:
            continue
        if not role_config.allow_targets:
            raise HandoffConfigError(
                f"Config allow_targets for role '{role}' must not be empty."
            )
        if role in role_config.allow_targets:
            raise HandoffConfigError(
                f"Config allow_targets for role '{role}' must not include itself."
            )
        unknown_targets = sorted(set(role_config.allow_targets) - known_roles)
        if unknown_targets:
            raise HandoffConfigError(
                f"Config allow_targets for role '{role}' contains unknown roles: "
                f"{', '.join(unknown_targets)}."
            )

    return RelayConfig(roles=surfaces, role_configs=role_configs)


def parse_role_config(role: str, value: object) -> RoleConfig:
    if isinstance(value, str):
        surface = parse_surface(role, value)
        return RoleConfig(surface=surface)

    if not isinstance(value, dict):
        raise HandoffConfigError(
            f"Config role '{role}' must be a surface string or role object."
        )

    allowed_keys = {
        "surface",
        "agent",
        "ce_default",
        "workflow_profile",
        "reasoning_profile",
        "submit_delay",
        "allow_targets",
        "surface_hint",
    }
    unknown_keys = sorted(set(value) - allowed_keys)
    if unknown_keys:
        joined = ", ".join(unknown_keys)
        raise HandoffConfigError(f"Config role '{role}' has unknown keys: {joined}.")

    surface = parse_surface(role, value.get("surface"))

    agent = parse_optional_string(role, value.get("agent"), "agent")
    ce_default = parse_optional_string(role, value.get("ce_default"), "ce_default")
    workflow_profile = parse_optional_choice(
        role, value.get("workflow_profile"), "workflow_profile", WORKFLOW_PROFILES
    )
    reasoning_profile = parse_optional_choice(
        role, value.get("reasoning_profile"), "reasoning_profile", REASONING_PROFILES
    )
    submit_delay = parse_optional_nonnegative_number(
        role, value.get("submit_delay"), "submit_delay"
    )
    surface_hint = parse_optional_string(
        role, value.get("surface_hint"), "surface_hint"
    )
    allow_targets = parse_optional_string_list(
        role, value.get("allow_targets"), "allow_targets"
    )
    return RoleConfig(
        surface=surface,
        agent=agent,
        ce_default=ce_default,
        workflow_profile=workflow_profile,
        reasoning_profile=reasoning_profile,
        submit_delay=submit_delay,
        allow_targets=allow_targets,
        surface_hint=surface_hint,
    )


def parse_surface(role: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise HandoffConfigError(
            f"Config surface for role '{role}' must be a non-empty string."
        )

    surface = value.strip()
    if not SURFACE_RE.fullmatch(surface):
        raise HandoffConfigError(
            f"Config surface for role '{role}' must match surface:<id>."
        )
    return surface


def parse_optional_string(role: str, value: object, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise HandoffConfigError(
            f"Config {field} for role '{role}' must be a non-empty string when set."
        )
    return value.strip()


def parse_optional_choice(
    role: str, value: object, field: str, choices: tuple[str, ...]
) -> str | None:
    parsed = parse_optional_string(role, value, field)
    if parsed is None:
        return None
    if parsed not in choices:
        allowed = ", ".join(choices)
        raise HandoffConfigError(
            f"Config {field} for role '{role}' must be one of: {allowed}."
        )
    return parsed


def parse_optional_nonnegative_number(
    role: str, value: object, field: str
) -> float | None:
    if value is None:
        return None
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
        raise HandoffConfigError(
            f"Config {field} for role '{role}' must be a non-negative number when set."
        )
    return float(value)


def parse_optional_string_list(
    role: str, value: object, field: str
) -> tuple[str, ...] | None:
    if value is None:
        return None
    if not isinstance(value, list):
        raise HandoffConfigError(
            f"Config {field} for role '{role}' must be a list of role names when set."
        )

    parsed: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise HandoffConfigError(
                f"Config {field} for role '{role}' must contain non-empty strings."
            )
        normalized = item.strip()
        if normalized not in seen:
            parsed.append(normalized)
            seen.add(normalized)
    return tuple(parsed)


def format_roles(roles: Mapping[str, object]) -> str:
    return ", ".join(sorted(roles)) if roles else "<none>"
