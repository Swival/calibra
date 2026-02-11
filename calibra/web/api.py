"""JSON API endpoints."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request

from calibra.web.security import ResultsDir, validate_path, validate_segment

router = APIRouter(prefix="/api")


@router.get("/campaigns")
def list_campaigns(request: Request):
    cache = request.app.state.cache
    result = []
    for name, idx in sorted(cache.campaigns.items()):
        result.append(
            {
                "name": idx.name,
                "n_variants": idx.n_variants,
                "n_tasks": idx.n_tasks,
                "n_trials": idx.n_trials,
                "pass_rate": idx.pass_rate,
                "latest": (
                    datetime.fromtimestamp(idx.latest_mtime, tz=timezone.utc).isoformat()
                    if idx.latest_mtime
                    else None
                ),
            }
        )
    return result


@router.get("/campaign/{name}")
def get_campaign(name: str, results_dir: ResultsDir):
    validate_segment(name, "campaign name")
    summary_path = validate_path(results_dir, name, "summary.json")
    return json.loads(summary_path.read_text())


@router.get("/campaign/{name}/heatmap")
def get_heatmap(name: str, request: Request, results_dir: ResultsDir):
    validate_segment(name, "campaign name")
    cache = request.app.state.cache
    idx = cache.get(name)
    if idx is None or idx.summary is None:
        raise HTTPException(status_code=404, detail="Campaign not found or not analyzed")

    trials = idx.summary.get("trials", [])
    cells: dict[tuple[str, str], dict] = {}
    for t in trials:
        key = (t["task"], t["variant_label"])
        if key not in cells:
            cells[key] = {"task": t["task"], "variant": t["variant_label"], "n": 0, "passes": 0}
        cells[key]["n"] += 1
        if t.get("verified") is True:
            cells[key]["passes"] += 1

    result = []
    for cell in cells.values():
        cell["pass_rate"] = round(cell["passes"] / cell["n"], 4) if cell["n"] > 0 else 0.0
        result.append(cell)
    return result


@router.get("/campaign/{name}/trial/{task}/{variant}/{repeat}")
def get_trial(name: str, task: str, variant: str, repeat: str, results_dir: ResultsDir):
    validate_segment(name, "campaign name")
    validate_segment(task, "task")
    validate_segment(variant, "variant")
    validate_segment(repeat, "repeat")
    filename = f"{variant}_{repeat}.json"
    trial_path = validate_path(results_dir, name, task, filename)
    return json.loads(trial_path.read_text())


@router.get("/compare")
def compare(a: str, b: str, results_dir: ResultsDir):
    validate_segment(a, "campaign A")
    validate_segment(b, "campaign B")
    validate_path(results_dir, a)
    validate_path(results_dir, b)

    from calibra.compare import compute_comparison
    from dataclasses import asdict

    result = compute_comparison(results_dir / a, results_dir / b)
    if result is None:
        raise HTTPException(status_code=404, detail="No common variants found")
    return asdict(result)


@router.post("/reload")
def reload_cache(request: Request):
    request.app.state.cache.reload()
    return {"status": "ok", "campaigns": len(request.app.state.cache.campaigns)}
