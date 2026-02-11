"""Tests for web security: path validation and traversal prevention."""

import json

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from calibra.web import create_app
from calibra.web.security import validate_path, validate_segment


@pytest.fixture
def results_dir(tmp_path):
    campaign = tmp_path / "test-campaign" / "hello"
    campaign.mkdir(parents=True)
    report = {
        "version": 1,
        "result": {"outcome": "success"},
        "stats": {
            "turns": 3,
            "tool_calls_total": 2,
            "tool_calls_succeeded": 2,
            "tool_calls_failed": 0,
            "tool_calls_by_name": {},
            "total_llm_time_s": 1.0,
            "total_tool_time_s": 0.1,
            "compactions": 0,
            "skills_used": [],
            "guardrail_interventions": 0,
        },
        "timeline": [{"type": "llm_call", "prompt_tokens_est": 500}],
        "calibra": {
            "task": "hello",
            "variant": "v1_default_none_none_base",
            "repeat": 0,
            "wall_time_s": 1.1,
            "verified": True,
            "config_hash": "abc",
        },
    }
    (campaign / "v1_default_none_none_base_0.json").write_text(json.dumps(report, indent=2))

    summary = {
        "variants": [
            {
                "variant_label": "v1_default_none_none_base",
                "n_trials": 1,
                "pass_rate": 1.0,
                "outcome_counts": {"success": 1},
                "turns": {
                    "mean": 3,
                    "median": 3,
                    "std": 0,
                    "min": 3,
                    "max": 3,
                    "p90": 3,
                    "ci_lower": 3,
                    "ci_upper": 3,
                },
                "tool_calls_total": {
                    "mean": 2,
                    "median": 2,
                    "std": 0,
                    "min": 2,
                    "max": 2,
                    "p90": 2,
                    "ci_lower": 2,
                    "ci_upper": 2,
                },
                "tool_calls_failed": {
                    "mean": 0,
                    "median": 0,
                    "std": 0,
                    "min": 0,
                    "max": 0,
                    "p90": 0,
                    "ci_lower": 0,
                    "ci_upper": 0,
                },
                "llm_time_s": {
                    "mean": 1,
                    "median": 1,
                    "std": 0,
                    "min": 1,
                    "max": 1,
                    "p90": 1,
                    "ci_lower": 1,
                    "ci_upper": 1,
                },
                "tool_time_s": {
                    "mean": 0.1,
                    "median": 0.1,
                    "std": 0,
                    "min": 0.1,
                    "max": 0.1,
                    "p90": 0.1,
                    "ci_lower": 0.1,
                    "ci_upper": 0.1,
                },
                "wall_time_s": {
                    "mean": 1.1,
                    "median": 1.1,
                    "std": 0,
                    "min": 1.1,
                    "max": 1.1,
                    "p90": 1.1,
                    "ci_lower": 1.1,
                    "ci_upper": 1.1,
                },
                "compactions": {
                    "mean": 0,
                    "median": 0,
                    "std": 0,
                    "min": 0,
                    "max": 0,
                    "p90": 0,
                    "ci_lower": 0,
                    "ci_upper": 0,
                },
                "prompt_tokens_est": {
                    "mean": 500,
                    "median": 500,
                    "std": 0,
                    "min": 500,
                    "max": 500,
                    "p90": 500,
                    "ci_lower": 500,
                    "ci_upper": 500,
                },
                "score_per_1k_tokens": 2.0,
                "pass_rate_per_minute": 54.5,
            }
        ],
        "trials": [
            {
                "task": "hello",
                "variant_label": "v1_default_none_none_base",
                "outcome": "success",
                "verified": True,
                "turns": 3,
                "tool_calls_total": 2,
                "tool_calls_failed": 0,
                "tool_calls_by_name": {},
                "llm_time_s": 1.0,
                "tool_time_s": 0.1,
                "wall_time_s": 1.1,
                "compactions": 0,
                "prompt_tokens_est": 500,
                "skills_used": [],
                "guardrail_interventions": 0,
                "failure_class": None,
            }
        ],
    }
    (tmp_path / "test-campaign" / "summary.json").write_text(json.dumps(summary, indent=2))
    return tmp_path


@pytest.fixture
def client(results_dir):
    app = create_app(results_dir)
    return TestClient(app)


