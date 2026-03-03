"""CLI entrypoint for Calibra."""

import argparse
import sys


def cmd_validate(args):
    """Validate a campaign config file."""
    from pathlib import Path

    from calibra.config import load_campaign
    from calibra.prices import load_prices, validate_price_coverage

    campaign = load_campaign(args.config)

    if campaign.budget.require_price_coverage:
        prices = load_prices(Path(args.config))
        validate_price_coverage(campaign, prices)

    from calibra.matrix import expand_matrix, apply_constraints, apply_screening
    from calibra.tasks import discover_tasks

    variants = expand_matrix(campaign)
    variants = apply_constraints(variants, campaign.constraints)
    variants = apply_screening(variants, campaign.sampling, campaign.seed)
    tasks = discover_tasks(campaign.tasks_dir)

    total = len(variants) * len(tasks) * campaign.repeat
    print(
        f"Config valid. {len(variants)} variants x {len(tasks)} tasks x {campaign.repeat} repeats = {total} trials."
    )


def cmd_run(args):
    """Run a campaign."""
    from calibra.config import load_campaign
    from calibra.matrix import expand_matrix, apply_constraints, apply_screening
    from calibra.tasks import discover_tasks

    campaign = load_campaign(args.config)
    variants = expand_matrix(campaign)
    variants = apply_constraints(variants, campaign.constraints)
    variants = apply_screening(variants, campaign.sampling, campaign.seed)

    if args.filter:
        from calibra.matrix import apply_filter

        variants = apply_filter(variants, args.filter)

    tasks = discover_tasks(campaign.tasks_dir)

    if args.dry_run:
        print(f"Campaign: {campaign.name}")
        print(f"Config hash: {campaign.config_hash}")
        print(f"Tasks: {len(tasks)}")
        print(f"Variants: {len(variants)}")
        print(f"Repeats: {campaign.repeat}")
        print(f"Total trials: {len(variants) * len(tasks) * campaign.repeat}")
        print()
        for v in variants:
            print(f"  {v.label}")
        return

    from calibra.runner import run_campaign

    run_campaign(
        campaign=campaign,
        variants=variants,
        tasks=tasks,
        workers=args.workers,
        output_dir=args.output,
        resume=args.resume,
        keep_workdirs=args.keep_workdirs,
        config_path=args.config,
        verbose=args.verbose,
    )


def cmd_analyze(args):
    """Analyze campaign results."""
    from calibra.analyze import analyze_campaign

    analyze_campaign(args.results_dir, output_dir=args.output)


def cmd_show(args):
    """Show a single trial report."""
    from calibra.show import show_report

    show_report(args.report)


def cmd_compare(args):
    """Compare two campaign results."""
    from calibra.compare import compare_campaigns

    compare_campaigns(args.dir_a, args.dir_b, output_dir=args.output)


def cmd_diff(args):
    """Diff two trial report JSON files in the browser."""
    from pathlib import Path

    from calibra.web.export import load_diff_report

    paths = []
    for label, raw in [("A", args.file_a), ("B", args.file_b)]:
        p = Path(raw).resolve(strict=False)
        try:
            load_diff_report(p, label)
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            sys.exit(1)
        paths.append(p)

    if args.export:
        output = Path(args.export).resolve()
        if output.is_dir():
            print(f"Error: --export path is a directory: {output}", file=sys.stderr)
            sys.exit(1)
        if not output.parent.is_dir():
            print(f"Error: parent directory does not exist: {output.parent}", file=sys.stderr)
            sys.exit(1)
        from calibra.web.export import export_diff

        export_diff(paths[0], paths[1], output)
        print(f"Exported diff to {output}")
        return

    import tempfile
    import threading
    import urllib.parse
    import webbrowser

    port = args.port
    qs = urllib.parse.urlencode({"a": str(paths[0]), "b": str(paths[1])})
    url = f"http://127.0.0.1:{port}/diff?{qs}"

    def _open():
        import time

        time.sleep(0.5)
        webbrowser.open(url)

    threading.Thread(target=_open, daemon=True).start()

    import uvicorn

    from calibra.web import create_app

    with tempfile.TemporaryDirectory() as tmp:
        app = create_app(Path(tmp))
        uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")


