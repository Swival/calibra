"""Failure classification for trial errors."""

from __future__ import annotations

from enum import Enum


class FailureClass(Enum):
    INFRA = "infra"
    PROVIDER = "provider"
    TOOL = "tool"
    TIMEOUT = "timeout"
    TASK = "task"


PROVIDER_PATTERNS = [
    "rate limit",
    "429",
    "503",
    "502",
    "auth",
    "unauthorized",
    "forbidden",
    "connection refused",
]


def classify_failure(
    error: Exception | None,
    report: dict | None,
    timed_out: bool,
    verified: bool | None = None,
) -> str | None:
    if error is None and not timed_out:
        if report and report.get("result", {}).get("outcome") == "error":
            stats = report.get("stats", {})
            if stats.get("tool_calls_failed", 0) > 0:
                return FailureClass.TOOL.value
            return FailureClass.TASK.value
        if report and report.get("result", {}).get("outcome") == "exhausted":
            return FailureClass.TASK.value
        if verified is False:
            return FailureClass.TASK.value
        return None

    if timed_out:
        return FailureClass.TIMEOUT.value

    if error is not None:
        if isinstance(error, (OSError, PermissionError)):
            return FailureClass.INFRA.value

        msg = str(error).lower()
        for pattern in PROVIDER_PATTERNS:
            if pattern in msg:
                return FailureClass.PROVIDER.value

    return FailureClass.TASK.value
