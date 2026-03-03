# Web Dashboard

Calibra includes an interactive web interface for browsing campaign results. The web dependencies (FastAPI, Uvicorn, Jinja2) are included in the core install.

## Launching the dashboard

Point it at your results directory:

```bash
uv run calibra web serve results/ --open
```

This starts a local server and opens your browser. By default it runs on `http://127.0.0.1:8118`.

| Flag     | Default     | Description                |
| -------- | ----------- | -------------------------- |
| `--port` | `8118`      | Port number                |
| `--host` | `127.0.0.1` | Bind address               |
| `--open` | off         | Automatically open browser |

To make the dashboard accessible from other machines:

```bash
uv run calibra web serve results/ --host 0.0.0.0 --port 9000
```

## Pages

### Campaign list

The landing page shows all campaigns found in the results directory. Each campaign card displays the campaign name, number of variants and tasks, total trial count, overall weighted pass rate (color-coded), and the last updated timestamp. Click a campaign to drill in.

### Campaign detail

This is the main analysis view for a campaign. At the top you'll see KPI tiles for overall pass rate, variant count, task count, total trials, median turns, and failure rate. Below that is a pass rate bar chart with variants sorted by pass rate and color-coded by performance, an efficiency scatter plot showing token usage on the x-axis versus pass rate on the y-axis with the Pareto front highlighted, and a sortable variant rankings table with pass rate, turns, tokens, LLM time, efficiency scores, and a review rounds column (shown only when the campaign used a reviewer). Click any variant row to see its detail page.

### Task heatmap

Accessible from the campaign detail page, the heatmap shows a matrix with tasks as rows and variants as columns. Each cell shows the pass rate for that task+variant pair, color-coded from green (high) to red (low). Hovering over a cell shows sample count, mean turns, and mean tokens. This view quickly reveals which tasks are hard for which variants.

### Variant detail

A deep dive into a single variant's performance. You'll find aggregate stats (pass rate, mean turns, mean tokens, mean wall time), a per-task breakdown with pass rates and distributions, failure class counts showing how many trials hit each failure type, tool usage statistics, and a filterable list of every individual trial with links to the trial inspector.

### Trial inspector

View a single trial in full detail: a formatted stats table (turns, timing, tokens, etc.), tool usage breakdown, timeline of events, and a raw JSON viewer for the complete report.

### Comparison

Compare two campaigns side by side with dropdown selectors for campaign A and campaign B, a pass rate comparison chart for common variants, a delta table showing improvement or regression for each variant, and effect size indicators.

### Trial diff

Compare two individual trial report JSON files side by side. Access this page at `/diff` with query parameters `a` and `b` pointing to local file paths, or use `calibra diff` from the CLI which opens this page automatically. The diff view shows KPI delta tiles (wall time, turns, tokens, LLM time, tool time, LLM calls, tool calls, compactions) with color-coded deltas (green when the B value is lower, red when higher), outcome and verification badges, model and provider info, a settings diff table (only shown when settings differ), per-tool usage comparison with "only in A/B" badges, side-by-side event timelines, and collapsible raw JSON panels.

## Static HTML export

You can build a static site to share without running a server:

```bash
uv run calibra web build results/ --output site/
```

The export generates a multi-page static site mirroring the dashboard structure, with an index page, per-campaign pages, variant detail pages, task heatmaps, and trial inspector pages. Static assets (CSS, JS) are copied into a `static/` directory alongside the HTML. The default output location is `<results_dir>/web`. You can upload the output directory to a static host or check it into a repository.

## REST API

The web dashboard also exposes a JSON API for programmatic access:

| Endpoint                                               | Method | Description               |
| ------------------------------------------------------ | ------ | ------------------------- |
| `/api/campaigns`                                       | GET    | List all campaigns        |
| `/api/campaign/{name}`                                 | GET    | Campaign summary data     |
| `/api/campaign/{name}/heatmap`                         | GET    | Task-variant heatmap data |
| `/api/campaign/{name}/trial/{task}/{variant}/{repeat}` | GET    | Single trial JSON         |
| `/api/compare?a={name}&b={name}`                       | GET    | Campaign comparison       |
| `/api/reload`                                          | POST   | Force cache refresh       |

```bash
# List campaigns
curl http://127.0.0.1:8118/api/campaigns

# Get campaign summary
curl http://127.0.0.1:8118/api/campaign/model-shootout

# Get a specific trial
curl http://127.0.0.1:8118/api/campaign/model-shootout/trial/hello-world/sonnet_minimal_none_none_base/0

# Compare two campaigns
curl "http://127.0.0.1:8118/api/compare?a=run-a&b=run-b"
```

## Dashboard features

The web interface supports dark mode (toggle in the header, persisted in the browser), keyboard shortcuts for navigating between pages, column sorting by clicking table headers, a responsive layout that works on different screen sizes, and manual cache refresh via `POST /api/reload`.
