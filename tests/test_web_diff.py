"""Tests for the /diff trial report comparison feature."""

import json
import re

import pytest
from fastapi.testclient import TestClient

from calibra.cli import main
from calibra.web import create_app
from calibra.web.export import export_diff, load_diff_report
from calibra.web.viewdata import KpiDelta, build_trial_diff


def _make_report(
    task="t1",
    variant="v1",
    repeat=0,
    outcome="success",
    verified=True,
    model="claude-sonnet",
    provider="anthropic",
    wall_time=10.5,
    turns=5,
    llm_calls=5,
    tool_calls_total=8,
    tool_calls_failed=1,
    total_llm_time=3.2,
    total_tool_time=1.1,
    compactions=0,
    tokens=1200,
    tools=None,
    settings=None,
    timeline=None,
):
    if tools is None:
        tools = {"Read": {"succeeded": 4, "failed": 0}, "Write": {"succeeded": 3, "failed": 1}}
    if settings is None:
        settings = {"max_turns": 25, "temperature": 0.7}
    if timeline is None:
        timeline = [
            {
                "type": "llm_call",
                "prompt_tokens_est": tokens,
                "duration_s": 0.9,
                "finish_reason": "stop",
            },
        ]
    return {
        "version": 1,
        "model": model,
        "provider": provider,
        "result": {"outcome": outcome},
        "stats": {
            "turns": turns,
            "llm_calls": llm_calls,
            "tool_calls_total": tool_calls_total,
            "tool_calls_succeeded": tool_calls_total - tool_calls_failed,
            "tool_calls_failed": tool_calls_failed,
            "tool_calls_by_name": tools,
            "total_llm_time_s": total_llm_time,
            "total_tool_time_s": total_tool_time,
            "compactions": compactions,
            "skills_used": [],
            "guardrail_interventions": 0,
        },
        "timeline": timeline,
        "calibra": {
            "task": task,
            "variant": variant,
            "repeat": repeat,
            "wall_time_s": wall_time,
            "verified": verified,
            "config_hash": "abc",
        },
        "settings": settings,
    }


class TestKpiDelta:
    def test_normal_values(self):
        kpi = KpiDelta.build(100, 120)
        assert kpi.a == 100
        assert kpi.b == 120
        assert kpi.delta == 20
        assert kpi.pct == pytest.approx(0.2)

    def test_zero_baseline(self):
        kpi = KpiDelta.build(0, 50)
        assert kpi.delta == 50
        assert kpi.pct is None

    def test_both_zero(self):
        kpi = KpiDelta.build(0, 0)
        assert kpi.delta == 0
        assert kpi.pct is None

    def test_negative_delta(self):
        kpi = KpiDelta.build(100, 80)
        assert kpi.delta == -20
        assert kpi.pct == pytest.approx(-0.2)

    def test_string_values_coerced(self):
        kpi = KpiDelta.build("100", "120")
        assert kpi.a == 100
        assert kpi.b == 120

    def test_none_values_coerced(self):
        kpi = KpiDelta.build(None, None)
        assert kpi.a == 0
        assert kpi.b == 0
        assert kpi.pct is None


