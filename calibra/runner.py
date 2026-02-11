"""Trial runner: workspace setup, execution, orchestration."""

from __future__ import annotations

import copy
import hashlib
import json
import shutil
import subprocess
import tempfile
import threading
import time
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

from calibra.config import Campaign, ConfigError
from calibra.failure import classify_failure
from calibra.matrix import Variant
from calibra.tasks import Task


def _deep_merge(base: dict, override: dict) -> dict:
    merged = {**base}
    for key, val in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(val, dict):
            merged[key] = _deep_merge(merged[key], val)
        else:
            merged[key] = val
    return merged


def _resolve_yolo(session_opts: dict) -> tuple[bool, dict]:
    opts = copy.deepcopy(session_opts)
    has_allowlist = "allowed_commands" in opts
    if has_allowlist and "yolo" not in opts:
        yolo = False
    else:
        yolo = opts.pop("yolo", True)
    return yolo, opts


def _validate_merged_options(opts: dict, model_variants: list[Variant]):
    if "allowed_commands" in opts and opts.get("yolo") is True:
        warnings.warn(
            "Session options contain both 'allowed_commands' and 'yolo=true'; "
            "yolo overrides the command allowlist",
            stacklevel=2,
        )

    if opts.get("no_skills") is True:
        has_nonempty_skills = any(v.skills.skills_dirs for v in model_variants)
        if has_nonempty_skills:
            raise ConfigError(
                "Merged session options have 'no_skills=true' but some variants "
                "for this model have non-empty skills_dirs"
            )


@dataclass
class TrialSpec:
    task: Task
    variant: Variant
    repeat_index: int
    trial_seed: int


@dataclass
class TrialResult:
    spec: TrialSpec
    report: dict | None
    verified: bool | None
    failure_class: str | None
    wall_time_s: float
    error_message: str | None
    attempts: int


def compute_trial_seed(base_seed: int, task_name: str, variant_label: str, repeat: int) -> int:
    h = hashlib.sha256()
    h.update(f"{base_seed}:{task_name}:{variant_label}:{repeat}".encode())
    return int.from_bytes(h.digest()[:4], "big")


def trial_report_path(output_dir: Path, spec: TrialSpec) -> Path:
    return output_dir / spec.task.name / f"{spec.variant.label}_{spec.repeat_index}.json"


def build_all_specs(
    campaign: Campaign, variants: list[Variant], tasks: list[Task]
) -> list[TrialSpec]:
    specs = []
    for task in tasks:
        for variant in variants:
            for r in range(campaign.repeat):
                seed = compute_trial_seed(campaign.seed, task.name, variant.label, r)
                specs.append(TrialSpec(task=task, variant=variant, repeat_index=r, trial_seed=seed))
    return specs


def result_exists(output_dir: Path, spec: TrialSpec, config_hash: str) -> bool:
    path = trial_report_path(output_dir, spec)
    try:
        with open(path) as f:
            report = json.load(f)
        cal = report.get("calibra", {})
        return (
            cal.get("config_hash") == config_hash
            and cal.get("task") == spec.task.name
            and cal.get("variant") == spec.variant.label
            and cal.get("repeat") == spec.repeat_index
        )
    except (json.JSONDecodeError, OSError):
        return False


def setup_workspace(spec: TrialSpec, variant: Variant) -> Path:
    tmpdir = Path(tempfile.mkdtemp(prefix=f"calibra_{spec.task.name}_"))
    shutil.copytree(spec.task.env_dir, tmpdir, dirs_exist_ok=True)

    if variant.environment.overlay:
        overlay = Path(variant.environment.overlay)
        if overlay.is_dir():
            shutil.copytree(overlay, tmpdir, dirs_exist_ok=True)

    if variant.agent_instructions.agents_md:
        agents_md = Path(variant.agent_instructions.agents_md)
        if agents_md.is_file():
            shutil.copy2(agents_md, tmpdir / "AGENTS.md")

    return tmpdir


def run_verify(verify_script: Path, workdir: Path) -> bool:
    try:
        result = subprocess.run(
            [str(verify_script)],
            cwd=str(workdir),
            timeout=30,
            capture_output=True,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, OSError):
        return False


def _load_mcp_config(path: Path) -> dict | None:
    if path.suffix == ".toml":
        import tomllib

        with open(path, "rb") as f:
            return tomllib.load(f)
    else:
        with open(path) as f:
            return json.load(f)


