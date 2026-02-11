"""Static site builder: generates self-contained HTML with inlined JSON data."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from html import escape as html_escape
from pathlib import Path

from calibra.utils import json_for_html, weighted_pass_rate

SCHEMA_VERSION = 1

STATIC_DIR = Path(__file__).parent / "static"


def _build_campaign_bundle(campaign_dir: Path) -> dict:
    """Build structured data bundle for a single campaign."""
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

    variants_raw = summary.get("variants")
    trials_raw = summary.get("trials")
    if not isinstance(variants_raw, list) or not isinstance(trials_raw, list):
        raise ValueError(
            f"Invalid summary.json structure in {campaign_dir}: "
            f"expected 'variants' and 'trials' arrays. "
            f"Expected schema version {SCHEMA_VERSION}."
        )

    n_variants = len(variants_raw)
    n_trials = len(trials_raw)
    tasks = {t.get("task") for t in trials_raw if "task" in t}
    n_tasks = len(tasks)

    pass_rate = weighted_pass_rate(variants_raw)

    task_aggregates = _build_task_aggregates(trials_raw)

    campaign_data = {
        "name": campaign_dir.name,
        "n_variants": n_variants,
        "n_tasks": n_tasks,
        "n_trials": n_trials,
        "pass_rate": pass_rate,
    }

    summary_mtime = datetime.fromtimestamp(
        summary_path.stat().st_mtime, tz=timezone.utc
    ).isoformat()

    meta = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": summary_mtime,
        "generator": "calibra",
    }

    return {
        "campaign": campaign_data,
        "variants": variants_raw,
        "tasks": task_aggregates,
        "trials": trials_raw,
        "meta": meta,
    }


def _build_task_aggregates(trials: list[dict]) -> list[dict]:
    """Group trials by (task, variant) and compute per-task-variant aggregates."""
    cells: dict[tuple[str, str], list[dict]] = {}
    for t in trials:
        key = (t.get("task", ""), t.get("variant_label", ""))
        cells.setdefault(key, []).append(t)

    result = []
    for (task, variant), group in sorted(cells.items()):
        n = len(group)
        passes = sum(1 for t in group if t.get("verified") is True)
        result.append(
            {
                "task": task,
                "variant": variant,
                "n": n,
                "passes": passes,
                "pass_rate": round(passes / n, 4) if n > 0 else 0.0,
            }
        )
    return result


def _render_export_html(bundle: dict) -> str:
    """Render a self-contained HTML page with inlined JSON data blocks."""
    campaign = bundle["campaign"]

    def inline_json(data_id: str, data: object) -> str:
        encoded = json_for_html(data)
        return f'<script type="application/json" id="data-{data_id}">\n{encoded}\n</script>'

    blocks = [
        inline_json("campaign", bundle["campaign"]),
        inline_json("variants", bundle["variants"]),
        inline_json("tasks", bundle["tasks"]),
        inline_json("trials", bundle["trials"]),
        inline_json("meta", bundle["meta"]),
    ]

    pass_rate_display = ""
    if campaign.get("pass_rate") is not None:
        pass_rate_display = f"{campaign['pass_rate'] * 100:.1f}%"

    return f"""\
<!DOCTYPE html>
<html lang="en" class="h-full">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Calibra: {html_escape(campaign["name"])}</title>
  <script src="assets/tailwindcss-browser-4.2.1.js"></script>
  <script src="assets/htmx-2.0.8.min.js"></script>
  <script src="assets/plotly-3.4.0.min.js"></script>
  <style type="text/tailwindcss">
    @theme {{
      --font-mono: ui-monospace, 'IBM Plex Mono', 'Cascadia Code', 'Source Code Pro', Menlo, Consolas, 'DejaVu Sans Mono', monospace;
      --color-pass: #0d9488;
      --color-warn: #d97706;
      --color-fail: #dc2626;
    }}
  </style>
