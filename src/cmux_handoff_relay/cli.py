"""Command line interface for cmux-handoff-relay."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import os
from pathlib import Path
import secrets
import sys
import time
from typing import Iterable, Mapping, Sequence, TextIO

from .cmux import (
    APP_BUNDLE_CMUX_BIN,
    CmuxClient,
    detect_cmux_executable,
    validate_workspace_ref,
)
from .config import (
    DEFAULT_CONFIG_PATH,
    REASONING_PROFILES,
    RelayConfig,
    RoleConfig,
    load_config,
)
from .errors import (
    CmuxCommandError,
    HandoffAuthError,
    HandoffAbort,
    HandoffConfigError,
    HandoffParseError,
    HandoffRelayError,
)
from .parser import HandoffBlock, parse_latest_handoff

SUBCOMMANDS = {"doctor", "discover", "init", "watch"}
WATCH_ENTER_FAILURE_EXIT_CODE = 3
DEFAULT_SUBMIT_DELAY = 0.2
WORKFLOW_MODES = ("ce", "smoke")
CLASSIC_CONFIG = """{
  "roles": {
    "main": "surface:1",
    "review": "surface:2",
    "qa": "surface:3",
    "docs": "surface:4"
  }
}
"""
CE_FIRST_CONFIG = """{
  "roles": {
    "main": {
      "surface": "surface:1",
      "agent": "codex",
      "ce_default": "/ce-work",
      "workflow_profile": "standard",
      "reasoning_profile": "high",
      "allow_targets": ["review", "qa", "docs"]
    },
    "review": {
      "surface": "surface:2",
      "agent": "claude",
      "ce_default": "/ce-code-review",
      "workflow_profile": "light",
      "reasoning_profile": "medium",
      "allow_targets": ["main", "qa", "docs"]
    },
    "qa": {
      "surface": "surface:3",
      "agent": "gemini",
      "ce_default": "/ce-debug",
      "workflow_profile": "light",
      "reasoning_profile": "low",
      "allow_targets": ["main", "review", "docs"]
    },
    "docs": {
      "surface": "surface:4",
      "agent": "cursor",
      "ce_default": "/ce-compound",
      "workflow_profile": "light",
      "reasoning_profile": "minimal",
      "allow_targets": ["review"]
    }
  }
}
"""
NO_HANDOFF_MESSAGE = "No HANDOFF block found."


@dataclass(frozen=True)
class WatchEvent:
    source_role: str
    source_surface: str
    block: HandoffBlock
    target_surface: str
    payload: "BuiltPayload"
    fingerprint: str


@dataclass(frozen=True)
class BuiltPayload:
    text: str
    workflow_prefix: str | None
    configured_workflow_prefix: str | None
    workflow_prefix_enabled: bool
    workflow_profile: str | None
    configured_workflow_profile: str | None
    reasoning_profile: str | None
    requested_reasoning_profile: str | None
    agent_effort_cue: str | None
    handoff_contract: str | None
    handoff_contract_enabled: bool
    handoff_nonce: str | None


HANDOFF_CONTRACT_HEADER = "CHR handoff contract:"
WORKFLOW_PROFILE_GUIDANCE = {
    "light": (
        "Keep context lean; use the handoff body and directly relevant files, "
        "then summarize before handoff."
    ),
    "standard": (
        "Use the target CE workflow, but keep context scoped to the current "
        "task and summarize decisions before handoff."
    ),
    "deep": (
        "Use deeper planning/review for high-risk work, but prefer summaries "
        "over pasted logs or broad context dumps."
    ),
}
REASONING_PROFILE_GUIDANCE = {
    "minimal": (
        "Use the smallest useful amount of internal reasoning; avoid extra "
        "exploration and keep the handoff focused."
    ),
    "low": (
        "Use concise internal reasoning and avoid broad exploration unless the "
        "task is blocked."
    ),
    "medium": (
        "Use balanced internal reasoning; check the directly relevant evidence "
        "before acting."
    ),
    "high": (
        "Use deeper internal reasoning for risk and design tradeoffs, then keep "
        "the visible response concise."
    ),
}
AGENT_EFFORT_CUES = {
    "codex": {
        "minimal": 'Codex model_reasoning_effort="minimal"',
        "low": 'Codex model_reasoning_effort="low"',
        "medium": 'Codex model_reasoning_effort="medium"',
        "high": 'Codex model_reasoning_effort="high"',
    },
    "claude": {
        "minimal": 'Claude Code "think"',
        "low": 'Claude Code "think hard"',
        "medium": 'Claude Code "think harder"',
        "high": 'Claude Code "ultrathink"',
    },
    "gemini": {
        "minimal": "Gemini/Antigravity fast mode or thinking_level=MINIMAL",
        "low": "Gemini/Antigravity thinking_level=LOW",
        "medium": "Gemini/Antigravity thinking_level=MEDIUM",
        "high": "Gemini/Antigravity thinking_level=HIGH",
    },
    "cursor": {
        "minimal": "Cursor normal/non-thinking mode",
        "low": "Cursor Thinking model when useful",
        "medium": "Cursor Thinking model",
        "high": "Cursor Max Mode or highest-thinking model",
    },
}
AGENT_ALIASES = {
    "codex": "codex",
    "openai": "codex",
    "gpt": "codex",
    "claude": "claude",
    "claude-code": "claude",
    "claude_code": "claude",
    "anthropic": "claude",
    "gemini": "gemini",
    "google": "gemini",
    "agy": "gemini",
    "antigravity": "gemini",
    "antigravity-cli": "gemini",
    "antigravity_cli": "gemini",
    "cursor": "cursor",
    "cursor-agent": "cursor",
    "cursor_agent": "cursor",
    "agent": "cursor",
}


def build_relay_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cmux-handoff",
        description=(
            "Safely relay explicit HANDOFF blocks between cmux surfaces. "
            "Subcommands: doctor, discover, init, watch."
        ),
    )
    parser.add_argument(
        "--from",
        dest="source_role",
        required=True,
        help="Source role name from the config, such as main or review.",
    )
    parser.add_argument(
        "--config",
        default=DEFAULT_CONFIG_PATH,
        help=f"Path to role-to-surface config. Defaults to {DEFAULT_CONFIG_PATH}.",
    )
    parser.add_argument(
        "--lines",
        type=int,
        default=200,
        help="Number of scrollback lines to read from the source surface.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview only. Do not send anything to cmux.",
    )
    parser.add_argument(
        "--submit",
        action="store_true",
        help="After sending the payload, explicitly press Enter in the target surface.",
    )
    parser.add_argument(
        "--submit-delay",
        type=float,
        default=None,
        help=(
            "Seconds to wait between sending text and pressing Enter. "
            f"Defaults to target role submit_delay or {DEFAULT_SUBMIT_DELAY}."
        ),
    )
    parser.add_argument(
        "--mode",
        "--workflow-mode",
        choices=WORKFLOW_MODES,
        default="ce",
        help=(
            "Workflow mode. 'ce' applies configured CE prefixes and contracts; "
            "'smoke' disables both for transport tests."
        ),
    )
    parser.add_argument(
        "--reasoning-profile",
        choices=REASONING_PROFILES,
        help=(
            "Override the target role's advisory reasoning profile for this run."
        ),
    )
    parser.add_argument(
        "--single-line",
        action="store_true",
        help="Replace internal newlines with spaces before previewing and sending.",
    )
    parser.add_argument(
        "--no-ce",
        "--no-workflow-prefix",
        dest="workflow_prefix_enabled",
        action="store_false",
        default=True,
        help="Do not prepend the target role's configured CE/workflow prefix.",
    )
    parser.add_argument(
        "--no-handoff-contract",
        dest="handoff_contract_enabled",
        action="store_false",
        default=True,
        help="Do not append the CHR continuation contract to the outgoing payload.",
    )
    parser.add_argument(
        "--nonce",
        help=(
            "Require the source HANDOFF block to include this nonce. "
            "Use 'auto' to generate a session nonce."
        ),
    )
    parser.add_argument(
        "--input-file",
        help="Read captured source text from a file instead of cmux. Useful for dry runs and tests.",
    )
    parser.add_argument(
        "--cmux-bin",
        default=os.environ.get("CMUX_HANDOFF_CMUX_BIN"),
        help=(
            "cmux executable to run. Defaults to CMUX_HANDOFF_CMUX_BIN, PATH, "
            f"or {APP_BUNDLE_CMUX_BIN}. "
            "Useful for DMG installs where the CLI is inside the app bundle."
        ),
    )
    add_cmux_workspace_arg(parser)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    return run(argv)


def run(
    argv: Sequence[str] | None = None,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
    stdin: TextIO | None = None,
    cmux_client: CmuxClient | None = None,
) -> int:
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr
    stdin = stdin or sys.stdin

    argv_list = list(sys.argv[1:] if argv is None else argv)
    if argv_list and argv_list[0] in SUBCOMMANDS:
        return run_subcommand(
            argv_list,
            stdout=stdout,
            stderr=stderr,
            stdin=stdin,
            cmux_client=cmux_client,
        )

    return run_relay(
        argv_list,
        stdout=stdout,
        stderr=stderr,
        stdin=stdin,
        cmux_client=cmux_client,
    )


def run_relay(
    argv: Sequence[str],
    *,
    stdout: TextIO,
    stderr: TextIO,
    stdin: TextIO,
    cmux_client: CmuxClient | None = None,
) -> int:
    parser = build_relay_parser()
    args = parser.parse_args(argv)

    try:
        if args.lines <= 0:
            raise HandoffRelayError("--lines must be a positive integer.")
        if args.submit_delay is not None and args.submit_delay < 0:
            raise HandoffRelayError("--submit-delay must be zero or greater.")
        workspace = resolve_workspace(args.workspace)

        active_nonce = resolve_nonce(args.nonce)
        config = load_config(args.config)
        source_surface = config.surface_for(args.source_role)

        client = cmux_client
        if args.input_file:
            screen_text = Path(args.input_file).read_text(encoding="utf-8")
        else:
            if client is None:
                client = CmuxClient(args.cmux_bin, workspace=workspace)
            screen_text = client.read_screen(source_surface, args.lines)
            verify_screen_surface_hint(
                role_name=args.source_role,
                role_config=config.role_for(args.source_role),
                screen_text=screen_text,
            )

        block = parse_latest_handoff(screen_text)
        verify_handoff_nonce(block, active_nonce)
        target_role = config.role_for(block.target)
        config.ensure_target_allowed(args.source_role, block.target)
        target_surface = target_role.surface
        workflow_prefix_enabled = workflow_prefix_enabled_for(args)
        handoff_contract_enabled = handoff_contract_enabled_for(args)
        payload = build_payload(
            body=block.body,
            workflow_prefix=target_role.ce_default,
            workflow_profile=target_role.workflow_profile,
            target_agent=target_role.agent,
            reasoning_profile=resolve_reasoning_profile(
                args.reasoning_profile, target_role
            ),
            workflow_prefix_enabled=workflow_prefix_enabled,
            handoff_contract_enabled=handoff_contract_enabled,
            handoff_nonce=active_nonce,
            source_role=args.source_role,
            target_role=block.target,
            available_roles=config.allowed_targets_for(block.target),
            single_line=args.single_line,
        )

        print_preview(
            block=block,
            source_role=args.source_role,
            source_surface=source_surface,
            target_surface=target_surface,
            payload=payload,
            cli_submit=args.submit,
            single_line=args.single_line,
            stdout=stdout,
        )

        if args.dry_run:
            stdout.write("Dry run: no cmux send performed.\n")
            return 0

        confirm_send(target_surface=target_surface, stdout=stdout, stdin=stdin)

        if client is None:
            client = CmuxClient(args.cmux_bin, workspace=workspace)
        verify_live_surface_hint(
            client=client,
            role_name=block.target,
            role_config=target_role,
            lines=args.lines,
        )
        client.send_text(target_surface, payload.text)

        if args.submit:
            time.sleep(resolve_submit_delay(args.submit_delay, target_role))
            client.send_enter(target_surface)
            stdout.write("Sent payload and pressed Enter because --submit was passed.\n")
        else:
            stdout.write("Sent payload. Enter was not pressed.\n")

        return 0
    except HandoffRelayError as exc:
        stderr.write(f"Error: {exc}\n")
        return 1
    except OSError as exc:
        stderr.write(f"Error: {exc}\n")
        return 1


def run_subcommand(
    argv: Sequence[str],
    *,
    stdout: TextIO,
    stderr: TextIO,
    stdin: TextIO,
    cmux_client: CmuxClient | None = None,
) -> int:
    command = argv[0]
    if command == "doctor":
        return run_doctor(argv[1:], stdout=stdout, stderr=stderr)
    if command == "discover":
        return run_discover(argv[1:], stdout=stdout, stderr=stderr)
    if command == "init":
        return run_init(argv[1:], stdout=stdout, stderr=stderr, stdin=stdin)
    if command == "watch":
        return run_watch(
            argv[1:],
            stdout=stdout,
            stderr=stderr,
            stdin=stdin,
            cmux_client=cmux_client,
        )
    stderr.write(f"Error: unknown subcommand '{command}'\n")
    return 1


def add_cmux_bin_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--cmux-bin",
        default=os.environ.get("CMUX_HANDOFF_CMUX_BIN"),
        help=(
            "cmux executable to run. Defaults to CMUX_HANDOFF_CMUX_BIN, PATH, "
            f"or {APP_BUNDLE_CMUX_BIN}."
        ),
    )


def add_cmux_workspace_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--workspace",
        help=(
            "cmux workspace ref or ID to pass to read/send commands. "
            "Useful when relaying a workspace other than the caller's current workspace."
        ),
    )


def run_doctor(argv: Sequence[str], *, stdout: TextIO, stderr: TextIO) -> int:
    parser = argparse.ArgumentParser(
        prog="cmux-handoff doctor",
        description="Check cmux-handoff and cmux CLI readiness without changing cmux state.",
    )
    add_cmux_bin_arg(parser)
    add_cmux_workspace_arg(parser)
    parser.add_argument(
        "--config",
        default=DEFAULT_CONFIG_PATH,
        help=f"Config path to inspect. Defaults to {DEFAULT_CONFIG_PATH}.",
    )
    args = parser.parse_args(argv)

    try:
        workspace = resolve_workspace(args.workspace)
    except HandoffRelayError as exc:
        stderr.write(f"Error: {exc}\n")
        return 1

    cmux_bin = detect_cmux_executable(args.cmux_bin)
    stdout.write("cmux-handoff doctor\n")
    stdout.write(f"cmux binary: {cmux_bin}\n")

    client = CmuxClient(cmux_bin, workspace=workspace)
    status_ok = True

    try:
        stdout.write(f"cmux version: {client.version()}\n")
    except CmuxCommandError as exc:
        stderr.write(f"Error: {exc}\n")
        return 1

    try:
        client.ping()
        stdout.write("cmux socket: ok\n")
    except CmuxCommandError as exc:
        status_ok = False
        stdout.write("cmux socket: failed\n")
        stderr.write(f"Warning: {exc}\n")

    config_path = Path(args.config)
    if config_path.exists():
        try:
            config = load_config(config_path)
            stdout.write(f"config: ok ({len(config.roles)} roles)\n")
            hint_failures = check_surface_hints(client, config, stdout, stderr)
            if hint_failures:
                status_ok = False
        except HandoffRelayError as exc:
            status_ok = False
            stdout.write("config: failed\n")
            stderr.write(f"Warning: {exc}\n")
    else:
        status_ok = False
        stdout.write(f"config: missing ({config_path})\n")

    if not status_ok:
        stdout.write("doctor result: attention needed\n")
        return 1

    stdout.write("doctor result: ok\n")
    return 0


def run_discover(argv: Sequence[str], *, stdout: TextIO, stderr: TextIO) -> int:
    parser = argparse.ArgumentParser(
        prog="cmux-handoff discover",
        description="Print cmux panes and optionally surfaces for a pane.",
    )
    add_cmux_bin_arg(parser)
    add_cmux_workspace_arg(parser)
    parser.add_argument(
        "--pane",
        help="Pane ref or ID to inspect with cmux list-pane-surfaces --pane.",
    )
    args = parser.parse_args(argv)

    try:
        workspace = resolve_workspace(args.workspace)
        client = CmuxClient(args.cmux_bin, workspace=workspace)
    except HandoffRelayError as exc:
        stderr.write(f"Error: {exc}\n")
        return 1

    try:
        panels = client.list_panels()
        surfaces = client.list_pane_surfaces(args.pane) if args.pane else None
        stdout.write("cmux panels\n")
        stdout.write("--- BEGIN PANELS ---\n")
        stdout.write(panels)
        stdout.write("--- END PANELS ---\n")
        if surfaces is not None:
            stdout.write(f"cmux surfaces for pane {args.pane}\n")
            stdout.write("--- BEGIN SURFACES ---\n")
            stdout.write(surfaces)
            stdout.write("--- END SURFACES ---\n")
        else:
            stdout.write("Next: run discover again with --pane <pane_id> to list surfaces.\n")
        return 0
    except CmuxCommandError as exc:
        stderr.write(f"Error: {exc}\n")
        return 1


def run_init(
    argv: Sequence[str],
    *,
    stdout: TextIO,
    stderr: TextIO,
    stdin: TextIO,
) -> int:
    parser = argparse.ArgumentParser(
        prog="cmux-handoff init",
        description="Create a starter .cmux-handoff.json without secrets.",
    )
    parser.add_argument(
        "--config",
        default=DEFAULT_CONFIG_PATH,
        help=f"Config file to create. Defaults to {DEFAULT_CONFIG_PATH}.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing config after confirmation.",
    )
    parser.add_argument(
        "--classic",
        action="store_true",
        help="Create a legacy surface-only config instead of the CE-first template.",
    )
    args = parser.parse_args(argv)

    path = Path(args.config)
    try:
        if path.exists() and not args.force:
            stderr.write(
                f"Error: config already exists: {path}. Use --force to overwrite intentionally.\n"
            )
            return 1
        if path.exists() and args.force:
            stdout.write(f"Overwrite existing config '{path}'? Type 'yes' to continue: ")
            stdout.flush()
            if stdin.readline().strip() != "yes":
                raise HandoffAbort("Aborted by user; config was not modified.")

        template = CLASSIC_CONFIG if args.classic else CE_FIRST_CONFIG
        path.write_text(template, encoding="utf-8")
        stdout.write(f"Created {path}\n")
        stdout.write("Edit role surface IDs after running cmux-handoff discover.\n")
        if args.classic:
            stdout.write("Template: classic surface-only\n")
        else:
            stdout.write("Template: CE-first workflow prefixes\n")
        return 0
    except HandoffRelayError as exc:
        stderr.write(f"Error: {exc}\n")
        return 1
    except OSError as exc:
        stderr.write(f"Error: {exc}\n")
        return 1


def run_watch(
    argv: Sequence[str],
    *,
    stdout: TextIO,
    stderr: TextIO,
    stdin: TextIO,
    cmux_client: CmuxClient | None = None,
) -> int:
    parser = argparse.ArgumentParser(
        prog="cmux-handoff watch",
        description="Watch configured cmux roles and relay new HANDOFF blocks by target role.",
    )
    add_cmux_bin_arg(parser)
    add_cmux_workspace_arg(parser)
    parser.add_argument(
        "--config",
        default=DEFAULT_CONFIG_PATH,
        help=f"Path to role-to-surface config. Defaults to {DEFAULT_CONFIG_PATH}.",
    )
    parser.add_argument(
        "--roles",
        help="Comma-separated source roles to watch. Defaults to every role in the config.",
    )
    parser.add_argument(
        "--lines",
        type=int,
        default=200,
        help="Number of scrollback lines to read from each source surface.",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=2.0,
        help="Seconds to wait between polling cycles.",
    )
    parser.add_argument(
        "--max-turns",
        type=int,
        default=12,
        help="Maximum handoffs to relay before stopping. Use 0 for unlimited.",
    )
    parser.add_argument(
        "--idle-polls",
        type=int,
        default=0,
        help="Stop after this many polling cycles with no new handoff. Defaults to 0, meaning wait indefinitely.",
    )
    parser.add_argument(
        "--relay-existing",
        action="store_true",
        help="Relay latest handoff blocks that already exist when watch starts.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview matching handoffs without sending anything to cmux.",
    )
    parser.add_argument(
        "--submit",
        action="store_true",
        help="After each payload, explicitly press Enter in the target surface.",
    )
    parser.add_argument(
        "--submit-delay",
        type=float,
        default=None,
        help=(
            "Seconds to wait between sending text and pressing Enter. "
            f"Defaults to target role submit_delay or {DEFAULT_SUBMIT_DELAY}."
        ),
    )
    parser.add_argument(
        "--mode",
        "--workflow-mode",
        choices=WORKFLOW_MODES,
        default="ce",
        help=(
            "Workflow mode. 'ce' applies configured CE prefixes and contracts; "
            "'smoke' disables both for transport tests."
        ),
    )
    parser.add_argument(
        "--reasoning-profile",
        choices=REASONING_PROFILES,
        help=(
            "Override every target role's advisory reasoning profile for this run."
        ),
    )
    parser.add_argument(
        "--single-line",
        action="store_true",
        help="Replace internal newlines with spaces before previewing and sending.",
    )
    parser.add_argument(
        "--no-ce",
        "--no-workflow-prefix",
        dest="workflow_prefix_enabled",
        action="store_false",
        default=True,
        help="Do not prepend the target role's configured CE/workflow prefix.",
    )
    parser.add_argument(
        "--no-handoff-contract",
        dest="handoff_contract_enabled",
        action="store_false",
        default=True,
        help="Do not append the CHR continuation contract to each outgoing payload.",
    )
    parser.add_argument(
        "--nonce",
        help=(
            "Require watched HANDOFF blocks to include this nonce. "
            "Use 'auto' to generate a session nonce."
        ),
    )
    parser.add_argument(
        "--confirm",
        choices=("each", "never"),
        default="each",
        help="Confirmation policy before sending. Defaults to each.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Alias for --confirm never. Use only when you intentionally want automatic relay.",
    )
    args = parser.parse_args(argv)

    try:
        if args.lines <= 0:
            raise HandoffRelayError("--lines must be a positive integer.")
        if args.submit_delay is not None and args.submit_delay < 0:
            raise HandoffRelayError("--submit-delay must be zero or greater.")
        if args.interval < 0:
            raise HandoffRelayError("--interval must be zero or greater.")
        if args.max_turns < 0:
            raise HandoffRelayError("--max-turns must be zero or greater.")
        if args.idle_polls < 0:
            raise HandoffRelayError("--idle-polls must be zero or greater.")
        workspace = resolve_workspace(args.workspace)

        active_nonce = resolve_nonce(args.nonce)
        confirm_policy = "never" if args.yes else args.confirm
        if confirm_policy == "never" and not args.dry_run and args.max_turns == 0:
            raise HandoffRelayError(
                "--max-turns 0 cannot be combined with --yes/--confirm never."
            )
        if confirm_policy == "never" and not args.dry_run and not active_nonce:
            raise HandoffRelayError(
                "Automatic relay requires --nonce. Use --nonce auto to arm a "
                "one-time session nonce."
            )

        config = load_config(args.config)
        roles = parse_watch_roles(args.roles, config.roles)
        source_surfaces = {role: config.surface_for(role) for role in roles}
        client = cmux_client or CmuxClient(args.cmux_bin, workspace=workspace)
        seen: dict[str, str] = {}
        warning_cache: set[tuple[str, str]] = set()
        workflow_prefix_enabled = workflow_prefix_enabled_for(args)
        handoff_contract_enabled = handoff_contract_enabled_for(args)

        stdout.write(f"Watching roles: {', '.join(roles)}\n")
        stdout.write(
            "Confirmation: none\n"
            if confirm_policy == "never"
            else "Confirmation: each handoff\n"
        )
        if args.max_turns == 0:
            stdout.write("Max turns: unlimited\n")
        else:
            stdout.write(f"Max turns: {args.max_turns}\n")
        if active_nonce:
            stdout.write(f"Session nonce: {active_nonce}\n")

        if not args.relay_existing:
            for role in roles:
                event = read_watch_event_or_warn(
                    client=client,
                    config=config,
                    source_role=role,
                    source_surface=source_surfaces[role],
                    lines=args.lines,
                    single_line=args.single_line,
                    workflow_prefix_enabled=workflow_prefix_enabled,
                    handoff_contract_enabled=handoff_contract_enabled,
                    reasoning_profile_override=args.reasoning_profile,
                    active_nonce=active_nonce,
                    warning_cache=warning_cache,
                    stderr=stderr,
                )
                if event is not None:
                    seen[role] = event.fingerprint
            stdout.write("Existing handoffs baselined; waiting for new handoffs.\n")

        turns = 0
        idle_polls = 0
        enter_failures = 0
        while True:
            relayed_this_poll = False
            for role in roles:
                event = read_watch_event_or_warn(
                    client=client,
                    config=config,
                    source_role=role,
                    source_surface=source_surfaces[role],
                    lines=args.lines,
                    single_line=args.single_line,
                    workflow_prefix_enabled=workflow_prefix_enabled,
                    handoff_contract_enabled=handoff_contract_enabled,
                    reasoning_profile_override=args.reasoning_profile,
                    active_nonce=active_nonce,
                    warning_cache=warning_cache,
                    stderr=stderr,
                )
                if event is None or seen.get(role) == event.fingerprint:
                    continue

                next_turn = turns + 1
                stdout.write(f"Watch turn: {next_turn}\n")
                print_preview(
                    block=event.block,
                    source_role=event.source_role,
                    source_surface=event.source_surface,
                    target_surface=event.target_surface,
                    payload=event.payload,
                    cli_submit=args.submit,
                    single_line=args.single_line,
                    stdout=stdout,
                )

                if args.dry_run:
                    stdout.write("Watch dry run: no cmux send performed.\n")
                else:
                    if confirm_policy == "each":
                        confirm_send(
                            target_surface=event.target_surface,
                            stdout=stdout,
                            stdin=stdin,
                        )
                    try:
                        verify_live_surface_hint(
                            client=client,
                            role_name=event.block.target,
                            role_config=config.role_for(event.block.target),
                            lines=args.lines,
                        )
                        client.send_text(event.target_surface, event.payload.text)
                    except (CmuxCommandError, HandoffAuthError) as exc:
                        warn_once_watch_error(
                            event.source_role,
                            event.source_surface,
                            exc,
                            warning_cache,
                            stderr,
                        )
                        continue
                    if args.submit:
                        try:
                            time.sleep(
                                resolve_submit_delay(
                                    args.submit_delay,
                                    config.role_for(event.block.target),
                                )
                            )
                            client.send_enter(event.target_surface)
                        except CmuxCommandError as exc:
                            enter_failures += 1
                            warn_once_watch_enter_error(
                                event.block.target,
                                event.target_surface,
                                exc,
                                warning_cache,
                                stderr,
                            )
                            stdout.write(
                                "Sent payload. Enter failed; payload will not be resent.\n"
                            )
                        else:
                            stdout.write(
                                "Sent payload and pressed Enter because --submit was passed.\n"
                            )
                    else:
                        stdout.write("Sent payload. Enter was not pressed.\n")

                seen[role] = event.fingerprint
                relayed_this_poll = True
                turns = next_turn
                if args.max_turns and turns >= args.max_turns:
                    return finish_watch(
                        "Watch stopped: max turns reached.",
                        enter_failures=enter_failures,
                        stdout=stdout,
                        stderr=stderr,
                    )

            if relayed_this_poll:
                idle_polls = 0
            else:
                idle_polls += 1
                if args.idle_polls and idle_polls >= args.idle_polls:
                    return finish_watch(
                        "Watch stopped: idle poll limit reached.",
                        enter_failures=enter_failures,
                        stdout=stdout,
                        stderr=stderr,
                    )

            time.sleep(args.interval)
    except HandoffRelayError as exc:
        stderr.write(f"Error: {exc}\n")
        return 1
    except OSError as exc:
        stderr.write(f"Error: {exc}\n")
        return 1


def parse_watch_roles(
    raw_roles: str | None, config_roles: Mapping[str, object]
) -> list[str]:
    if raw_roles is None:
        return list(config_roles.keys())

    roles: list[str] = []
    seen: set[str] = set()
    for role in raw_roles.split(","):
        normalized = role.strip()
        if not normalized:
            continue
        if normalized not in seen:
            roles.append(normalized)
            seen.add(normalized)

    if not roles:
        raise HandoffRelayError("--roles must include at least one role.")

    return roles


def read_watch_event(
    *,
    client: CmuxClient,
    config: RelayConfig,
    source_role: str,
    source_surface: str,
    lines: int,
    single_line: bool,
    workflow_prefix_enabled: bool,
    handoff_contract_enabled: bool,
    reasoning_profile_override: str | None,
    active_nonce: str | None,
) -> WatchEvent | None:
    screen_text = client.read_screen(source_surface, lines)
    verify_screen_surface_hint(
        role_name=source_role,
        role_config=config.role_for(source_role),
        screen_text=screen_text,
    )
    try:
        block = parse_latest_handoff(screen_text)
    except HandoffParseError as exc:
        if str(exc) == NO_HANDOFF_MESSAGE:
            return None
        raise

    verify_handoff_nonce(block, active_nonce)
    target_role = config.role_for(block.target)
    config.ensure_target_allowed(source_role, block.target)

    payload = build_payload(
        body=block.body,
        workflow_prefix=target_role.ce_default,
        workflow_profile=target_role.workflow_profile,
        target_agent=target_role.agent,
        reasoning_profile=resolve_reasoning_profile(
            reasoning_profile_override, target_role
        ),
        workflow_prefix_enabled=workflow_prefix_enabled,
        handoff_contract_enabled=handoff_contract_enabled,
        handoff_nonce=active_nonce,
        source_role=source_role,
        target_role=block.target,
        available_roles=config.allowed_targets_for(block.target),
        single_line=single_line,
    )
    return WatchEvent(
        source_role=source_role,
        source_surface=source_surface,
        block=block,
        target_surface=target_role.surface,
        payload=payload,
        fingerprint=(
            f"{block.target}\0{str(block.submit).lower()}\0"
            f"{block.nonce or ''}\0{payload.text}"
        ),
    )


def read_watch_event_or_warn(
    *,
    client: CmuxClient,
    config: RelayConfig,
    source_role: str,
    source_surface: str,
    lines: int,
    single_line: bool,
    workflow_prefix_enabled: bool,
    handoff_contract_enabled: bool,
    reasoning_profile_override: str | None,
    active_nonce: str | None,
    warning_cache: set[tuple[str, str]],
    stderr: TextIO,
) -> WatchEvent | None:
    try:
        return read_watch_event(
            client=client,
            config=config,
            source_role=source_role,
            source_surface=source_surface,
            lines=lines,
            single_line=single_line,
            workflow_prefix_enabled=workflow_prefix_enabled,
            handoff_contract_enabled=handoff_contract_enabled,
            reasoning_profile_override=reasoning_profile_override,
            active_nonce=active_nonce,
        )
    except HandoffParseError as exc:
        if str(exc) == NO_HANDOFF_MESSAGE:
            return None
        warn_once_watch_error(source_role, source_surface, exc, warning_cache, stderr)
        return None
    except HandoffConfigError as exc:
        warn_once_watch_error(source_role, source_surface, exc, warning_cache, stderr)
        return None
    except HandoffAuthError as exc:
        warn_once_watch_error(source_role, source_surface, exc, warning_cache, stderr)
        return None
    except CmuxCommandError as exc:
        warn_once_watch_error(source_role, source_surface, exc, warning_cache, stderr)
        return None


def check_surface_hints(
    client: CmuxClient, config: RelayConfig, stdout: TextIO, stderr: TextIO
) -> bool:
    failures = False
    checked = 0
    for role_name, role_config in config.role_configs.items():
        if not role_config.surface_hint:
            continue
        checked += 1
        try:
            verify_live_surface_hint(
                client=client,
                role_name=role_name,
                role_config=role_config,
                lines=20,
            )
        except HandoffRelayError as exc:
            failures = True
            stderr.write(f"Warning: {exc}\n")

    if checked:
        status = "failed" if failures else "ok"
        stdout.write(f"surface hints: {status} ({checked} checked)\n")
    return failures


def verify_live_surface_hint(
    *,
    client: CmuxClient,
    role_name: str,
    role_config: RoleConfig,
    lines: int,
) -> None:
    if not role_config.surface_hint:
        return
    screen_text = client.read_screen(role_config.surface, lines)
    verify_screen_surface_hint(
        role_name=role_name,
        role_config=role_config,
        screen_text=screen_text,
    )


def verify_screen_surface_hint(
    *,
    role_name: str,
    role_config: RoleConfig,
    screen_text: str,
) -> None:
    if not role_config.surface_hint:
        return
    if role_config.surface_hint not in screen_text:
        raise HandoffAuthError(
            f"Surface hint mismatch for role '{role_name}' on "
            f"{role_config.surface}."
        )


def resolve_nonce(raw_nonce: str | None) -> str | None:
    if raw_nonce is None:
        return None
    nonce = raw_nonce.strip()
    if not nonce:
        raise HandoffRelayError("--nonce must be non-empty when set.")
    if nonce == "auto":
        return secrets.token_urlsafe(12)
    return nonce


def resolve_workspace(raw_workspace: str | None) -> str | None:
    if raw_workspace is None:
        return None
    return validate_workspace_ref(raw_workspace)


def verify_handoff_nonce(block: HandoffBlock, required_nonce: str | None) -> None:
    if required_nonce is None:
        return
    if block.nonce != required_nonce:
        raise HandoffAuthError("HANDOFF nonce missing or mismatched.")


def warn_once_watch_error(
    source_role: str,
    source_surface: str,
    exc: Exception,
    warning_cache: set[tuple[str, str]],
    stderr: TextIO,
) -> None:
    message = str(exc)
    key = (source_role, message)
    if key in warning_cache:
        return

    warning_cache.add(key)
    stderr.write(
        f"Warning: skipping role '{source_role}' on {source_surface}: {message}\n"
    )


def warn_once_watch_enter_error(
    target_role: str,
    target_surface: str,
    exc: Exception,
    warning_cache: set[tuple[str, str]],
    stderr: TextIO,
) -> None:
    message = str(exc)
    key = (target_role, f"enter:{message}")
    if key in warning_cache:
        return

    warning_cache.add(key)
    stderr.write(
        "Warning: sent payload to "
        f"'{target_role}' on {target_surface} but failed to press Enter: {message}\n"
    )


def finish_watch(
    message: str,
    *,
    enter_failures: int,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    stdout.write(f"{message}\n")
    if enter_failures:
        stderr.write(
            "Error: "
            f"{enter_failures} payload(s) were sent but Enter failed; "
            "inspect target panes before continuing automation.\n"
        )
        return WATCH_ENTER_FAILURE_EXIT_CODE
    return 0


def workflow_prefix_enabled_for(args: argparse.Namespace) -> bool:
    return bool(args.workflow_prefix_enabled and args.mode != "smoke")


def handoff_contract_enabled_for(args: argparse.Namespace) -> bool:
    return bool(args.handoff_contract_enabled and args.mode != "smoke")


def resolve_submit_delay(cli_delay: float | None, role_config: RoleConfig) -> float:
    if cli_delay is not None:
        return cli_delay
    if role_config.submit_delay is not None:
        return role_config.submit_delay
    return DEFAULT_SUBMIT_DELAY


def resolve_reasoning_profile(
    cli_profile: str | None, role_config: RoleConfig
) -> str | None:
    return cli_profile or role_config.reasoning_profile


def resolve_agent_effort_cue(
    agent: str | None, reasoning_profile: str | None
) -> str | None:
    if not agent or not reasoning_profile:
        return None
    canonical_agent = AGENT_ALIASES.get(agent.strip().lower())
    if not canonical_agent:
        return None
    return AGENT_EFFORT_CUES[canonical_agent][reasoning_profile]


def to_single_line(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", " ")


def build_payload(
    *,
    body: str,
    workflow_prefix: str | None,
    workflow_profile: str | None,
    target_agent: str | None,
    reasoning_profile: str | None,
    workflow_prefix_enabled: bool,
    handoff_contract_enabled: bool,
    handoff_nonce: str | None,
    source_role: str,
    target_role: str,
    available_roles: Iterable[str],
    single_line: bool,
) -> BuiltPayload:
    configured_workflow_prefix = workflow_prefix.strip() if workflow_prefix else None
    applied_workflow_prefix = (
        configured_workflow_prefix if workflow_prefix_enabled else None
    )
    configured_workflow_profile = workflow_profile.strip() if workflow_profile else None
    applied_workflow_profile = (
        configured_workflow_profile if handoff_contract_enabled else None
    )
    requested_reasoning_profile = (
        reasoning_profile.strip() if reasoning_profile else None
    )
    applied_reasoning_profile = (
        requested_reasoning_profile if handoff_contract_enabled else None
    )
    agent_effort_cue = (
        resolve_agent_effort_cue(target_agent, applied_reasoning_profile)
        if handoff_contract_enabled
        else None
    )
    handoff_contract = (
        build_handoff_contract(
            source_role=source_role,
            target_role=target_role,
            available_roles=available_roles,
            workflow_profile=applied_workflow_profile,
            reasoning_profile=applied_reasoning_profile,
            agent_effort_cue=agent_effort_cue,
            handoff_nonce=handoff_nonce,
        )
        if handoff_contract_enabled
        else None
    )

    payload_parts = [
        part for part in (applied_workflow_prefix, body, handoff_contract) if part
    ]
    payload = "\n\n".join(payload_parts)
    if single_line:
        payload = to_single_line(payload)

    return BuiltPayload(
        text=payload,
        workflow_prefix=applied_workflow_prefix,
        configured_workflow_prefix=configured_workflow_prefix,
        workflow_prefix_enabled=workflow_prefix_enabled,
        workflow_profile=applied_workflow_profile,
        configured_workflow_profile=configured_workflow_profile,
        reasoning_profile=applied_reasoning_profile,
        requested_reasoning_profile=requested_reasoning_profile,
        agent_effort_cue=agent_effort_cue,
        handoff_contract=handoff_contract,
        handoff_contract_enabled=handoff_contract_enabled,
        handoff_nonce=handoff_nonce,
    )


def build_handoff_contract(
    *,
    source_role: str,
    target_role: str,
    available_roles: Iterable[str],
    workflow_profile: str | None,
    reasoning_profile: str | None,
    agent_effort_cue: str | None,
    handoff_nonce: str | None,
) -> str:
    roles = ", ".join(available_roles) or "<none>"
    profile_line = ""
    if workflow_profile:
        guidance = WORKFLOW_PROFILE_GUIDANCE[workflow_profile]
        profile_line = f"- Workflow profile: {workflow_profile}. {guidance}\n"
    reasoning_line = ""
    if reasoning_profile:
        guidance = REASONING_PROFILE_GUIDANCE[reasoning_profile]
        cue = (
            " Agent effort cue: "
            f"{agent_effort_cue} (plain-text hint; CHR does not change app "
            "settings, but the target agent may interpret it)."
            if agent_effort_cue
            else ""
        )
        reasoning_line = (
            f"- Reasoning profile: {reasoning_profile}. {guidance}{cue}\n"
        )
    nonce_line = (
        f"- Future handoff headers from this worker must include "
        f"`nonce={handoff_nonce}`.\n"
        if handoff_nonce
        else ""
    )
    return (
        f"{HANDOFF_CONTRACT_HEADER}\n"
        f"- Current role: {target_role}; source role: {source_role}; "
        f"available target roles: {roles}.\n"
        f"{profile_line}"
        f"{reasoning_line}"
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


def print_preview(
    *,
    block: HandoffBlock,
    source_role: str,
    source_surface: str,
    target_surface: str,
    payload: BuiltPayload,
    cli_submit: bool,
    single_line: bool,
    stdout: TextIO,
) -> None:
    stdout.write("Handoff preview\n")
    stdout.write(f"Source role: {source_role}\n")
    stdout.write(f"Source surface: {source_surface}\n")
    stdout.write(f"Target role: {block.target}\n")
    stdout.write(f"Target surface: {target_surface}\n")
    stdout.write(f"Workflow prefix: {format_workflow_prefix(payload)}\n")
    stdout.write(f"Workflow profile: {format_workflow_profile(payload)}\n")
    stdout.write(f"Reasoning profile: {format_reasoning_profile(payload)}\n")
    stdout.write(f"Agent effort cue: {format_agent_effort_cue(payload)}\n")
    stdout.write(f"Handoff contract: {format_handoff_contract(payload)}\n")
    stdout.write(f"Block submit metadata: {str(block.submit).lower()} (parsed only)\n")
    stdout.write(f"CLI --submit: {str(cli_submit).lower()}\n")
    if single_line:
        stdout.write("Payload transform: internal newlines replaced with spaces\n")
    stdout.write(f"Payload characters: {len(payload.text)}\n")
    stdout.write("--- BEGIN PAYLOAD ---\n")
    stdout.write(payload.text)
    stdout.write("\n--- END PAYLOAD ---\n")


def format_workflow_prefix(payload: BuiltPayload) -> str:
    if payload.workflow_prefix:
        return payload.workflow_prefix
    if payload.configured_workflow_prefix and not payload.workflow_prefix_enabled:
        return f"disabled (configured: {payload.configured_workflow_prefix})"
    return "none"


def format_workflow_profile(payload: BuiltPayload) -> str:
    if payload.workflow_profile:
        return payload.workflow_profile
    if payload.configured_workflow_profile and not payload.handoff_contract_enabled:
        return f"disabled (configured: {payload.configured_workflow_profile})"
    return "none"


def format_reasoning_profile(payload: BuiltPayload) -> str:
    if payload.reasoning_profile:
        return payload.reasoning_profile
    if payload.requested_reasoning_profile and not payload.handoff_contract_enabled:
        return f"disabled (requested: {payload.requested_reasoning_profile})"
    return "none"


def format_agent_effort_cue(payload: BuiltPayload) -> str:
    if payload.agent_effort_cue:
        return payload.agent_effort_cue
    if payload.requested_reasoning_profile and not payload.handoff_contract_enabled:
        return "disabled"
    return "none"


def format_handoff_contract(payload: BuiltPayload) -> str:
    if payload.handoff_contract:
        return "enabled"
    if not payload.handoff_contract_enabled:
        return "disabled"
    return "none"


def confirm_send(*, target_surface: str, stdout: TextIO, stdin: TextIO) -> None:
    stdout.write(
        f"Send this payload to cmux surface '{target_surface}'? "
        "Type 'yes' to continue: "
    )
    stdout.flush()
    raw_answer = stdin.readline()
    if raw_answer == "":
        raise HandoffAbort(
            "No confirmation input available; run in an interactive terminal or pass --yes."
        )
    answer = raw_answer.strip()
    if answer != "yes":
        raise HandoffAbort("Aborted by user; no payload sent.")
