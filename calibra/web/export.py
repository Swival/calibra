"""Static site builder: generates multi-page HTML using the same templates as serve."""

from __future__ import annotations

import json
import shutil
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace

from jinja2 import Environment, FileSystemLoader

from calibra.utils import json_for_html, safe_num
from calibra.web.viewdata import (
    STATIC_DIR,
    TEMPLATES_DIR,
    build_task_cells,
    build_trial_diff,
    build_variant_stats,
    campaign_stats,
    rank_variants,
)

SCHEMA_VERSION = 1


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

    def _root_path_for(self, page_path: Path) -> str:
        """Compute relative root path from a page's location back to the output root."""
        depth = len(page_path.relative_to(self.output_dir).parts) - 1
        if depth <= 0:
            return "."
        return "/".join([".."] * depth)

    def _render_page(self, page_path: Path, template_name: str, context: dict) -> None:
        """Render a template with auto-computed root_path and write to disk."""
        context["root_path"] = self._root_path_for(page_path)
        html = self.env.get_template(template_name).render(**context)
        _write_page(page_path, html)

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
        campaigns = [campaign_stats(d.name, s) for d, s in zip(campaign_dirs, summaries)]
        self._render_page(
            self.output_dir / "index.html",
            "campaigns.html",
            {"campaigns": campaigns},
        )

    def _build_campaign_pages(self, campaign_dir: Path, summary: dict) -> None:
        name = campaign_dir.name
        base = self.output_dir / "campaign" / name
        variants = summary.get("variants", [])
        trials = summary.get("trials", [])

        ranked = rank_variants(variants)
        ranked_summary = {**summary, "variants": ranked}
        stats = campaign_stats(name, summary)
        campaign_obj = SimpleNamespace(**stats)
        self._render_page(
            base / "index.html",
            "campaign.html",
            {
                "campaign": campaign_obj,
                "summary": ranked_summary,
                "variants_json": json_for_html(ranked),
            },
        )

        self._build_task_matrix(base, name, summary)

        trials_by_variant: dict[str, list[dict]] = defaultdict(list)
        for t in trials:
            trials_by_variant[t["variant_label"]].append(t)

        for v in variants:
            label = v["variant_label"]
            self._build_variant_page(base, name, v, trials_by_variant.get(label, []))

        self._build_trial_pages(base, name, campaign_dir)

    def _build_task_matrix(self, base: Path, name: str, summary: dict) -> None:
        trials = summary.get("trials", [])
        variants_list = summary.get("variants", [])
        cells_list, tasks_list, variant_labels = build_task_cells(trials, variants_list)

        self._render_page(
            base / "tasks" / "index.html",
            "tasks.html",
            {
                "campaign_name": name,
                "tasks_list": tasks_list,
                "variant_labels": variant_labels,
                "cells_json": json_for_html(cells_list),
            },
        )

    def _build_variant_page(
        self, base: Path, name: str, variant_agg: dict, trials: list[dict]
    ) -> None:
        label = variant_agg["variant_label"]
        task_stats, failure_counts, tool_agg = build_variant_stats(trials)

        self._render_page(
            base / "variant" / label / "index.html",
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
            },
        )

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

            self._render_page(
                base / "trial" / task / variant / repeat / "index.html",
                "trial.html",
                {
                    "campaign_name": name,
                    "task": task,
                    "variant": variant,
                    "repeat": repeat,
                    "trial": trial_data,
                    "raw_json": raw_text,
                    "error": error,
                },
            )


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


def load_diff_report(path: Path, label: str) -> tuple[dict, str]:
    """Load and validate a trial report JSON file for diffing.

    Returns (parsed_dict, raw_text). Raises ValueError on any validation problem.
    Error messages preserve the wording used by the CLI so existing tests on
    exact text remain stable.
    """
    if not path.exists():
        raise ValueError(f"File {label} not found: {path}")
    if path.suffix.lower() != ".json":
        raise ValueError(f"File {label} is not a .json file: {path}")
    try:
        raw = path.read_text()
        parsed = json.loads(raw)
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
        raise ValueError(f"File {label}: {exc}")
    if not isinstance(parsed, dict):
        raise ValueError(f"File {label} is not a JSON object: {path}")
    return parsed, raw


def export_diff(path_a: Path, path_b: Path, output: Path) -> Path:
    """Export a diff of two trial reports as a single self-contained HTML file.

    Reads both JSON files, computes the diff, inlines all JS/CSS assets, and
    writes the result to *output*. Returns *output*.

    Raises ValueError for invalid input files, FileNotFoundError if the output
    parent directory does not exist, and IsADirectoryError if *output* is an
    existing directory.
    """
    output = output.resolve()
    if output.is_dir():
        raise IsADirectoryError(f"Output path is a directory: {output}")
    if not output.parent.is_dir():
        raise FileNotFoundError(f"Parent directory does not exist: {output.parent}")

    report_a, raw_a = load_diff_report(path_a, "A")
    report_b, raw_b = load_diff_report(path_b, "B")

    label_a = path_a.name
    label_b = path_b.name
    diff = build_trial_diff(report_a, report_b, label_a, label_b)

    inline_tailwind_js = (STATIC_DIR / "vendor" / "tailwindcss-browser-4.2.1.js").read_text()
    inline_htmx_js = (STATIC_DIR / "vendor" / "htmx-2.0.8.min.js").read_text()
    inline_style_css = (STATIC_DIR / "style.css").read_text()

    env = _create_jinja_env()
    html = env.get_template("diff.html").render(
        root_path=".",
        static_export=True,
        inline_assets=True,
        inline_tailwind_js=inline_tailwind_js,
        inline_htmx_js=inline_htmx_js,
        inline_style_css=inline_style_css,
        a=str(path_a),
        b=str(path_b),
        diff=diff,
        trial_a=report_a,
        trial_b=report_b,
        raw_a=raw_a,
        raw_b=raw_b,
        error=None,
    )

    _write_page(output, html)
    return output