def run_single_trial(
    spec: TrialSpec,
    campaign: Campaign,
    *,
    keep_workdirs: bool = False,
    merged_session_opts: dict | None = None,
) -> TrialResult:
    tmpdir = setup_workspace(spec, spec.variant)
    start = time.monotonic()
    timed_out = False

    try:
        from swival import Session

        mcp_servers = None
        if spec.variant.mcp.config:
            mcp_config_path = Path(spec.variant.mcp.config)
            if mcp_config_path.exists():
                mcp_servers = _load_mcp_config(mcp_config_path)

        skills_dir = spec.variant.skills.skills_dirs or None

        yolo, session_opts = _resolve_yolo(merged_session_opts or {})

        session = Session(
            base_dir=str(tmpdir),
            provider=spec.variant.model.provider,
            model=spec.variant.model.model,
            max_turns=campaign.max_turns,
            seed=spec.trial_seed,
            yolo=yolo,
            history=False,
            skills_dir=skills_dir,
            mcp_servers=mcp_servers,
            **session_opts,
        )

        container: list = []
        error_container: list = []

        def _run_session():
            try:
                container.append(session.run(spec.task.prompt, report=True))
            except Exception as exc:
                error_container.append(exc)

        with session:
            worker = threading.Thread(target=_run_session, daemon=True)
            worker.start()
            worker.join(timeout=campaign.timeout_s)
            if worker.is_alive():
                timed_out = True
                raise TimeoutError(f"Wall-clock timeout after {campaign.timeout_s}s")
            if error_container:
                raise error_container[0]
            result = container[0]

        wall_time = time.monotonic() - start
        report = result.report if result.report else None

        verified = None
        if spec.task.verify_script:
            verified = run_verify(spec.task.verify_script, tmpdir)

        failure_class = classify_failure(None, report, False, verified=verified)

        return TrialResult(
            spec=spec,
            report=report,
            verified=verified,
            failure_class=failure_class,
            wall_time_s=round(wall_time, 3),
            error_message=None,
            attempts=1,
        )

    except Exception as e:
        wall_time = time.monotonic() - start
        failure_class = classify_failure(e, None, timed_out)
        return TrialResult(
            spec=spec,
            report=None,
            verified=None,
            failure_class=failure_class,
            wall_time_s=round(wall_time, 3),
            error_message=str(e),
            attempts=1,
        )

    finally:
        if not keep_workdirs:
            shutil.rmtree(tmpdir, ignore_errors=True)


def run_trial_with_retry(
    spec: TrialSpec,
    campaign: Campaign,
    *,
    keep_workdirs: bool = False,
    merged_session_opts: dict | None = None,
) -> TrialResult:
    attempts: list[TrialResult] = []

    while True:
        attempt_index = len(attempts)
        if attempt_index > 0:
            backoff = min(
                campaign.retry.backoff_base_s * (2 ** (attempt_index - 1)),
                campaign.retry.backoff_max_s,
            )
            time.sleep(backoff)

        result = run_single_trial(
            spec,
            campaign,
            keep_workdirs=keep_workdirs,
            merged_session_opts=merged_session_opts,
        )
        attempts.append(result)

        if result.failure_class is None:
            break

        max_retries = getattr(campaign.retry, result.failure_class, 0)
        if attempt_index >= max_retries:
            break

    final = attempts[-1]
    final.attempts = len(attempts)
    return final


def write_trial_report(output_dir: Path, result: TrialResult, campaign: Campaign):
    path = trial_report_path(output_dir, result.spec)
    path.parent.mkdir(parents=True, exist_ok=True)

    report = result.report or {}
    report["calibra"] = {
        "config_hash": campaign.config_hash,
        "task": result.spec.task.name,
        "variant": result.spec.variant.label,
        "repeat": result.spec.repeat_index,
        "trial_seed": result.spec.trial_seed,
    }
    if result.verified is not None:
        report["calibra"]["verified"] = result.verified
    if result.failure_class:
        report["calibra"]["failure_class"] = result.failure_class
    if result.error_message:
        report["calibra"]["error_message"] = result.error_message
    report["calibra"]["wall_time_s"] = result.wall_time_s
    report["calibra"]["attempts"] = result.attempts

    with open(path, "w") as f:
        json.dump(report, f, indent=2)
        f.write("\n")


def run_campaign(
    campaign: Campaign,
    variants: list[Variant],
    tasks: list[Task],
    workers: int = 1,
    output_dir: str = "results",
    resume: bool = False,
    keep_workdirs: bool = False,
    config_path: str | None = None,
):
    from calibra.budget import BudgetTracker

    out = Path(output_dir) / campaign.name
    out.mkdir(parents=True, exist_ok=True)

    specs = build_all_specs(campaign, variants, tasks)

    if resume:
        specs = [s for s in specs if not result_exists(out, s, campaign.config_hash)]

    if not specs:
        print("No trials to run.")
        return

    merged_session_opts: dict[str, dict] = {}
    for model in campaign.models:
        opts = _deep_merge(campaign.session_options, model.session_options)
        model_variants = [v for v in variants if v.model.label == model.label]
        _validate_merged_options(opts, model_variants)
        merged_session_opts[model.label] = opts

    print(f"Running {len(specs)} trials with {workers} worker(s)...")

    from calibra.prices import load_prices, validate_price_coverage

    prices = load_prices(Path(config_path)) if config_path else {}
    if campaign.budget.require_price_coverage:
        validate_price_coverage(campaign, prices)
    budget_tracker = BudgetTracker(campaign.budget, prices)

    from concurrent.futures import CancelledError

    results = []
    budget_exceeded = False
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(
                run_trial_with_retry,
                spec,
                campaign,
                keep_workdirs=keep_workdirs,
                merged_session_opts=merged_session_opts.get(spec.variant.model.label),
            ): spec
            for spec in specs
        }
        for future in as_completed(futures):
            try:
                result = future.result()
            except CancelledError:
                continue
            results.append(result)
            write_trial_report(out, result, campaign)

            status = "PASS" if result.failure_class is None else result.failure_class.upper()
            print(
                f"  [{status}] {result.spec.task.name} / {result.spec.variant.label} #{result.spec.repeat_index}"
            )

            if not budget_exceeded and budget_tracker.update(result):
                budget_exceeded = True
                print(f"Budget exceeded: {budget_tracker.reason}")
                for f in futures:
                    f.cancel()

    summary = {
        "campaign": campaign.name,
        "config_hash": campaign.config_hash,
        "total_trials": len(results),
        "passed": sum(1 for r in results if r.failure_class is None),
        "failed": sum(1 for r in results if r.failure_class is not None),
    }
    summary_path = out / "summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)
        f.write("\n")
    print(f"Summary written to {summary_path}")