</head>
<body class="h-full bg-slate-50 text-slate-900 dark:bg-slate-900 dark:text-slate-100">
  <nav class="bg-white dark:bg-slate-800 border-b border-slate-200 dark:border-slate-700 px-6 py-3 flex items-center justify-between">
    <span class="text-lg font-semibold tracking-tight text-slate-900 dark:text-white">Calibra</span>
    <button id="theme-toggle" class="p-1.5 rounded-md text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200" title="Toggle dark mode">
      <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z"/>
      </svg>
    </button>
  </nav>

  <main class="max-w-7xl mx-auto px-6 py-8">
    <div class="mb-6">
      <h1 class="text-2xl font-bold text-slate-900 dark:text-white">{html_escape(campaign["name"])}</h1>
      <p class="mt-1 text-sm text-slate-500 dark:text-slate-400">{campaign["n_variants"]} variants, {campaign["n_tasks"]} tasks, {campaign["n_trials"]} trials{f", {pass_rate_display} pass rate" if pass_rate_display else ""}</p>
    </div>

    <div id="dashboard">
      <div id="kpi-tiles" class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4 mb-8">
        <div class="rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 p-4">
          <span class="block text-xs uppercase tracking-wide text-slate-400 dark:text-slate-500">Pass Rate</span>
          <span class="text-2xl font-bold font-mono tabular-nums text-slate-900 dark:text-white">{pass_rate_display or "-"}</span>
        </div>
        <div class="rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 p-4">
          <span class="block text-xs uppercase tracking-wide text-slate-400 dark:text-slate-500">Variants</span>
          <span class="text-2xl font-bold font-mono tabular-nums text-slate-900 dark:text-white">{campaign["n_variants"]}</span>
        </div>
        <div class="rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 p-4">
          <span class="block text-xs uppercase tracking-wide text-slate-400 dark:text-slate-500">Tasks</span>
          <span class="text-2xl font-bold font-mono tabular-nums text-slate-900 dark:text-white">{campaign["n_tasks"]}</span>
        </div>
        <div class="rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 p-4">
          <span class="block text-xs uppercase tracking-wide text-slate-400 dark:text-slate-500">Total Trials</span>
          <span class="text-2xl font-bold font-mono tabular-nums text-slate-900 dark:text-white">{campaign["n_trials"]}</span>
        </div>
        <div class="rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 p-4">
          <span class="block text-xs uppercase tracking-wide text-slate-400 dark:text-slate-500">Med. Turns</span>
          <span class="text-2xl font-bold font-mono tabular-nums text-slate-900 dark:text-white" id="kpi-turns">-</span>
        </div>
        <div class="rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 p-4">
          <span class="block text-xs uppercase tracking-wide text-slate-400 dark:text-slate-500">Failure Rate</span>
          <span class="text-2xl font-bold font-mono tabular-nums text-slate-900 dark:text-white" id="kpi-failure">-</span>
        </div>
      </div>

      <div id="warnings-panel" class="mb-8 hidden">
        <div class="rounded-lg border border-amber-200 dark:border-amber-800 bg-amber-50 dark:bg-amber-900/20 p-4">
          <h3 class="text-sm font-semibold text-amber-800 dark:text-amber-300 mb-2">Warnings</h3>
          <ul id="warnings-list" class="text-sm text-amber-700 dark:text-amber-400 space-y-1"></ul>
        </div>
      </div>

      <div class="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
        <div class="rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 p-4">
          <h3 class="text-sm font-semibold text-slate-700 dark:text-slate-300 mb-3">Pass Rate by Variant</h3>
          <div id="chart-pass-rate" style="height: 300px;"></div>
        </div>
        <div class="rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 p-4">
          <h3 class="text-sm font-semibold text-slate-700 dark:text-slate-300 mb-3">Efficiency: Tokens vs Pass Rate</h3>
          <div id="chart-efficiency" style="height: 300px;"></div>
        </div>
      </div>

      <div id="variant-table" class="rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 overflow-hidden">
        <p class="p-8 text-center text-slate-500 dark:text-slate-400">Loading variant rankings...</p>
      </div>
    </div>
  </main>

