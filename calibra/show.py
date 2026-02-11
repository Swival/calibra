"""Pretty-print a single trial report."""

from __future__ import annotations

import json
from pathlib import Path


def show_report(report_path: str | Path):
    path = Path(report_path)
    with open(path) as f:
        report = json.load(f)

    try:
        from rich.console import Console
        from rich.table import Table

        console = Console()

        cal = report.get("calibra", {})
        result = report.get("result", {})
        stats = report.get("stats", {})

        console.print(f"\n[bold]Trial Report[/bold]: {path.name}")
        console.print(f"  Task: {cal.get('task', 'unknown')}")
        console.print(f"  Variant: {cal.get('variant', 'unknown')}")
        console.print(f"  Outcome: {result.get('outcome', 'unknown')}")
        if cal.get("verified") is not None:
            console.print(f"  Verified: {cal['verified']}")
        console.print(f"  Wall time: {cal.get('wall_time_s', 0):.1f}s")
        console.print()

        table = Table(title="Stats")
        table.add_column("Metric")
        table.add_column("Value", justify="right")
        table.add_row("Turns", str(stats.get("turns", 0)))
        table.add_row("LLM calls", str(stats.get("llm_calls", 0)))
        table.add_row("Tool calls", str(stats.get("tool_calls_total", 0)))
        table.add_row("Tool failures", str(stats.get("tool_calls_failed", 0)))
        table.add_row("LLM time", f"{stats.get('total_llm_time_s', 0):.1f}s")
        table.add_row("Tool time", f"{stats.get('total_tool_time_s', 0):.1f}s")
        table.add_row("Compactions", str(stats.get("compactions", 0)))
        console.print(table)

        tools = stats.get("tool_calls_by_name", {})
        if tools:
            ttable = Table(title="Tool Usage")
            ttable.add_column("Tool")
            ttable.add_column("Succeeded", justify="right")
            ttable.add_column("Failed", justify="right")
            for name, counts in sorted(tools.items()):
                ttable.add_row(name, str(counts.get("succeeded", 0)), str(counts.get("failed", 0)))
            console.print(ttable)

    except ImportError:
        print(json.dumps(report, indent=2))