class TestBuildTrialDiff:
    def test_normal_reports(self):
        a = _make_report(wall_time=10, turns=5, tokens=1000)
        b = _make_report(wall_time=8, turns=3, tokens=800)
        diff = build_trial_diff(a, b, "a.json", "b.json")

        assert diff.label_a == "a.json"
        assert diff.label_b == "b.json"
        assert diff.wall_time.a == 10
        assert diff.wall_time.b == 8
        assert diff.wall_time.delta == -2
        assert diff.turns.a == 5
        assert diff.turns.b == 3
        assert diff.outcome_a == "success"
        assert diff.outcome_b == "success"
        assert diff.model_a == "claude-sonnet"

    def test_token_count_from_timeline(self):
        a = _make_report(tokens=500)
        b = _make_report(tokens=1000)
        diff = build_trial_diff(a, b, "a.json", "b.json")
        assert diff.tokens.a == 500
        assert diff.tokens.b == 1000
        assert diff.tokens.delta == 500

    def test_zero_baseline_pct_is_none(self):
        a = _make_report(wall_time=0, turns=0, compactions=0)
        b = _make_report(wall_time=5, turns=3, compactions=1)
        diff = build_trial_diff(a, b, "a.json", "b.json")
        assert diff.wall_time.pct is None
        assert diff.turns.pct is None
        assert diff.compactions.pct is None

    def test_missing_fields(self):
        a = {"version": 1}
        b = {"version": 1}
        diff = build_trial_diff(a, b, "a.json", "b.json")
        assert diff.wall_time.a == 0
        assert diff.wall_time.b == 0
        assert diff.outcome_a == "unknown"
        assert diff.model_a == "unknown"
        assert diff.tool_usage == []
        assert diff.settings_diff == {}

    def test_malformed_numeric_fields(self):
        a = _make_report()
        a["stats"]["turns"] = "not_a_number"
        a["stats"]["total_llm_time_s"] = None
        a["calibra"]["wall_time_s"] = "broken"
        b = _make_report()
        diff = build_trial_diff(a, b, "a.json", "b.json")
        assert diff.turns.a == 0
        assert diff.llm_time.a == 0
        assert diff.wall_time.a == 0

    def test_disjoint_tool_sets(self):
        a = _make_report(tools={"Read": {"succeeded": 3, "failed": 0}})
        b = _make_report(tools={"Bash": {"succeeded": 5, "failed": 2}})
        diff = build_trial_diff(a, b, "a.json", "b.json")

        tools_by_name = {e.tool: e for e in diff.tool_usage}
        assert "Read" in tools_by_name
        assert "Bash" in tools_by_name
        assert tools_by_name["Read"].only_in == "a"
        assert tools_by_name["Read"].succeeded_a == 3
        assert tools_by_name["Read"].succeeded_b == 0
        assert tools_by_name["Bash"].only_in == "b"
        assert tools_by_name["Bash"].succeeded_b == 5
        assert tools_by_name["Bash"].failed_b == 2
        assert tools_by_name["Bash"].succeeded_a == 0

    def test_overlapping_tool_sets(self):
        a = _make_report(tools={"Read": {"succeeded": 3, "failed": 1}})
        b = _make_report(tools={"Read": {"succeeded": 5, "failed": 0}})
        diff = build_trial_diff(a, b, "a.json", "b.json")
        assert len(diff.tool_usage) == 1
        entry = diff.tool_usage[0]
        assert entry.tool == "Read"
        assert entry.only_in is None
        assert entry.succeeded_a == 3
        assert entry.failed_a == 1
        assert entry.succeeded_b == 5
        assert entry.failed_b == 0

    def test_settings_diff_only_differences(self):
        a = _make_report(settings={"max_turns": 25, "temperature": 0.7, "seed": 42})
        b = _make_report(settings={"max_turns": 50, "temperature": 0.7, "top_p": 0.9})
        diff = build_trial_diff(a, b, "a.json", "b.json")
        assert "temperature" not in diff.settings_diff
        assert diff.settings_diff["max_turns"] == (25, 50)
        assert diff.settings_diff["seed"] == (42, None)
        assert diff.settings_diff["top_p"] == (None, 0.9)

    def test_tool_usage_sorted_by_total_calls(self):
        a = _make_report(
            tools={"Read": {"succeeded": 1, "failed": 0}, "Write": {"succeeded": 10, "failed": 0}}
        )
        b = _make_report(
            tools={"Read": {"succeeded": 1, "failed": 0}, "Write": {"succeeded": 10, "failed": 0}}
        )
        diff = build_trial_diff(a, b, "a.json", "b.json")
        assert diff.tool_usage[0].tool == "Write"
        assert diff.tool_usage[1].tool == "Read"


def _write_report(path, **kwargs):
    report = _make_report(**kwargs)
    path.write_text(json.dumps(report, indent=2))
    return path


@pytest.fixture
def diff_client(tmp_path):
    app = create_app(tmp_path)
    return TestClient(app)


@pytest.fixture
def report_files(tmp_path):
    a = tmp_path / "report_a.json"
    b = tmp_path / "report_b.json"
    _write_report(a, wall_time=10, turns=5, tokens=1000)
    _write_report(b, wall_time=8, turns=3, tokens=800)
    return a, b


