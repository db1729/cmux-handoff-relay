"""Thin subprocess wrapper around documented cmux CLI commands."""

from __future__ import annotations

from pathlib import Path
import re
import shutil
import subprocess

from .errors import CmuxCommandError

APP_BUNDLE_CMUX_BIN = "/Applications/cmux.app/Contents/Resources/bin/cmux"
CMUX_COMMAND_TIMEOUT_SECONDS = 10
WORKSPACE_RE = re.compile(r"^(?:workspace:)?[A-Za-z0-9_][A-Za-z0-9_.:-]*$")


def detect_cmux_executable(explicit: str | None = None) -> str:
    """Find a cmux CLI executable without modifying the user's system."""

    if explicit:
        return explicit

    found = shutil.which("cmux")
    if found:
        return found

    app_bundle = Path(APP_BUNDLE_CMUX_BIN)
    if app_bundle.exists():
        return str(app_bundle)

    return "cmux"


class CmuxClient:
    def __init__(
        self, executable: str | None = None, *, workspace: str | None = None
    ) -> None:
        self.executable = detect_cmux_executable(executable)
        self.workspace = validate_workspace_ref(workspace) if workspace else None

    def version(self) -> str:
        result = self._run(["version"], display_args=["version"])
        return result.stdout.strip()

    def ping(self) -> str:
        result = self._run(["ping"], display_args=["ping"])
        return result.stdout.strip()

    def list_panels(self) -> str:
        result = self._run(
            self._scoped(["list-panels"]),
            display_args=self._scoped(["list-panels"]),
        )
        return result.stdout

    def list_pane_surfaces(self, pane: str) -> str:
        result = self._run(
            self._scoped(["list-pane-surfaces", "--pane", pane]),
            display_args=self._scoped(["list-pane-surfaces", "--pane", pane]),
        )
        return result.stdout

    def read_screen(self, surface: str, lines: int) -> str:
        result = self._run(
            self._scoped(
                [
                    "read-screen",
                    "--scrollback",
                    "--lines",
                    str(lines),
                    "--surface",
                    surface,
                ]
            ),
            display_args=self._scoped(
                [
                    "read-screen",
                    "--scrollback",
                    "--lines",
                    str(lines),
                    "--surface",
                    surface,
                ]
            ),
        )
        return result.stdout

    def send_text(self, surface: str, text: str) -> None:
        self._run(
            self._scoped(["send", "--surface", surface, "--", text]),
            display_args=self._scoped(
                ["send", "--surface", surface, "--", "<payload>"]
            ),
        )

    def send_enter(self, surface: str) -> None:
        self._run(
            self._scoped(["send-key", "--surface", surface, "enter"]),
            display_args=self._scoped(["send-key", "--surface", surface, "enter"]),
        )

    def _scoped(self, args: list[str]) -> list[str]:
        if not self.workspace:
            return args
        return [
            args[0],
            "--workspace",
            self.workspace,
            *args[1:],
        ]

    def _run(
        self, args: list[str], *, display_args: list[str]
    ) -> subprocess.CompletedProcess[str]:
        command = [self.executable, *args]
        try:
            result = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=CMUX_COMMAND_TIMEOUT_SECONDS,
            )
        except FileNotFoundError as exc:
            raise CmuxCommandError(
                "cmux executable not found. Install cmux or use --input-file for dry runs."
            ) from exc
        except subprocess.TimeoutExpired as exc:
            command_text = " ".join([self.executable, *display_args])
            raise CmuxCommandError(
                f"{command_text} timed out after {CMUX_COMMAND_TIMEOUT_SECONDS} seconds."
            ) from exc

        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            command_text = " ".join([self.executable, *display_args])
            if detail:
                raise CmuxCommandError(
                    f"{command_text} failed with exit code {result.returncode}: {detail}"
                )
            raise CmuxCommandError(
                f"{command_text} failed with exit code {result.returncode}."
            )

        return result


def validate_workspace_ref(workspace: str) -> str:
    if workspace != workspace.strip() or not WORKSPACE_RE.fullmatch(workspace):
        raise CmuxCommandError(
            "cmux workspace must be a ref or ID such as workspace:7 or 7."
        )
    return workspace
