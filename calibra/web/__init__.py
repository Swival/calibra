"""Calibra web interface: FastAPI app factory."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from calibra.compare import compute_comparison
from calibra.utils import json_for_html, safe_num
from calibra.web.api import router as api_router
from calibra.web.cache import ResultCache
from calibra.web.security import validate_path, validate_segment
from calibra.web.viewdata import (
    STATIC_DIR,
    TEMPLATES_DIR,
    build_task_cells,
    build_variant_stats,
    rank_variants,
)


def create_app(results_dir: Path) -> FastAPI:
    results_dir = results_dir.resolve()
    if (results_dir / "summary.json").is_file():
        results_dir = results_dir.parent

    app = FastAPI(title="Calibra", docs_url=None, redoc_url=None)

    app.state.results_dir = results_dir
    app.state.templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    app.state.templates.env.filters["num"] = safe_num
    app.state.templates.env.globals["root_path"] = ""

    cache = ResultCache(results_dir=results_dir.resolve())
    cache.scan()
    app.state.cache = cache

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    app.include_router(api_router)

    @app.get("/")
    def home(request: Request):
        campaigns = []
        for name, idx in sorted(app.state.cache.campaigns.items()):
            campaigns.append(
                {
                    "name": idx.name,
                    "n_variants": idx.n_variants,
                    "n_tasks": idx.n_tasks,
                    "n_trials": idx.n_trials,
                    "pass_rate": idx.pass_rate,
                    "latest_mtime": idx.latest_mtime,
                }
            )
        return app.state.templates.TemplateResponse(
            request, "campaigns.html", {"campaigns": campaigns}
        )

    @app.get("/campaign/{name}")
    def campaign_detail(name: str, request: Request):
        validate_segment(name, "campaign name")
        idx = app.state.cache.get(name)
        if idx is None:
            raise HTTPException(status_code=404, detail="Campaign not found")
        summary = idx.summary
        variants_json = ""
        if summary and "variants" in summary:
            ranked = rank_variants(summary["variants"])
            summary = {**summary, "variants": ranked}
            variants_json = json_for_html(ranked)
        return app.state.templates.TemplateResponse(
            request,
            "campaign.html",
            {"campaign": idx, "summary": summary, "variants_json": variants_json},
        )

    @app.get("/campaign/{name}/tasks")
    def task_matrix(name: str, request: Request):
        validate_segment(name, "campaign name")
        idx = app.state.cache.get(name)
        if idx is None:
            raise HTTPException(status_code=404, detail="Campaign not found")
        summary = idx.summary
        if not summary:
            raise HTTPException(status_code=404, detail="No analysis data")

        trials = summary.get("trials", [])
        variants_list = summary.get("variants", [])
        cells_list, tasks_list, variant_labels = build_task_cells(trials, variants_list)

        return app.state.templates.TemplateResponse(
            request,
            "tasks.html",
            {
                "campaign_name": name,
                "tasks_list": tasks_list,
                "variant_labels": variant_labels,
                "cells_json": json_for_html(cells_list),
            },
        )

    @app.get("/campaign/{name}/variant/{label}")
    def variant_detail(name: str, label: str, request: Request, task: str | None = None):
        validate_segment(name, "campaign name")
        validate_segment(label, "variant label")
        idx = app.state.cache.get(name)
        if idx is None:
            raise HTTPException(status_code=404, detail="Campaign not found")
        summary = idx.summary
        if not summary:
            raise HTTPException(status_code=404, detail="No analysis data")

        variant_agg = None
        for v in summary.get("variants", []):
            if v["variant_label"] == label:
                variant_agg = v
                break
        if variant_agg is None:
            raise HTTPException(status_code=404, detail="Variant not found")

        trials = [t for t in summary.get("trials", []) if t["variant_label"] == label]
        task_stats, failure_counts, tool_agg = build_variant_stats(trials)

        dimensions = label.split("_")

        task_stats_json = json_for_html(task_stats)
        failure_json = json_for_html(failure_counts)
        tool_json = json_for_html(tool_agg)

        filtered_trials = trials
        if task:
            filtered_trials = [t for t in trials if t["task"] == task]

        return app.state.templates.TemplateResponse(
            request,
            "variant.html",
            {
                "campaign_name": name,
                "label": label,
                "dimensions": dimensions,
                "variant_agg": variant_agg,
                "task_stats": task_stats,
                "task_stats_json": task_stats_json,
                "failure_counts": failure_counts,
                "failure_json": failure_json,
                "tool_agg": tool_agg,
                "tool_json": tool_json,
                "trials": filtered_trials,
                "task_filter": task,
            },
        )

    @app.get("/campaign/{name}/trial/{task}/{variant}/{repeat}")
    def trial_inspector(name: str, task: str, variant: str, repeat: str, request: Request):
        validate_segment(name, "campaign name")
        validate_segment(task, "task")
        validate_segment(variant, "variant")
        validate_segment(repeat, "repeat")
        filename = f"{variant}_{repeat}.json"
        trial_path = validate_path(app.state.results_dir, name, task, filename)
        try:
            raw_text = trial_path.read_text()
            trial_data = json.loads(raw_text)
        except (json.JSONDecodeError, OSError, UnicodeDecodeError) as exc:
            return app.state.templates.TemplateResponse(
                request,
                "trial.html",
                {
                    "campaign_name": name,
                    "task": task,
                    "variant": variant,
                    "repeat": repeat,
                    "trial": {},
                    "raw_json": "",
                    "error": f"Failed to load trial data: {exc}",
                },
            )
        raw_json = raw_text
        return app.state.templates.TemplateResponse(
            request,
            "trial.html",
            {
                "campaign_name": name,
                "task": task,
                "variant": variant,
                "repeat": repeat,
                "trial": trial_data,
                "raw_json": raw_json,
                "error": None,
            },
        )

    @app.get("/compare")
    def compare_page(request: Request, a: str | None = None, b: str | None = None):
        campaign_names = sorted(app.state.cache.campaigns.keys())
        results_dir = app.state.results_dir
        comparison = None
        comparison_json = ""
        error = None

        if a and b:
            validate_segment(a, "campaign A")
            validate_segment(b, "campaign B")
            if app.state.cache.get(a) is None:
                raise HTTPException(status_code=404, detail="Campaign A not found")
            if app.state.cache.get(b) is None:
                raise HTTPException(status_code=404, detail="Campaign B not found")
            result = compute_comparison(results_dir / a, results_dir / b)
            if result is None:
                error = "No common variants found"
            else:
                comparison = asdict(result)
                comparison_json = json_for_html(comparison["variants"])

        return app.state.templates.TemplateResponse(
            request,
            "compare.html",
            {
                "campaign_names": campaign_names,
                "a": a,
                "b": b,
                "comparison": comparison,
                "comparison_json": comparison_json,
                "error": error,
            },
        )

    return app