class TestSegmentValidation:
    def test_valid_segments(self):
        assert validate_segment("hello-world") == "hello-world"
        assert validate_segment("v1_default_none_none_base") == "v1_default_none_none_base"
        assert validate_segment("model-shootout") == "model-shootout"
        assert validate_segment("0") == "0"
        assert validate_segment("test.v2") == "test.v2"

    def test_rejects_dot_dot(self):
        with pytest.raises(HTTPException) as exc_info:
            validate_segment("..")
        assert exc_info.value.status_code == 400

    def test_rejects_slash(self):
        with pytest.raises(HTTPException) as exc_info:
            validate_segment("foo/bar")
        assert exc_info.value.status_code == 400

    def test_rejects_empty(self):
        with pytest.raises(HTTPException) as exc_info:
            validate_segment("")
        assert exc_info.value.status_code == 400

    def test_rejects_leading_dot(self):
        with pytest.raises(HTTPException) as exc_info:
            validate_segment(".hidden")
        assert exc_info.value.status_code == 400

    def test_rejects_spaces(self):
        with pytest.raises(HTTPException) as exc_info:
            validate_segment("foo bar")
        assert exc_info.value.status_code == 400

    def test_rejects_encoded_traversal(self):
        with pytest.raises(HTTPException) as exc_info:
            validate_segment("..%2f")
        assert exc_info.value.status_code == 400


class TestPathContainment:
    def test_valid_path(self, results_dir):
        path = validate_path(results_dir, "test-campaign", "summary.json")
        assert path.exists()

    def test_nonexistent_returns_404(self, results_dir):
        with pytest.raises(HTTPException) as exc_info:
            validate_path(results_dir, "nonexistent")
        assert exc_info.value.status_code == 404

    def test_symlink_escape(self, results_dir):
        escape_target = results_dir.parent / "secret.txt"
        escape_target.write_text("secret")
        link = results_dir / "evil-link"
        link.symlink_to(escape_target)
        with pytest.raises(HTTPException) as exc_info:
            validate_path(results_dir, "evil-link")
        assert exc_info.value.status_code == 400

    def test_same_prefix_escape(self, results_dir):
        """Ensure /tmp/results-evil is not accepted when root is /tmp/results."""
        evil_dir = results_dir.parent / (results_dir.name + "-evil")
        evil_dir.mkdir()
        secret = evil_dir / "gotcha.txt"
        secret.write_text("pwned")
        link = results_dir / "escape"
        link.symlink_to(evil_dir)
        with pytest.raises(HTTPException) as exc_info:
            validate_path(results_dir, "escape", "gotcha.txt")
        assert exc_info.value.status_code == 400


class TestAPITraversalPrevention:
    def test_campaign_traversal_encoded(self, client):
        r = client.get("/api/campaign/..%2f..%2fetc%2fpasswd")
        assert r.status_code in (400, 404)

    def test_campaign_traversal_dotdot(self, client):
        r = client.get("/api/campaign/..")
        assert r.status_code in (400, 404)  # Starlette normalizes .. before routing

    def test_trial_traversal_encoded(self, client):
        r = client.get("/api/campaign/test-campaign/trial/hello/..%2f..%2fetc/0")
        assert r.status_code in (400, 404)

    def test_trial_traversal_dotdot(self, client):
        r = client.get("/api/campaign/test-campaign/trial/../../../etc/passwd/0")
        assert r.status_code in (400, 404)

    def test_trial_dot_dot_variant(self, client):
        r = client.get("/api/campaign/test-campaign/trial/hello/../0")
        assert r.status_code in (400, 404, 422)

    def test_nonexistent_campaign(self, client):
        r = client.get("/api/campaign/nonexistent")
        assert r.status_code == 404

    def test_nonexistent_trial(self, client):
        r = client.get("/api/campaign/test-campaign/trial/hello/nonexistent/0")
        assert r.status_code == 404


class TestValidRoutes:
    def test_home(self, client):
        r = client.get("/")
        assert r.status_code == 200
        assert "Calibra" in r.text

    def test_campaigns_api(self, client):
        r = client.get("/api/campaigns")
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 1
        assert data[0]["name"] == "test-campaign"

    def test_campaign_api(self, client):
        r = client.get("/api/campaign/test-campaign")
        assert r.status_code == 200
        data = r.json()
        assert "variants" in data
        assert "trials" in data

    def test_heatmap_api(self, client):
        r = client.get("/api/campaign/test-campaign/heatmap")
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 1
        assert data[0]["task"] == "hello"
        assert data[0]["pass_rate"] == 1.0

    def test_trial_api(self, client):
        r = client.get("/api/campaign/test-campaign/trial/hello/v1_default_none_none_base/0")
        assert r.status_code == 200
        data = r.json()
        assert data["calibra"]["task"] == "hello"

    def test_reload_api(self, client):
        r = client.post("/api/reload")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"


class TestEmptyResultsDir:
    def test_empty_dir(self, tmp_path):
        app = create_app(tmp_path)
        c = TestClient(app)

        r = c.get("/")
        assert r.status_code == 200

        r = c.get("/api/campaigns")
        assert r.status_code == 200
        assert r.json() == []