class TestDiffRoute:
    def test_200_without_params(self, diff_client):
        r = diff_client.get("/diff")
        assert r.status_code == 200
        assert "Enter two report file paths" in r.text

    def test_picker_form_rendered(self, diff_client):
        r = diff_client.get("/diff")
        assert 'data-test="file-picker"' in r.text
        assert "<input" in r.text

    def test_200_with_valid_files(self, diff_client, report_files):
        a, b = report_files
        r = diff_client.get(f"/diff?a={a}&b={b}")
        assert r.status_code == 200
        assert 'data-test="kpi-tiles"' in r.text

    def test_inputs_prefilled(self, diff_client, report_files):
        a, b = report_files
        r = diff_client.get(f"/diff?a={a}&b={b}")
        assert str(a) in r.text
        assert str(b) in r.text

    def test_nonexistent_file_a(self, diff_client, report_files):
        _, b = report_files
        r = diff_client.get(f"/diff?a=/nonexistent/file.json&b={b}")
        assert r.status_code == 200
        assert 'data-test="error-message"' in r.text
        assert "File A not found" in r.text

    def test_nonexistent_both(self, diff_client):
        r = diff_client.get("/diff?a=/nonexistent/a.json&b=/nonexistent/b.json")
        assert r.status_code == 200
        text = r.text
        assert "File A not found" in text
        assert "File B not found" in text
        a_idx = text.index("File A not found")
        b_idx = text.index("File B not found")
        assert a_idx < b_idx

    def test_inputs_prefilled_on_error(self, diff_client, report_files):
        _, b = report_files
        r = diff_client.get(f"/diff?a=/nonexistent/file.json&b={b}")
        assert "/nonexistent/file.json" in r.text
        assert str(b) in r.text

    def test_invalid_json(self, diff_client, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("not json at all")
        good = tmp_path / "good.json"
        _write_report(good)
        r = diff_client.get(f"/diff?a={bad}&b={good}")
        assert r.status_code == 200
        assert 'data-test="error-message"' in r.text
        assert "File A" in r.text

    def test_non_json_extension(self, diff_client, tmp_path, report_files):
        _, b = report_files
        txt = tmp_path / "report.txt"
        txt.write_text("{}")
        r = diff_client.get(f"/diff?a={txt}&b={b}")
        assert r.status_code == 200
        assert "not a .json file" in r.text

    def test_missing_b_param(self, diff_client, report_files):
        a, _ = report_files
        r = diff_client.get(f"/diff?a={a}")
        assert r.status_code == 200
        assert "File B: no path provided" in r.text

    def test_non_dict_json_root(self, diff_client, tmp_path, report_files):
        _, b = report_files
        arr = tmp_path / "array.json"
        arr.write_text("[1, 2, 3]")
        r = diff_client.get(f"/diff?a={arr}&b={b}")
        assert r.status_code == 200
        assert "not a JSON object" in r.text


class TestDiffTemplateRendering:
    def test_kpi_green_when_b_lower(self, diff_client, tmp_path):
        a = tmp_path / "a.json"
        b = tmp_path / "b.json"
        _write_report(a, wall_time=100, turns=10, tokens=5000)
        _write_report(b, wall_time=50, turns=5, tokens=2000)
        r = diff_client.get(f"/diff?a={a}&b={b}")
        text = r.text
        assert "text-teal-600" in text

    def test_kpi_red_when_b_higher(self, diff_client, tmp_path):
        a = tmp_path / "a.json"
        b = tmp_path / "b.json"
        _write_report(a, wall_time=50, turns=5, tokens=2000)
        _write_report(b, wall_time=100, turns=10, tokens=5000)
        r = diff_client.get(f"/diff?a={a}&b={b}")
        text = r.text
        assert "text-red-600" in text

    def test_kpi_na_when_zero_baseline(self, diff_client, tmp_path):
        a = tmp_path / "a.json"
        b = tmp_path / "b.json"
        _write_report(a, wall_time=0, turns=0, tokens=0, timeline=[])
        _write_report(b, wall_time=5, turns=3, tokens=0, timeline=[])
        r = diff_client.get(f"/diff?a={a}&b={b}")
        assert "(n/a)" in r.text

    def test_settings_diff_rendered(self, diff_client, tmp_path):
        a = tmp_path / "a.json"
        b = tmp_path / "b.json"
        _write_report(a, settings={"max_turns": 25})
        _write_report(b, settings={"max_turns": 50})
        r = diff_client.get(f"/diff?a={a}&b={b}")
        assert 'data-test="settings-diff"' in r.text
        assert "max_turns" in r.text

    def test_settings_diff_hidden_when_identical(self, diff_client, tmp_path):
        a = tmp_path / "a.json"
        b = tmp_path / "b.json"
        _write_report(a, settings={"max_turns": 25})
        _write_report(b, settings={"max_turns": 25})
        r = diff_client.get(f"/diff?a={a}&b={b}")
        assert 'data-test="settings-diff"' not in r.text

    def test_tool_usage_rendered(self, diff_client, tmp_path):
        a = tmp_path / "a.json"
        b = tmp_path / "b.json"
        _write_report(a, tools={"Read": {"succeeded": 5, "failed": 0}})
        _write_report(b, tools={"Read": {"succeeded": 3, "failed": 2}})
        r = diff_client.get(f"/diff?a={a}&b={b}")
        assert 'data-test="tool-usage"' in r.text
        assert "Read" in r.text

    def test_only_in_badge_rendered(self, diff_client, tmp_path):
        a = tmp_path / "a.json"
        b = tmp_path / "b.json"
        _write_report(a, tools={"Read": {"succeeded": 5, "failed": 0}})
        _write_report(b, tools={"Bash": {"succeeded": 3, "failed": 0}})
        r = diff_client.get(f"/diff?a={a}&b={b}")
        assert "A only" in r.text
        assert "B only" in r.text

    def test_raw_json_panels(self, diff_client, report_files):
        a, b = report_files
        r = diff_client.get(f"/diff?a={a}&b={b}")
        assert "raw-json-a" in r.text
        assert "raw-json-b" in r.text

    def test_timelines_rendered(self, diff_client, report_files):
        a, b = report_files
        r = diff_client.get(f"/diff?a={a}&b={b}")
        assert 'data-test="timelines"' in r.text

    def test_provider_rendered(self, diff_client, tmp_path):
        a = tmp_path / "a.json"
        b = tmp_path / "b.json"
        _write_report(a, provider="openrouter", model="claude-sonnet")
        _write_report(b, provider="anthropic", model="claude-haiku")
        r = diff_client.get(f"/diff?a={a}&b={b}")
        assert "openrouter/" in r.text
        assert "anthropic/" in r.text


class TestDiffMalformedData:
    def test_non_dict_tool_calls_by_name(self):
        a = _make_report()
        a["stats"]["tool_calls_by_name"] = ["Read", "Write"]
        b = _make_report()
        diff = build_trial_diff(a, b, "a.json", "b.json")
        for entry in diff.tool_usage:
            if entry.only_in == "b":
                assert entry.succeeded_a == 0

    def test_non_dict_tool_calls_by_name_string(self):
        a = _make_report()
        a["stats"]["tool_calls_by_name"] = "garbage"
        b = _make_report()
        diff = build_trial_diff(a, b, "a.json", "b.json")
        assert isinstance(diff.tool_usage, list)

    def test_non_dict_stats(self):
        a = {"version": 1, "stats": "broken"}
        b = _make_report()
        diff = build_trial_diff(a, b, "a.json", "b.json")
        assert diff.turns.a == 0

    def test_non_dict_settings(self):
        a = {"version": 1, "settings": [1, 2, 3]}
        b = _make_report()
        diff = build_trial_diff(a, b, "a.json", "b.json")
        assert isinstance(diff.settings_diff, dict)

    def test_non_dict_calibra(self):
        a = {"version": 1, "calibra": "nope"}
        b = _make_report()
        diff = build_trial_diff(a, b, "a.json", "b.json")
        assert diff.wall_time.a == 0

    def test_json_extension_case_insensitive(self, diff_client, tmp_path):
        a = tmp_path / "report.JSON"
        b = tmp_path / "report2.JSON"
        _write_report(a)
        _write_report(b)
        r = diff_client.get(f"/diff?a={a}&b={b}")
        assert r.status_code == 200
        assert 'data-test="kpi-tiles"' in r.text


class TestDiffCli:
    def test_nonexistent_file_exits(self, tmp_path):
        good = tmp_path / "good.json"
        _write_report(good)
        with pytest.raises(SystemExit) as exc_info:
            main(["diff", "/nonexistent/file.json", str(good)])
        assert exc_info.value.code == 1

    def test_non_json_extension_exits(self, tmp_path):
        txt = tmp_path / "report.txt"
        txt.write_text("{}")
        good = tmp_path / "good.json"
        _write_report(good)
        with pytest.raises(SystemExit) as exc_info:
            main(["diff", str(txt), str(good)])
        assert exc_info.value.code == 1

    def test_invalid_json_exits(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("not json")
        good = tmp_path / "good.json"
        _write_report(good)
        with pytest.raises(SystemExit) as exc_info:
            main(["diff", str(bad), str(good)])
        assert exc_info.value.code == 1

    def test_json_extension_case_insensitive(self, tmp_path):
        upper = tmp_path / "report.JSON"
        _write_report(upper)
        good = tmp_path / "good.json"
        _write_report(good)
        # Should not raise on extension check; will fail on uvicorn startup
        # but that's after validation passes. We just verify it doesn't exit(1)
        # during validation by mocking uvicorn.
        import unittest.mock

        with unittest.mock.patch("calibra.cli.sys.exit") as mock_exit:
            # Mock uvicorn so the server doesn't start, and threading.Thread
            # so the browser-opening daemon thread never spawns.
            with unittest.mock.patch("uvicorn.run"):
                with unittest.mock.patch("threading.Thread"):
                    try:
                        main(["diff", str(upper), str(good)])
                    except (SystemExit, Exception):
                        pass
            # sys.exit should not have been called with 1 (validation error)
            for call in mock_exit.call_args_list:
                assert call[0][0] != 1

    def test_non_dict_json_root_exits(self, tmp_path):
        arr = tmp_path / "array.json"
        arr.write_text("[1, 2, 3]")
        good = tmp_path / "good.json"
        _write_report(good)
        with pytest.raises(SystemExit) as exc_info:
            main(["diff", str(arr), str(good)])
        assert exc_info.value.code == 1

    def test_export_writes_file(self, report_files, tmp_path):
        a, b = report_files
        out = tmp_path / "output.html"
        main(["diff", str(a), str(b), "--export", str(out)])
        assert out.is_file()

    def test_export_dir_path_exits(self, report_files, tmp_path):
        a, b = report_files
        with pytest.raises(SystemExit):
            main(["diff", str(a), str(b), "--export", str(tmp_path)])

    def test_export_bad_parent_exits(self, report_files, tmp_path):
        a, b = report_files
        out = tmp_path / "nonexistent" / "diff.html"
        with pytest.raises(SystemExit):
            main(["diff", str(a), str(b), "--export", str(out)])


class TestLoadDiffReport:
    def test_valid_file(self, report_files):
        a, _ = report_files
        parsed, raw = load_diff_report(a, "A")
        assert isinstance(parsed, dict)
        assert isinstance(raw, str)
        assert "model" in parsed

    def test_nonexistent(self, tmp_path):
        with pytest.raises(ValueError, match="File A not found"):
            load_diff_report(tmp_path / "missing.json", "A")

    def test_not_json_extension(self, tmp_path):
        p = tmp_path / "report.txt"
        p.write_text("{}")
        with pytest.raises(ValueError, match="not a .json file"):
            load_diff_report(p, "B")

    def test_invalid_json(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("not json")
        with pytest.raises(ValueError, match="File A"):
            load_diff_report(p, "A")

    def test_non_dict_root(self, tmp_path):
        p = tmp_path / "arr.json"
        p.write_text("[1, 2]")
        with pytest.raises(ValueError, match="not a JSON object"):
            load_diff_report(p, "A")


class TestDiffExport:
    def test_produces_html_file(self, report_files, tmp_path):
        a, b = report_files
        out = tmp_path / "diff.html"
        result = export_diff(a, b, out)
        assert result == out
        assert out.is_file()
        html = out.read_text()
        assert "<!DOCTYPE html>" in html

    def test_contains_diff_content(self, report_files, tmp_path):
        a, b = report_files
        out = tmp_path / "diff.html"
        export_diff(a, b, out)
        html = out.read_text()
        assert "report_a.json" in html
        assert "report_b.json" in html
        assert 'data-test="kpi-tiles"' in html

    def test_self_contained_no_static_refs(self, report_files, tmp_path):
        """No external asset references remain — all JS/CSS is inlined."""
        a, b = report_files
        out = tmp_path / "diff.html"
        export_diff(a, b, out)
        html = out.read_text()
        assert not re.search(r'src="[^"]*/static/', html)
        assert not re.search(r'href="[^"]*/static/', html)

    def test_no_file_picker(self, report_files, tmp_path):
        a, b = report_files
        out = tmp_path / "diff.html"
        export_diff(a, b, out)
        html = out.read_text()
        assert 'data-test="file-picker"' not in html

    def test_labels_from_filenames(self, tmp_path):
        a = tmp_path / "trial-alpha.json"
        b = tmp_path / "trial-beta.json"
        _write_report(a)
        _write_report(b)
        out = tmp_path / "diff.html"
        export_diff(a, b, out)
        html = out.read_text()
        assert "trial-alpha.json" in html
        assert "trial-beta.json" in html

    def test_brand_link_inert(self, report_files, tmp_path):
        a, b = report_files
        out = tmp_path / "diff.html"
        export_diff(a, b, out)
        html = out.read_text()
        assert "<span" in html and ">Calibra</span>" in html
        assert not re.search(r"<a [^>]*>Calibra</a>", html)

    def test_export_dir_path_raises(self, report_files, tmp_path):
        a, b = report_files
        with pytest.raises(IsADirectoryError):
            export_diff(a, b, tmp_path)

    def test_export_bad_parent_raises(self, report_files, tmp_path):
        a, b = report_files
        with pytest.raises(FileNotFoundError, match="Parent directory"):
            export_diff(a, b, tmp_path / "nonexistent" / "diff.html")
