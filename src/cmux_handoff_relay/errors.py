"""Project-specific exceptions."""


class HandoffRelayError(Exception):
    """Base error for expected relay failures."""


class HandoffParseError(HandoffRelayError):
    """Raised when a handoff block cannot be parsed safely."""


class HandoffConfigError(HandoffRelayError):
    """Raised when relay configuration is missing or invalid."""


class HandoffAuthError(HandoffRelayError):
    """Raised when a handoff block fails relay authorization checks."""


class CmuxCommandError(HandoffRelayError):
    """Raised when a cmux command fails."""


class HandoffAbort(HandoffRelayError):
    """Raised when the user declines to send a payload."""