{chr(10).join(blocks)}

  <script>
    // Theme toggle
    const toggle = document.getElementById('theme-toggle');
    const htmlEl = document.documentElement;
    if (localStorage.getItem('theme') === 'dark' || (!localStorage.getItem('theme') && window.matchMedia('(prefers-color-scheme: dark)').matches)) {{
      htmlEl.classList.add('dark');
    }}
    toggle.addEventListener('click', () => {{
      htmlEl.classList.toggle('dark');
      localStorage.setItem('theme', htmlEl.classList.contains('dark') ? 'dark' : 'light');
    }});

    // Schema compatibility check
    const meta = JSON.parse(document.getElementById('data-meta').textContent);
    if (meta.schema_version > {SCHEMA_VERSION}) {{
      var errDiv = document.createElement('div');
      errDiv.className = 'rounded-lg border border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-900/20 p-6 text-center';
      var errP = document.createElement('p');
      errP.className = 'text-red-700 dark:text-red-400 font-medium';
      errP.textContent = 'This export was generated with a newer schema (v' + meta.schema_version + '). Please update Calibra to view this data.';
      errDiv.appendChild(errP);
      var dashboard = document.getElementById('dashboard');
      dashboard.innerHTML = '';
      dashboard.appendChild(errDiv);
    }} else {{
      function esc(s) {{ var d = document.createElement('div'); d.textContent = String(s); return d.innerHTML; }}
      function num(v) {{ var n = Number(v); return isNaN(n) ? 0 : n; }}
      function stat(obj, key) {{ return num(obj && typeof obj === 'object' ? obj[key] : 0); }}

      var variants = JSON.parse(document.getElementById('data-variants').textContent);
      var isDark = htmlEl.classList.contains('dark');
      var textColor = isDark ? '#94a3b8' : '#64748b';
      var gridColor = isDark ? '#334155' : '#e2e8f0';
      var bgColor = 'rgba(0,0,0,0)';
      var plotlyFont = {{ family: 'ui-monospace, monospace', size: 11, color: textColor }};

      // KPI: median turns
      var allTurns = variants.map(function(v) {{ return stat(v.turns, 'median'); }});
      if (allTurns.length > 0) {{
        var sorted_t = allTurns.slice().sort(function(a,b){{return a-b;}});
        document.getElementById('kpi-turns').textContent = sorted_t[Math.floor(sorted_t.length/2)].toFixed(1);
      }}

      // KPI: failure rate
      var totalTrials = 0, totalFails = 0;
      variants.forEach(function(v) {{
        var n = num(v.n_trials);
        totalTrials += n;
        totalFails += n * (1 - num(v.pass_rate));
      }});
      if (totalTrials > 0) {{
        document.getElementById('kpi-failure').textContent = ((totalFails / totalTrials) * 100).toFixed(1) + '%';
      }}

      // Warnings
      var warnings = [];
      variants.forEach(function(v) {{
        var label = String(v.variant_label || '');
        ['turns', 'llm_time_s', 'prompt_tokens_est'].forEach(function(metric) {{
          var m = v[metric];
          if (m && typeof m === 'object') {{
            var mean = num(m.mean), std = num(m.std);
            if (mean > 0 && std / mean > 0.5) {{
              warnings.push(esc(label) + ': high variability in ' + esc(metric.replace(/_/g, ' ')) + ' (CV=' + (std/mean).toFixed(2) + ')');
            }}
          }}
        }});
        if (num(v.n_trials) < 3) {{
          warnings.push(esc(label) + ': fewer than 3 repeats, low confidence');
        }}
      }});
      if (warnings.length > 0) {{
        var panel = document.getElementById('warnings-panel');
        panel.classList.remove('hidden');
        var ul = document.getElementById('warnings-list');
        warnings.forEach(function(w) {{
          var li = document.createElement('li');
          li.innerHTML = w;
          ul.appendChild(li);
        }});
      }}

      if (variants.length > 0) {{
        // Pass Rate Bar Chart
        var barSorted = variants.slice().sort(function(a, b) {{ return num(a.pass_rate) - num(b.pass_rate); }});
        var barLabels = barSorted.map(function(v) {{ return String(v.variant_label || ''); }});
        var barValues = barSorted.map(function(v) {{ return num(v.pass_rate) * 100; }});
        var barColors = barSorted.map(function(v) {{
          var pr = num(v.pass_rate);
          if (pr >= 0.8) return '#0d9488';
          if (pr >= 0.5) return '#d97706';
          return '#dc2626';
        }});

        Plotly.newPlot('chart-pass-rate', [{{
          type: 'bar',
          orientation: 'h',
          y: barLabels,
          x: barValues,
          marker: {{ color: barColors }},
          hovertemplate: '%{{y}}<br>Pass rate: %{{x:.1f}}%<extra></extra>'
        }}], {{
          margin: {{ l: 140, r: 20, t: 10, b: 40 }},
          xaxis: {{ title: 'Pass Rate (%)', range: [0, 105], color: textColor, gridcolor: gridColor }},
          yaxis: {{ color: textColor, automargin: true }},
          paper_bgcolor: bgColor,
          plot_bgcolor: bgColor,
          font: plotlyFont
        }}, {{ displayModeBar: false, responsive: true }});

        // Efficiency Scatter
        var scatterX = variants.map(function(v) {{ return stat(v.prompt_tokens_est, 'mean'); }});
        var scatterY = variants.map(function(v) {{ return num(v.pass_rate) * 100; }});
        var scatterText = variants.map(function(v) {{
          return String(v.variant_label || '') +
            '<br>Pass: ' + (num(v.pass_rate)*100).toFixed(1) + '%' +
            '<br>Tokens: ' + stat(v.prompt_tokens_est, 'mean').toLocaleString('en-US', {{maximumFractionDigits:0}}) +
            '<br>Turns: ' + stat(v.turns, 'mean').toFixed(1);
        }});

        // Pareto front: maximize pass_rate, minimize tokens
        var points = variants.map(function(v, i) {{
          return {{ idx: i, pr: num(v.pass_rate), tok: stat(v.prompt_tokens_est, 'mean') }};
        }});
        points.sort(function(a, b) {{ return a.tok - b.tok; }});
        var pareto = [];
        var bestPR = -1;
        points.forEach(function(p) {{
          if (p.pr > bestPR) {{
            pareto.push(p);
            bestPR = p.pr;
          }}
        }});
        pareto.sort(function(a, b) {{ return a.tok - b.tok; }});

        var scatterTraces = [{{
          type: 'scatter',
          mode: 'markers',
          x: scatterX,
          y: scatterY,
          text: scatterText,
          hovertemplate: '%{{text}}<extra></extra>',
          marker: {{ size: 10, color: '#3b82f6', opacity: 0.8 }},
          name: 'Variants'
        }}];

        if (pareto.length > 1) {{
          scatterTraces.push({{
            type: 'scatter',
            mode: 'lines+markers',
            x: pareto.map(function(p) {{ return scatterX[p.idx]; }}),
            y: pareto.map(function(p) {{ return scatterY[p.idx]; }}),
            line: {{ color: '#0d9488', width: 2, dash: 'dot' }},
            marker: {{ size: 8, color: '#0d9488', symbol: 'diamond' }},
            name: 'Pareto front',
            hoverinfo: 'skip'
          }});
        }}

        Plotly.newPlot('chart-efficiency', scatterTraces, {{
          margin: {{ l: 60, r: 20, t: 10, b: 50 }},
          xaxis: {{ title: 'Mean Tokens', color: textColor, gridcolor: gridColor }},
          yaxis: {{ title: 'Pass Rate (%)', range: [0, 105], color: textColor, gridcolor: gridColor }},
          paper_bgcolor: bgColor,
          plot_bgcolor: bgColor,
          font: plotlyFont,
          showlegend: pareto.length > 1,
          legend: {{ x: 1, xanchor: 'right', y: 0, font: {{ size: 10, color: textColor }} }}
        }}, {{ displayModeBar: false, responsive: true }});

        // Sortable Variant Table
        var currentSort = null;
        var currentDir = 'desc';
        var tableVariants = variants.slice();

        function getVal(v, col) {{
          if (col === 'variant_label') return String(v.variant_label || '');
          if (col === 'pass_rate') return num(v.pass_rate);
          if (col === 'turns') return stat(v.turns, 'mean');
          if (col === 'tokens') return stat(v.prompt_tokens_est, 'mean');
          if (col === 'llm_time') return stat(v.llm_time_s, 'mean');
          if (col === 'wall_time') return stat(v.wall_time_s, 'mean');
          if (col === 'score_1k') return num(v.score_per_1k_tokens);
          return 0;
        }}

        function renderTable(sortCol, sortDir) {{
          var sorted = tableVariants.slice();
          if (sortCol) {{
            sorted.sort(function(a, b) {{
              var aV = getVal(a, sortCol), bV = getVal(b, sortCol);
              var cmp = (typeof aV === 'string') ? aV.localeCompare(bV) : aV - bV;
              return sortDir === 'desc' ? -cmp : cmp;
            }});
          }} else {{
            sorted.sort(function(a, b) {{
              var prA = num(a.pass_rate), prB = num(b.pass_rate);
              if (prB !== prA) return prB - prA;
              var tokA = stat(a.prompt_tokens_est, 'mean'), tokB = stat(b.prompt_tokens_est, 'mean');
              if (tokA !== tokB) return tokA - tokB;
              return stat(a.turns, 'mean') - stat(b.turns, 'mean');
            }});
          }}

          var cols = [
            ['rank', 'Rank', 'text-left'],
            ['variant_label', 'Variant', 'text-left'],
            ['pass_rate', 'Pass Rate', 'text-right'],
            ['turns', 'Turns', 'text-right'],
            ['tokens', 'Tokens', 'text-right'],
            ['llm_time', 'LLM Time', 'text-right'],
            ['wall_time', 'Wall Time', 'text-right'],
            ['score_1k', 'Score/1k', 'text-right']
          ];

          var tbl = '<table class="w-full text-sm" id="variant-tbl"><thead class="bg-slate-50 dark:bg-slate-700/50"><tr>';
          cols.forEach(function(c) {{
            var arrow = '';
            if (sortCol === c[0]) arrow = sortDir === 'asc' ? ' \\u25B2' : ' \\u25BC';
            tbl += '<th class="px-4 py-2 ' + c[2] + ' text-xs font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400 cursor-pointer select-none" data-sort="' + c[0] + '">' + c[1] + arrow + '</th>';
          }});
          tbl += '</tr></thead><tbody class="divide-y divide-slate-100 dark:divide-slate-700">';

          sorted.forEach(function(v, i) {{
            var pr = num(v.pass_rate);
            var prClass = pr >= 0.8 ? 'text-teal-600 dark:text-teal-400' :
                          pr >= 0.5 ? 'text-amber-600 dark:text-amber-400' :
                          'text-red-600 dark:text-red-400';
            tbl += '<tr class="hover:bg-slate-50 dark:hover:bg-slate-700/30 transition-colors duration-100">';
            tbl += '<td class="px-4 py-2 font-mono tabular-nums text-slate-500 dark:text-slate-400">' + esc(i + 1) + '</td>';
            tbl += '<td class="px-4 py-2 font-mono text-sm text-slate-900 dark:text-white">' + esc(v.variant_label) + '</td>';
            tbl += '<td class="px-4 py-2 text-right font-mono tabular-nums ' + prClass + '">' + esc((pr * 100).toFixed(1) + '%') + '</td>';
            tbl += '<td class="px-4 py-2 text-right font-mono tabular-nums text-slate-700 dark:text-slate-300">' + esc(stat(v.turns, 'mean').toFixed(1)) + '</td>';
            tbl += '<td class="px-4 py-2 text-right font-mono tabular-nums text-slate-700 dark:text-slate-300">' + esc(stat(v.prompt_tokens_est, 'mean').toLocaleString('en-US', {{maximumFractionDigits: 0}})) + '</td>';
            tbl += '<td class="px-4 py-2 text-right font-mono tabular-nums text-slate-700 dark:text-slate-300">' + esc(stat(v.llm_time_s, 'mean').toFixed(1) + 's') + '</td>';
            tbl += '<td class="px-4 py-2 text-right font-mono tabular-nums text-slate-700 dark:text-slate-300">' + esc(stat(v.wall_time_s, 'mean').toFixed(1) + 's') + '</td>';
            tbl += '<td class="px-4 py-2 text-right font-mono tabular-nums text-slate-700 dark:text-slate-300">' + esc(num(v.score_per_1k_tokens).toFixed(1)) + '</td>';
            tbl += '</tr>';
          }});
          tbl += '</tbody></table>';
          document.getElementById('variant-table').innerHTML = tbl;

          // Rebind click handlers
          document.querySelectorAll('#variant-tbl th[data-sort]').forEach(function(th) {{
            th.addEventListener('click', function() {{
              var col = th.dataset.sort;
              if (col === 'rank') return;
              var dir;
              if (currentSort === col) {{
                dir = currentDir === 'desc' ? 'asc' : 'desc';
              }} else {{
                dir = (col === 'variant_label') ? 'asc' : 'desc';
              }}
              currentSort = col;
              currentDir = dir;
              var params = new URLSearchParams(window.location.search);
              params.set('sort', col);
              params.set('dir', dir);
              history.replaceState(null, '', '?' + params.toString());
              renderTable(col, dir);
            }});
          }});
        }}

        // Apply URL sort or default
        var params = new URLSearchParams(window.location.search);
        var urlSort = params.get('sort');
        var urlDir = params.get('dir') || 'desc';
        if (urlSort) {{
          currentSort = urlSort;
          currentDir = urlDir;
          renderTable(urlSort, urlDir);
        }} else {{
          renderTable(null, 'desc');
        }}
      }} else {{
        document.getElementById('variant-table').textContent = 'No variant data available.';
      }}
    }}
  </script>
