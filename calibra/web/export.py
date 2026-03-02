"""Static site builder: generates multi-page HTML using the same templates as serve."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from types import SimpleNamespace

from jinja2 import Environment, FileSystemLoader

from calibra.utils import json_for_html, safe_num, weighted_pass_rate

SCHEMA_VERSION = 1
TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"


def _root_path(depth: int) -> str:
    """Relative path from a page at *depth* directories below root back to root."""
    if depth == 0:
        return "."
    return "/".join([".."] * depth)


def _stat_mean(obj: object) -> float:
    if isinstance(obj, dict):
        return safe_num(obj.get("mean", 0))
    return 0.0


def _rank_variants(variants: list[dict]) -> list[dict]:
    def _key(v: dict) -> tuple:
        return (
            -safe_num(v.get("pass_rate", 0)),
            _stat_mean(v.get("prompt_tokens_est")),
            _stat_mean(v.get("turns")),
        )

    return sorted(variants, key=_key)


def _load_summary(campaign_dir: Path) -> dict:
    """Load and validate summary.json from a campaign directory."""
    summary_path = campaign_dir / "summary.json"
    if not summary_path.is_file():
        raise FileNotFoundError(f"No summary.json in {campaign_dir}. Run 'calibra analyze' first.")
    try:
        summary = json.loads(summary_path.read_text())
    except json.JSONDecodeError as e:
        raise ValueError(
            f"Corrupt summary.json in {campaign_dir}: {e}. "
            f"Expected schema version {SCHEMA_VERSION}."
        )
    if not isinstance(summary.get("variants"), list) or not isinstance(summary.get("trials"), list):
        raise ValueError(
            f"Invalid summary.json structure in {campaign_dir}: "
            f"expected 'variants' and 'trials' arrays. "
            f"Expected schema version {SCHEMA_VERSION}."
        )
    return summary


def _create_jinja_env() -> Environment:
    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))
    env.filters["num"] = safe_num
    return env


def _write_page(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


class _SiteBuilder:
    """Renders all pages for a static export using the same Jinja2 templates as serve."""

    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.env = _create_jinja_env()

    def render(self, template_name: str, context: dict) -> str:
        return self.env.get_template(template_name).render(**context)

    def build(self, campaign_dirs: list[Path], summaries: list[dict]) -> None:
        self._copy_static()
        self._build_campaigns_page(campaign_dirs, summaries)
        for cdir, summary in zip(campaign_dirs, summaries):
            self._build_campaign_pages(cdir, summary)

    def _copy_static(self) -> None:
        dest = self.output_dir / "static"
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(STATIC_DIR, dest)

    def _build_campaigns_page(self, campaign_dirs: list[Path], summaries: list[dict]) -> None:
        campaigns = []
        for d, summary in zip(campaign_dirs, summaries):
            variants = summary.get("variants", [])
            trials = summary.get("trials", [])
            campaigns.append(
                {
                    "name": d.name,
                    "n_variants": len(variants),
                    "n_tasks": len({t["task"] for t in trials}),
                    "n_trials": len(trials),
                    "pass_rate": weighted_pass_rate(variants),
                }
            )
        html = self.render("campaigns.html", {"campaigns": campaigns, "root_path": "."})
        _write_page(self.output_dir / "index.html", html)

    def _build_campaign_pages(self, campaign_dir: Path, summary: dict) -> None:
        name = campaign_dir.name
        base = self.output_dir / "campaign" / name
        variants = summary.get("variants", [])
        trials = summary.get("trials", [])

        ranked = _rank_variants(variants)
        ranked_summary = {**summary, "variants": ranked}
        campaign_obj = SimpleNamespace(
            name=name,
            n_variants=len(variants),
            n_tasks=len({t["task"] for t in trials}),
            n_trials=len(trials),
            pass_rate=weighted_pass_rate(variants),
        )
        html = self.render(
            "campaign.html",
            {
                "campaign": campaign_obj,
                "summary": ranked_summary,
                "variants_json": json_for_html(ranked),
                "root_path": _root_path(2),
            },
        )
        _write_page(base / "index.html", html)

        self._build_task_matrix(base, name, summary)

        for v in variants:
            self._build_variant_page(base, name, v, summary)

        self._build_trial_pages(base, name, campaign_dir)

    def _build_task_matrix(self, base: Path, name: str, summary: dict) -> None:
        trials = summary.get("trials", [])
        variants_list = summary.get("variants", [])
        variant_labels = [v["variant_label"] for v in variants_list]

        cells: dict[tuple[str, str], dict] = {}
        task_names: set[str] = set()
        for t in trials:
            task_name = t["task"]
            task_names.add(task_name)
            key = (task_name, t["variant_label"])
            if key not in cells:
                cells[key] = {
                    "task": task_name,
                    "variant": t["variant_label"],
                    "n": 0,
                    "passes": 0,
                    "turns_sum": 0.0,
                    "tokens_sum": 0.0,
                }
            cells[key]["n"] += 1
            if t.get("verified") is True:
                cells[key]["passes"] += 1
            cells[key]["turns_sum"] += safe_num(t.get("turns", 0))
            cells[key]["tokens_sum"] += safe_num(t.get("prompt_tokens_est", 0))

        for cell in cells.values():
            n = cell["n"]
            cell["pass_rate"] = round(cell["passes"] / n, 4) if n > 0 else 0.0
            cell["mean_turns"] = round(cell["turns_sum"] / n, 1) if n > 0 else 0.0
            cell["mean_tokens"] = round(cell["tokens_sum"] / n, 0) if n > 0 else 0.0

        html = self.render(
            "tasks.html",
            {
                "campaign_name": name,
                "tasks_list": sorted(task_names),
                "variant_labels": variant_labels,
                "cells_json": json_for_html(list(cells.values())),
                "root_path": _root_path(3),
            },
        )
        _write_page(base / "tasks" / "index.html", html)

    def _build_variant_page(self, base: Path, name: str, variant_agg: dict, summary: dict) -> None:
        label = variant_agg["variant_label"]
        trials = [t for t in summary.get("trials", []) if t["variant_label"] == label]

        per_task: dict[str, dict] = {}
        failure_counts: dict[str, int] = {}
        tool_agg: dict[str, dict[str, int]] = {}
        for t in trials:
            tk = t["task"]
            if tk not in per_task:
                per_task[tk] = {
                    "task": tk,
                    "n": 0,
                    "passes": 0,
                    "outcomes": [],
                    "turns_vals": [],
                    "tokens_vals": [],
                    "wall_time_vals": [],
                }
            pt = per_task[tk]
            pt["n"] += 1
            if t.get("verified") is True:
                pt["passes"] += 1
            pt["outcomes"].append(t.get("outcome", "unknown"))
            pt["turns_vals"].append(safe_num(t.get("turns", 0)))
            pt["tokens_vals"].append(safe_num(t.get("prompt_tokens_est", 0)))
            pt["wall_time_vals"].append(safe_num(t.get("wall_time_s", 0)))

            fc = t.get("failure_class")
            if fc:
                failure_counts[fc] = failure_counts.get(fc, 0) + 1
            for tool_name, counts in t.get("tool_calls_by_name", {}).items():
                if tool_name not in tool_agg:
                    tool_agg[tool_name] = {"succeeded": 0, "failed": 0}
                if isinstance(counts, dict):
                    tool_agg[tool_name]["succeeded"] += counts.get("succeeded", 0)
                    tool_agg[tool_name]["failed"] += counts.get("failed", 0)

        task_stats = []
        for tk, pt in sorted(per_task.items()):
            n = pt["n"]
            task_stats.append(
                {
                    "task": tk,
                    "n": n,
                    "passes": pt["passes"],
                    "pass_rate": round(pt["passes"] / n, 4) if n > 0 else 0.0,
                    "outcomes": pt["outcomes"],
                    "mean_turns": round(sum(pt["turns_vals"]) / n, 1) if n > 0 else 0.0,
                    "mean_tokens": round(sum(pt["tokens_vals"]) / n, 0) if n > 0 else 0.0,
                    "mean_wall_time": (round(sum(pt["wall_time_vals"]) / n, 1) if n > 0 else 0.0),
                    "turns_vals": pt["turns_vals"],
                }
            )

        html = self.render(
            "variant.html",
            {
                "campaign_name": name,
                "label": label,
                "dimensions": label.split("_"),
                "variant_agg": variant_agg,
                "task_stats": task_stats,
                "task_stats_json": json_for_html(task_stats),
                "failure_counts": failure_counts,
                "failure_json": json_for_html(failure_counts),
                "tool_agg": tool_agg,
                "tool_json": json_for_html(tool_agg),
                "trials": trials,
                "task_filter": None,
                "root_path": _root_path(4),
            },
        )
        _write_page(base / "variant" / label / "index.html", html)

    def _build_trial_pages(self, base: Path, name: str, campaign_dir: Path) -> None:
        trial_files = sorted(p for p in campaign_dir.rglob("*.json") if p.name != "summary.json")
        for trial_path in trial_files:
            task = trial_path.parent.name
            parts = trial_path.stem.rsplit("_", 1)
            if len(parts) != 2:
                continue
            variant, repeat = parts

            try:
                raw_text = trial_path.read_text()
                trial_data = json.loads(raw_text)
                error = None
            except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
                trial_data = {}
                raw_text = ""
                error = f"Failed to load trial data: {exc}"

            html = self.render(
                "trial.html",
                {
                    "campaign_name": name,
                    "task": task,
                    "variant": variant,
                    "repeat": repeat,
                    "trial": trial_data,
                    "raw_json": raw_text,
                    "error": error,
                    "root_path": _root_path(6),
                },
            )
            _write_page(base / "trial" / task / variant / repeat / "index.html", html)


def build_static_site(results_dir: Path, output_dir: Path | None = None) -> Path:
    """Build a multi-page static site mirroring the web dashboard.

    Accepts either a results root (parent of campaign dirs) or a single campaign
    directory that contains summary.json directly. Returns the output directory.
    """
    results_dir = results_dir.resolve()
    if not results_dir.is_dir():
        raise FileNotFoundError(f"Results directory not found: {results_dir}")

    if (results_dir / "summary.json").is_file():
        out = output_dir if output_dir is not None else results_dir / "web"
        return build_single_campaign(results_dir, output_dir=out)

    campaign_dirs = sorted(
        d
        for d in results_dir.iterdir()
        if d.is_dir() and not d.name.startswith(".") and (d / "summary.json").is_file()
    )
    if not campaign_dirs:
        raise FileNotFoundError(
            f"No analyzed campaigns found in {results_dir}. Run 'calibra analyze' first."
        )

    summaries = [_load_summary(d) for d in campaign_dirs]
    out = output_dir if output_dir is not None else results_dir / "web"
    builder = _SiteBuilder(out)
    builder.build(campaign_dirs, summaries)
    return out


def build_single_campaign(campaign_dir: Path, output_dir: Path | None = None) -> Path:
    """Build a static site for a single campaign directory."""
    campaign_dir = campaign_dir.resolve()
    summary = _load_summary(campaign_dir)
    out = output_dir if output_dir is not None else campaign_dir / "web"
    builder = _SiteBuilder(out)
    builder.build([campaign_dir], [summary])
    return out
