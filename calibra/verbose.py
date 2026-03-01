"""Verbose formatting for trial output."""

from __future__ import annotations


def _fmt_tokens(n: int | float) -> str:
    if n >= 1000:
        return f"{n / 1000:.1f}k"
    return str(int(n))


def _extract_stats(report: dict) -> tuple[int, int, int]:
    """Extract (turns, tool_calls, total_tokens) from a report."""
    stats = report.get("stats", {})
    turns = stats.get("turns", 0)
    tool_calls = stats.get("tool_calls_total", 0)
    total_tokens = sum(e.get("prompt_tokens_est", 0) for e in report.get("timeline", []))
    return turns, tool_calls, total_tokens


def format_progress_header(total: int, workers: int, verbose: bool) -> str:
    suffix = " (verbose)" if verbose else ""
    return f"Running {total} trials with {workers} worker(s){suffix}..."


def format_trial_line(
    status: str,
    task_name: str,
    variant_label: str,
    repeat_index: int,
    wall_time_s: float,
    report: dict | None,
    completed: int,
    total: int,
    passed: int,
    failed: int,
) -> str:
    parts = [
        f"  [{completed}/{total}]",
        f"[{status}]",
        f"{task_name} / {variant_label} #{repeat_index}",
    ]
    line = " ".join(parts)

    if report:
        turns, tool_calls, total_tokens = _extract_stats(report)
        line += f"  ({wall_time_s:.1f}s | {turns} turns | {tool_calls} tools | {_fmt_tokens(total_tokens)} tok)"
    else:
        line += f"  ({wall_time_s:.1f}s)"

    line += f"  [{passed}P/{failed}F]"
    return line


def format_trial_detail(report: dict | None, stderr_capture: str | None = None) -> str:
    if not report:
        if stderr_capture and stderr_capture.strip():
            return f"    stderr: {stderr_capture.strip()[:200]}"
        return ""

    lines: list[str] = []
    stats = report.get("stats", {})
    result = report.get("result", {})

    outcome = result.get("outcome", "unknown")
    llm_time = stats.get("total_llm_time_s", 0)
    tool_time = stats.get("total_tool_time_s", 0)
    compactions = stats.get("compactions", 0)
    lines.append(
        f"    outcome={outcome}  llm_time={llm_time:.1f}s  tool_time={tool_time:.1f}s  compactions={compactions}"
    )

    for event in report.get("timeline", []):
        etype = event.get("type")
        turn = event.get("turn", "?")
        if etype == "llm_call":
            dur = event.get("duration_s", 0)
            tokens = event.get("prompt_tokens_est", 0)
            finish = event.get("finish_reason", "?")
            lines.append(f"    turn {turn}: LLM {dur:.1f}s  {_fmt_tokens(tokens)} tok  -> {finish}")
        elif etype == "tool_call":
            name = event.get("name", "?")
            dur = event.get("duration_s", 0)
            ok = "[ok]" if event.get("succeeded") else "[FAIL]"
            lines.append(f"    turn {turn}: tool {name}  {dur:.3f}s  {ok}")
        elif etype == "compaction":
            lines.append(f"    turn {turn}: compaction")

    tool_by_name = stats.get("tool_calls_by_name", {})
    if tool_by_name:
        tool_parts = []
        for name, counts in sorted(tool_by_name.items()):
            s = counts.get("succeeded", 0)
            total = s + counts.get("failed", 0)
            tool_parts.append(f"{name}={s}/{total}")
        lines.append(f"    tools: {', '.join(tool_parts)}")

    return "\n".join(lines)
