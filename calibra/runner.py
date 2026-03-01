"""Trial runner: workspace setup, execution, orchestration."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import signal
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
    stderr_capture: str | None = None


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


def _session_opts_to_cli_args(opts: dict) -> list[str]:
    args = []
    _FLAG_MAP = {
        "yolo": "--yolo",
        "no_skills": "--no-skills",
        "no_instructions": "--no-instructions",
    }
    _VALUE_MAP = {
        "max_output_tokens": "--max-output-tokens",
        "temperature": "--temperature",
        "top_p": "--top-p",
        "api_key": "--api-key",
        "base_url": "--base-url",
        "max_context_tokens": "--max-context-tokens",
        "seed": "--seed",
    }
    _REPEAT_MAP = {
        "skills_dir": "--skills-dir",
        "allowed_dirs": "--add-dir",
        "allowed_dirs_ro": "--add-dir-ro",
    }
    _SKIP = {
        "verbose",
        "history",
        "config_dir",
        "base_dir",
        "provider",
        "model",
        "max_turns",
        "mcp_servers",
    }

    for key, value in opts.items():
        if key in _SKIP:
            continue
        if key in _FLAG_MAP:
            if value:
                args.append(_FLAG_MAP[key])
            continue
        if key == "read_guard":
            if value is False:
                args.append("--no-read-guard")
            continue
        if key == "proactive_summaries":
            if value is True:
                args.append("--proactive-summaries")
            continue
        if key in _VALUE_MAP:
            args.extend([_VALUE_MAP[key], str(value)])
            continue
        if key == "allowed_commands" and isinstance(value, list):
            args.extend(["--allowed-commands", ",".join(value)])
            continue
        if key in _REPEAT_MAP and isinstance(value, list):
            for item in value:
                args.extend([_REPEAT_MAP[key], str(item)])
            continue
        if key == "extra_body" and isinstance(value, dict):
            args.extend(["--extra-body", json.dumps(value)])
            continue
        warnings.warn(f"Unknown session option '{key}' skipped in CLI mode", stacklevel=2)

    return args


def _write_cli_mcp_config(servers: dict, tmpdir: Path) -> Path:
    path = tmpdir / ".calibra-mcp.json"
    with open(path, "w") as f:
        json.dump({"mcpServers": servers}, f)
    return path


def _make_isolated_env() -> tuple[dict[str, str], Path]:
    env = os.environ.copy()
    empty_config = Path(tempfile.mkdtemp(prefix="calibra_xdg_"))
    env["XDG_CONFIG_HOME"] = str(empty_config)
    return env, empty_config


def _kill_tree(proc: subprocess.Popen):
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except OSError:
        proc.kill()
    proc.wait()


def _reviewer_verdict(report: dict) -> bool | None:
    review_events = [e for e in report.get("timeline", []) if e.get("type") == "review"]
    if not review_events:
        return None
    last = review_events[-1]
    exit_code = last.get("exit_code")
    if exit_code == 0:
        return True
    if exit_code == 1:
        return False
    return None


def _classify_cli_failure(
    exit_code: int,
    stderr_text: str,
    report: dict | None,
    timed_out: bool,
    verified: bool | None,
) -> str | None:
    if timed_out:
        return classify_failure(TimeoutError("wall-clock timeout"), report, timed_out=True)

    if exit_code == 0:
        return classify_failure(None, report, timed_out=False, verified=verified)

    if report:
        report_class = classify_failure(None, report, timed_out=False, verified=verified)
        if report_class is not None:
            if report_class == "task" and exit_code != 0:
                stderr_class = classify_failure(RuntimeError(stderr_text), None, timed_out=False)
                if stderr_class == "provider":
                    return stderr_class
            return report_class

    return classify_failure(RuntimeError(stderr_text), None, timed_out=False)


def run_single_trial(
    spec: TrialSpec,
    campaign: Campaign,
    *,
    keep_workdirs: bool = False,
    merged_session_opts: dict | None = None,
    verbose: bool = False,
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
        if verbose:
            session_opts["verbose"] = True

        session_kwargs = dict(
            base_dir=str(tmpdir),
            provider=spec.variant.model.provider,
            max_turns=campaign.max_turns,
            seed=spec.trial_seed,
            yolo=yolo,
            history=False,
            skills_dir=skills_dir,
            mcp_servers=mcp_servers,
            **session_opts,
        )
        if spec.variant.model.model is not None:
            session_kwargs["model"] = spec.variant.model.model

        session = Session(**session_kwargs)

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


def run_trial_cli(
    spec: TrialSpec,
    campaign: Campaign,
    *,
    keep_workdirs: bool = False,
    merged_session_opts: dict | None = None,
    verbose: bool = False,
) -> TrialResult:
    tmpdir = setup_workspace(spec, spec.variant)
    start = time.monotonic()
    timed_out = False
    env, xdg_dir = _make_isolated_env()
    report_path = tmpdir / ".calibra-report.json"

    swival_toml = tmpdir / "swival.toml"
    if swival_toml.exists():
        swival_toml.unlink()

    try:
        argv = [
            "swival",
            spec.task.prompt,
            "--base-dir",
            str(tmpdir),
            "--provider",
            spec.variant.model.provider,
            *(["--model", spec.variant.model.model] if spec.variant.model.model else []),
            "--max-turns",
            str(campaign.max_turns),
            "--seed",
            str(spec.trial_seed),
            *([] if verbose else ["--quiet"]),
            "--no-history",
            "--report",
            str(report_path),
            "--reviewer",
            campaign.reviewer.command,
            "--max-review-rounds",
            str(campaign.reviewer.max_rounds),
        ]

        mcp_servers = None
        if spec.variant.mcp.config:
            mcp_config_path = Path(spec.variant.mcp.config)
            if mcp_config_path.exists():
                mcp_servers = _load_mcp_config(mcp_config_path)

        if mcp_servers:
            mcp_file = _write_cli_mcp_config(mcp_servers, tmpdir)
            argv.extend(["--mcp-config", str(mcp_file)])
        else:
            argv.append("--no-mcp")

        yolo, session_opts = _resolve_yolo(merged_session_opts or {})
        if yolo:
            argv.append("--yolo")
        argv.extend(_session_opts_to_cli_args(session_opts))

        proc = subprocess.Popen(
            argv,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        try:
            stdout_bytes, stderr_bytes = proc.communicate(timeout=campaign.timeout_s)
        except subprocess.TimeoutExpired:
            _kill_tree(proc)
            timed_out = True
            stderr_bytes = b""

        wall_time = time.monotonic() - start
        exit_code = proc.returncode if not timed_out else -1
        stderr_text = stderr_bytes.decode("utf-8", errors="replace")

        report = None
        if report_path.exists():
            try:
                with open(report_path) as f:
                    report = json.load(f)
            except (json.JSONDecodeError, OSError):
                pass

        verified = None
        if report and campaign.reviewer:
            verified = _reviewer_verdict(report)

        failure_class = _classify_cli_failure(exit_code, stderr_text, report, timed_out, verified)

        return TrialResult(
            spec=spec,
            report=report,
            verified=verified,
            failure_class=failure_class,
            wall_time_s=round(wall_time, 3),
            error_message=stderr_text if failure_class else None,
            attempts=1,
            stderr_capture=stderr_text or None,
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
        shutil.rmtree(xdg_dir, ignore_errors=True)


def _run_trial_impl(
    spec: TrialSpec,
    campaign: Campaign,
    *,
    keep_workdirs: bool = False,
    merged_session_opts: dict | None = None,
    verbose: bool = False,
) -> TrialResult:
    if campaign.reviewer:
        return run_trial_cli(
            spec,
            campaign,
            keep_workdirs=keep_workdirs,
            merged_session_opts=merged_session_opts,
            verbose=verbose,
        )
    return run_single_trial(
        spec,
        campaign,
        keep_workdirs=keep_workdirs,
        merged_session_opts=merged_session_opts,
        verbose=verbose,
    )


def run_trial_with_retry(
    spec: TrialSpec,
    campaign: Campaign,
    *,
    keep_workdirs: bool = False,
    merged_session_opts: dict | None = None,
    verbose: bool = False,
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

        result = _run_trial_impl(
            spec,
            campaign,
            keep_workdirs=keep_workdirs,
            merged_session_opts=merged_session_opts,
            verbose=verbose,
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

    if campaign.reviewer and result.report:
        stats = result.report.get("stats", {})
        review_rounds = stats.get("review_rounds", 0)
        report["calibra"]["review_rounds"] = review_rounds

        verdict = _reviewer_verdict(result.report)
        if verdict is True:
            report["calibra"]["reviewer_verdict"] = "accepted"
        elif verdict is False:
            report["calibra"]["reviewer_verdict"] = "rejected"
        else:
            report["calibra"]["reviewer_verdict"] = "error"

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
    verbose: bool = False,
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

    from calibra.verbose import format_progress_header, format_trial_detail, format_trial_line

    print(format_progress_header(len(specs), workers, verbose))

    trial_verbose = verbose and workers == 1
    _print_lock = threading.Lock()
    completed_count = 0
    passed_count = 0
    failed_count = 0

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
                verbose=trial_verbose,
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
            with _print_lock:
                completed_count += 1
                if result.failure_class is None:
                    passed_count += 1
                else:
                    failed_count += 1

                if verbose:
                    print(
                        format_trial_line(
                            status,
                            result.spec.task.name,
                            result.spec.variant.label,
                            result.spec.repeat_index,
                            result.wall_time_s,
                            result.report,
                            completed_count,
                            len(specs),
                            passed_count,
                            failed_count,
                        )
                    )
                    detail = format_trial_detail(result.report, result.stderr_capture)
                    if detail:
                        print(detail)
                else:
                    print(
                        f"  [{status}] {result.spec.task.name}"
                        f" / {result.spec.variant.label}"
                        f" #{result.spec.repeat_index}"
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