def cmd_web_serve(args):
    """Serve the web interface."""
    from pathlib import Path

    from calibra.web.server import run_server

    run_server(
        results_dir=Path(args.results_dir),
        host=args.host,
        port=args.port,
        open_browser=args.open,
    )


def cmd_web_build(args):
    """Build a static web export."""
    from pathlib import Path

    from calibra.web.export import build_static_site

    output = Path(args.output) if args.output else None
    build_static_site(Path(args.results_dir), output_dir=output)


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="calibra", description="Benchmarking harness for coding agents"
    )
    sub = parser.add_subparsers(dest="command")

    # validate
    p_val = sub.add_parser("validate", help="Validate a campaign config file")
    p_val.add_argument("config", help="Path to campaign TOML file")

    # run
    p_run = sub.add_parser("run", help="Run a campaign")
    p_run.add_argument("config", help="Path to campaign TOML file")
    p_run.add_argument("--workers", type=int, default=1, help="Number of parallel workers")
    p_run.add_argument("--dry-run", action="store_true", help="Print trial plan without executing")
    p_run.add_argument("--filter", help="Filter variants (e.g. model=sonnet,skills=full)")
    p_run.add_argument("--resume", action="store_true", help="Skip completed trials")
    p_run.add_argument("--output", default="results", help="Output directory")
    p_run.add_argument(
        "--keep-workdirs", action="store_true", help="Keep trial working directories"
    )
    p_run.add_argument("-v", "--verbose", action="store_true", help="Show detailed trial output")

    # analyze
    p_ana = sub.add_parser("analyze", help="Analyze campaign results")
    p_ana.add_argument("results_dir", help="Path to campaign results directory")
    p_ana.add_argument("--output", default=None, help="Output directory (defaults to results_dir)")

    # show
    p_show = sub.add_parser("show", help="Show a single trial report")
    p_show.add_argument("report", help="Path to trial report JSON")

    # compare
    p_cmp = sub.add_parser("compare", help="Compare two campaign results")
    p_cmp.add_argument("dir_a", help="First campaign results directory")
    p_cmp.add_argument("dir_b", help="Second campaign results directory")
    p_cmp.add_argument("--output", default=None, help="Output directory")

    # diff
    p_diff = sub.add_parser("diff", help="Diff two trial report JSON files in the browser")
    p_diff.add_argument("file_a", help="First report JSON file")
    p_diff.add_argument("file_b", help="Second report JSON file")
    p_diff.add_argument("--port", type=int, default=8118, help="Port (default: 8118)")
    p_diff.add_argument(
        "--export", metavar="FILE", help="Export diff as a self-contained HTML file"
    )

    # web
    p_web = sub.add_parser("web", help="Web interface for results")
    web_sub = p_web.add_subparsers(dest="web_command")

    p_serve = web_sub.add_parser("serve", help="Launch interactive web server")
    p_serve.add_argument("results_dir", help="Path to results directory")
    p_serve.add_argument("--port", type=int, default=8118, help="Port (default: 8118)")
    p_serve.add_argument("--host", default="127.0.0.1", help="Host (default: 127.0.0.1)")
    p_serve.add_argument("--open", action="store_true", help="Open browser automatically")

    p_build = web_sub.add_parser("build", help="Build static web export")
    p_build.add_argument("results_dir", help="Path to results directory")
    p_build.add_argument("--output", default=None, help="Output directory")

    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        sys.exit(1)

    if args.command == "web":
        if args.web_command == "serve":
            handler = cmd_web_serve
        elif args.web_command == "build":
            handler = cmd_web_build
        else:
            p_web.print_help()
            sys.exit(1)
    else:
        handler = {
            "validate": cmd_validate,
            "run": cmd_run,
            "analyze": cmd_analyze,
            "show": cmd_show,
            "compare": cmd_compare,
            "diff": cmd_diff,
        }[args.command]

    try:
        handler(args)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