</body>
</html>
"""


def build_static_site(results_dir: Path, output_dir: Path | None = None) -> Path:
    """Build a static site with inlined data for campaigns.

    Accepts either a results root (parent of campaign dirs) or a single campaign
    directory that contains summary.json directly. If output_dir is None, writes
    to <campaign>/web/ for each campaign. Returns the output directory path.
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

    built = []
    for campaign_dir in campaign_dirs:
        if output_dir is not None:
            out = output_dir / campaign_dir.name / "web"
        else:
            out = campaign_dir / "web"

        bundle = _build_campaign_bundle(campaign_dir)
        _write_campaign_export(bundle, out)
        built.append(out)

    return built[0].parent if len(built) == 1 else results_dir


def build_single_campaign(campaign_dir: Path, output_dir: Path | None = None) -> Path:
    """Build a static site for a single campaign directory.

    Returns the output directory path.
    """
    campaign_dir = campaign_dir.resolve()
    bundle = _build_campaign_bundle(campaign_dir)
    out = output_dir if output_dir is not None else campaign_dir / "web"
    _write_campaign_export(bundle, out)
    return out


def _write_campaign_export(bundle: dict, output_dir: Path) -> None:
    """Write HTML and assets to output directory."""
    output_dir.mkdir(parents=True, exist_ok=True)

    html = _render_export_html(bundle)
    (output_dir / "index.html").write_text(html)

    assets_dir = output_dir / "assets"
    vendor_src = STATIC_DIR / "vendor"
    if vendor_src.is_dir():
        if assets_dir.exists():
            shutil.rmtree(assets_dir)
        shutil.copytree(vendor_src, assets_dir)
