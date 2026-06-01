"""Parser for explicit cmux handoff blocks."""

from __future__ import annotations

from dataclasses import dataclass
import re

from .errors import HandoffParseError

END_MARKER = "<<<END_HANDOFF>>>"
HANDOFF_PREFIX = "<<<HANDOFF"
TERMINAL_GUTTER_PREFIXES = ("• ", "  ")
HEADER_RE = re.compile(
    r"^<<<HANDOFF target=(?P<target>[A-Za-z0-9_.-]+) "
    r"submit=(?P<submit>true|false)"
    r"(?: nonce=(?P<nonce>[A-Za-z0-9_.:-]+))?>>>$"
)


@dataclass(frozen=True)
class HandoffBlock:
    target: str
    submit: bool
    body: str
    nonce: str | None = None


def parse_latest_handoff(text: str) -> HandoffBlock:
    """Parse the latest HANDOFF block from captured screen text.

    The latest block is determined by the latest line beginning with
    ``<<<HANDOFF``. If that latest candidate is malformed, parsing fails even if
    earlier valid blocks exist.
    """

    if not isinstance(text, str):
        raise HandoffParseError("Captured screen text must be a string.")

    lines = [line.rstrip() for line in text.splitlines()]
    marker_lines = [normalize_marker_line(line) for line in lines]
    header_indexes = [
        idx
        for idx, line in enumerate(marker_lines)
        if line.startswith(HANDOFF_PREFIX)
    ]

    if not header_indexes:
        if HANDOFF_PREFIX in text:
            raise HandoffParseError(
                "Malformed HANDOFF block: header must start at the beginning of a line."
            )
        raise HandoffParseError("No HANDOFF block found.")

    start_index = header_indexes[-1]
    for earlier_header_index in header_indexes[:-1]:
        end_before_latest_header = any(
            marker_lines[idx] == END_MARKER
            for idx in range(earlier_header_index + 1, start_index)
        )
        if not end_before_latest_header:
            raise HandoffParseError(
                "Malformed HANDOFF block: nested HANDOFF headers are not supported."
            )

    header = marker_lines[start_index]
    match = HEADER_RE.match(header)
    if not match:
        raise HandoffParseError(
            "Malformed HANDOFF header. Expected: "
            "<<<HANDOFF target=<role> submit=<true|false>>>"
        )

    end_index = None
    for idx in range(start_index + 1, len(lines)):
        if marker_lines[idx] == END_MARKER:
            end_index = idx
            break

    if end_index is None:
        raise HandoffParseError(
            f"Malformed HANDOFF block: missing {END_MARKER} after latest header."
        )

    body_lines = lines[start_index + 1 : end_index]
    body_gutter = marker_gutter_prefix(lines[end_index]) or marker_gutter_prefix(
        lines[start_index]
    )
    if body_gutter:
        body_lines = [strip_terminal_gutter(line, body_gutter) for line in body_lines]
    body = "\n".join(body_lines)
    if body.strip() == "":
        raise HandoffParseError("Malformed HANDOFF block: prompt body is empty.")

    return HandoffBlock(
        target=match.group("target"),
        submit=match.group("submit") == "true",
        body=body,
        nonce=match.group("nonce"),
    )


def normalize_marker_line(line: str) -> str:
    """Return marker text without known terminal UI gutters."""

    if line.startswith(HANDOFF_PREFIX) or line == END_MARKER:
        return line
    prefix = marker_gutter_prefix(line)
    if prefix:
        return line[len(prefix) :]
    return line


def marker_gutter_prefix(line: str) -> str | None:
    for prefix in TERMINAL_GUTTER_PREFIXES:
        if line.startswith(prefix):
            candidate = line[len(prefix) :]
            if candidate.startswith(HANDOFF_PREFIX) or candidate == END_MARKER:
                return prefix
    return None


def strip_terminal_gutter(line: str, prefix: str) -> str:
    if line.startswith(prefix):
        return line[len(prefix) :]
    return line
