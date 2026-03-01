"""Tests for verbose formatting functions."""

from calibra.verbose import format_progress_header, format_trial_detail, format_trial_line


SAMPLE_REPORT = {
    "version": 1,
    "result": {"outcome": "success", "exit_code": 0},
    "stats": {
        "turns": 2,
        "tool_calls_total": 1,
        "tool_calls_succeeded": 1,
        "tool_calls_failed": 0,
        "tool_calls_by_name": {"write_file": {"succeeded": 1, "failed": 0}},
        "compactions": 0,
        "llm_calls": 2,
        "total_llm_time_s": 6.647,
        "total_tool_time_s": 0.002,
    },
    "timeline": [
        {
            "turn": 1,
            "type": "llm_call",
            "duration_s": 3.586,
            "prompt_tokens_est": 3706,
            "finish_reason": "tool_calls",
            "is_retry": False,
        },
        {
            "turn": 1,
            "type": "tool_call",
            "name": "write_file",
            "succeeded": True,
            "duration_s": 0.002,
        },
        {
            "turn": 2,
            "type": "llm_call",
            "duration_s": 3.062,
            "prompt_tokens_est": 3772,
            "finish_reason": "stop",
            "is_retry": False,
        },
    ],
}


def test_format_progress_header_verbose():
    assert format_progress_header(10, 2, True) == "Running 10 trials with 2 worker(s) (verbose)..."


def test_format_progress_header_quiet():
    assert format_progress_header(5, 1, False) == "Running 5 trials with 1 worker(s)..."


def test_format_trial_line_with_report():
    line = format_trial_line(
        status="PASS",
        task_name="hello-world",
        variant_label="claude-sonnet_default_none_none_base",
        repeat_index=0,
        wall_time_s=6.8,
        report=SAMPLE_REPORT,
        completed=1,
        total=6,
        passed=1,
        failed=0,
    )
    assert "[1/6]" in line
    assert "[PASS]" in line
    assert "hello-world" in line
    assert "6.8s" in line
    assert "2 turns" in line
    assert "1 tools" in line
    assert "tok" in line
    assert "[1P/0F]" in line


def test_format_trial_line_without_report():
    line = format_trial_line(
        status="INFRA",
        task_name="fizzbuzz",
        variant_label="my-variant",
        repeat_index=1,
        wall_time_s=2.3,
        report=None,
        completed=3,
        total=10,
        passed=2,
        failed=1,
    )
    assert "[3/10]" in line
    assert "[INFRA]" in line
    assert "2.3s" in line
    assert "turns" not in line
    assert "[2P/1F]" in line


def test_format_trial_detail_with_report():
    detail = format_trial_detail(SAMPLE_REPORT)
    assert "outcome=success" in detail
    assert "llm_time=6.6s" in detail
    assert "tool_time=0.0s" in detail
    assert "compactions=0" in detail
    assert "turn 1: LLM 3.6s" in detail
    assert "-> tool_calls" in detail
    assert "turn 1: tool write_file" in detail
    assert "[ok]" in detail
    assert "turn 2: LLM 3.1s" in detail
    assert "-> stop" in detail
    assert "tools: write_file=1/1" in detail


def test_format_trial_detail_no_report():
    assert format_trial_detail(None) == ""


def test_format_trial_detail_no_report_with_stderr():
    detail = format_trial_detail(None, stderr_capture="some error output")
    assert "stderr:" in detail
    assert "some error output" in detail


def test_format_trial_detail_failed_tool():
    report = {
        "result": {"outcome": "error"},
        "stats": {
            "turns": 1,
            "total_llm_time_s": 1.0,
            "total_tool_time_s": 0.5,
            "compactions": 0,
            "tool_calls_by_name": {"bash": {"succeeded": 0, "failed": 1}},
        },
        "timeline": [
            {
                "turn": 1,
                "type": "tool_call",
                "name": "bash",
                "succeeded": False,
                "duration_s": 0.5,
            }
        ],
    }
    detail = format_trial_detail(report)
    assert "[FAIL]" in detail
    assert "bash=0/1" in detail


def test_format_trial_detail_compaction_event():
    report = {
        "result": {"outcome": "success"},
        "stats": {
            "turns": 1,
            "total_llm_time_s": 1.0,
            "total_tool_time_s": 0.0,
            "compactions": 1,
            "tool_calls_by_name": {},
        },
        "timeline": [
            {"turn": 3, "type": "compaction"},
        ],
    }
    detail = format_trial_detail(report)
    assert "turn 3: compaction" in detail


def test_format_trial_line_token_formatting():
    report = {
        "stats": {"turns": 1, "tool_calls_total": 0},
        "timeline": [
            {"type": "llm_call", "prompt_tokens_est": 500},
        ],
    }
    line = format_trial_line("PASS", "t", "v", 0, 1.0, report, 1, 1, 1, 0)
    assert "500 tok" in line

    report_large = {
        "stats": {"turns": 1, "tool_calls_total": 0},
        "timeline": [
            {"type": "llm_call", "prompt_tokens_est": 7500},
        ],
    }
    line2 = format_trial_line("PASS", "t", "v", 0, 1.0, report_large, 1, 1, 1, 0)
    assert "7.5k tok" in line2
