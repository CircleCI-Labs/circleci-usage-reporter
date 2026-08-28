"""Unit tests for top-workflows and top-jobs. These must not call the live Usage API."""

import argparse
import os
import shutil
from datetime import date
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

AUTH_ENV_VARS = (
    "CIRCLECI_API_TOKEN",
    "CIRCLE_TOKEN",
    "CIRCLECI_TOKEN",
    "CIRCLE_ORGANIZATION_ID",
    "ORG_ID",
    "CIRCLE_PROJECT_ID",
)

from src.aggregations import load_usage_dataframe
from src.cli import create_parser
from src.top import (
    CACHE_REUSED_NOTE,
    DISCLAIMER,
    RATE_LIMIT_BLOCK,
    cache_csv_path,
    ensure_usage_csv,
    filter_project,
    format_duration,
    handle,
    org_last_export_path,
    rank_jobs,
    rank_workflows,
    resolve_date_range,
    resolve_org_id_from_project,
    write_export_timestamps,
)

SAMPLE_CSV = os.path.join(
    os.path.dirname(__file__),
    "..",
    "examples",
    "observability",
    "fixtures",
    "sample_usage.csv",
)


@pytest.fixture(autouse=True)
def isolated_auth_env(monkeypatch):
    for name in AUTH_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def sample_df():
    return load_usage_dataframe(SAMPLE_CSV)


@pytest.fixture
def cache_dir(tmp_path, monkeypatch):
    directory = str(tmp_path / "cache")
    os.makedirs(directory, exist_ok=True)
    monkeypatch.setattr("src.top.TEMP_DIR_BASE", directory)
    return directory


def _args(**overrides):
    values = dict(
        command="top-workflows",
        project_id="proj-alpha",
        org_id="org-demo",
        api_token="test-token",
        start_date="2026-06-10",
        end_date="2026-06-14",
        days=30,
        limit=10,
    )
    values.update(overrides)
    return argparse.Namespace(**values)


class TestCLIParsing:
    def test_top_workflows_defaults(self):
        parser = create_parser()
        args = parser.parse_args(["top-workflows", "--project-id", "abc"])
        assert args.command == "top-workflows"
        assert args.project_id == "abc"
        assert args.days == 30
        assert args.limit == 10
        assert args.start_date is None
        assert args.end_date is None

    def test_top_jobs_accepts_dates_and_limit(self):
        parser = create_parser()
        args = parser.parse_args([
            "top-jobs",
            "--project-id", "abc",
            "--start-date", "2026-01-01",
            "--end-date", "2026-01-15",
            "--limit", "5",
            "--days", "14",
        ])
        assert args.command == "top-jobs"
        assert args.start_date == "2026-01-01"
        assert args.end_date == "2026-01-15"
        assert args.limit == 5
        assert args.days == 14

    def test_help_exits_zero(self):
        parser = create_parser()
        with pytest.raises(SystemExit) as exc:
            parser.parse_args(["top-workflows", "--help"])
        assert exc.value.code == 0


class TestDateRange:
    def test_default_days_uses_utc_today(self, monkeypatch):
        monkeypatch.setattr("src.top._today", lambda: date(2026, 8, 27))
        start, end = resolve_date_range(None, None, 30)
        assert start == "2026-07-28"
        assert end == "2026-08-27"

    def test_rejects_window_over_32_days(self):
        start, end = resolve_date_range("2026-01-01", "2026-03-01", 30)
        assert start is None
        assert end is None

    def test_requires_both_dates(self):
        start, end = resolve_date_range("2026-01-01", None, 30)
        assert start is None
        assert end is None


class TestRanking:
    def test_workflows_group_by_name_and_nunique_ids(self, sample_df):
        project = filter_project(sample_df, "proj-alpha")
        ranked = rank_workflows(project, limit=10)
        assert list(ranked["WORKFLOW_NAME"]) == ["build"]
        assert ranked.iloc[0]["CREDITS"] == pytest.approx(68.5)
        assert ranked.iloc[0]["RUNS"] == 2

    def test_workflow_duration_is_per_workflow_id_not_summed_job_seconds(self, sample_df):
        project = filter_project(sample_df, "proj-alpha")
        ranked = rank_workflows(project, limit=10)
        # wf-101 wall clock 09:01-09:20 = 1140s; wf-102 = 120s; not 240+840+120=1200
        assert ranked.iloc[0]["DURATION_SECONDS"] == pytest.approx(1260)

    def test_parallel_jobs_do_not_double_count_workflow_duration(self):
        df = pd.DataFrame([
            {
                "WORKFLOW_ID": "wf-1",
                "WORKFLOW_NAME": "ci",
                "JOB_ID": "job-a",
                "JOB_NAME": "a",
                "TOTAL_CREDITS": 100,
                "JOB_RUN_SECONDS": 1000,
                "JOB_RUN_STARTED_AT": "2026-06-10 10:00:00",
                "JOB_RUN_STOPPED_AT": "2026-06-10 10:16:40",
            },
            {
                "WORKFLOW_ID": "wf-1",
                "WORKFLOW_NAME": "ci",
                "JOB_ID": "job-b",
                "JOB_NAME": "b",
                "TOTAL_CREDITS": 50,
                "JOB_RUN_SECONDS": 1000,
                "JOB_RUN_STARTED_AT": "2026-06-10 10:00:00",
                "JOB_RUN_STOPPED_AT": "2026-06-10 10:16:40",
            },
        ])
        ranked = rank_workflows(df, limit=10)
        assert ranked.iloc[0]["CREDITS"] == pytest.approx(150)
        assert ranked.iloc[0]["RUNS"] == 1
        assert ranked.iloc[0]["DURATION_SECONDS"] == pytest.approx(1000)

    def test_jobs_rank_by_credits_and_count_runs(self, sample_df):
        project = filter_project(sample_df, "proj-alpha")
        ranked = rank_jobs(project, limit=10)
        assert list(ranked["JOB_NAME"]) == ["integration_tests", "unit_tests"]
        assert ranked.iloc[0]["CREDITS"] == pytest.approx(48.0)
        assert ranked.iloc[0]["RUNS"] == 1
        assert ranked.iloc[1]["CREDITS"] == pytest.approx(20.5)
        assert ranked.iloc[1]["RUNS"] == 2
        assert ranked.iloc[1]["DURATION_SECONDS"] == pytest.approx(360)

    def test_limit_truncates(self, sample_df):
        project = filter_project(sample_df, "proj-beta")
        ranked = rank_jobs(project, limit=1)
        assert len(ranked) == 1
        assert ranked.iloc[0]["JOB_NAME"] == "snyk_scan"

    def test_empty_dataframe_returns_empty_ranking(self):
        empty = pd.DataFrame(columns=["WORKFLOW_NAME", "WORKFLOW_ID", "TOTAL_CREDITS"])
        assert rank_workflows(empty).empty
        assert rank_jobs(empty).empty

    def test_format_duration(self):
        assert format_duration(1260) == "00:21:00"
        assert format_duration(None) == "--"


class TestCacheAndHandle:
    def test_handle_reuses_cache_and_does_not_export(
        self, cache_dir, capsys, sample_df
    ):
        csv_path = cache_csv_path("org-demo", "2026-06-10", "2026-06-14", cache_dir)
        shutil.copy(SAMPLE_CSV, csv_path)

        with patch("src.top.export_usage_report") as export:
            result = handle(_args())

        assert result == 0
        export.assert_not_called()
        out = capsys.readouterr().out
        assert DISCLAIMER in out.splitlines()[0]
        assert CACHE_REUSED_NOTE in out
        assert "build" in out
        assert csv_path not in out
        assert "sample_usage.csv" not in out

    def test_second_command_shares_one_export(self, cache_dir, capsys):
        def fake_export(org_id, api_token, start_date, end_date, output, quiet=False):
            shutil.copy(SAMPLE_CSV, output)
            return 0

        with patch("src.top.export_usage_report", side_effect=fake_export) as export:
            first = handle(_args(command="top-workflows"))
            second = handle(_args(command="top-jobs"))

        assert first == 0
        assert second == 0
        assert export.call_count == 1
        out = capsys.readouterr().out
        assert CACHE_REUSED_NOTE in out
        assert "unit_tests" in out
        assert cache_csv_path("org-demo", "2026-06-10", "2026-06-14", cache_dir) not in out

    def test_empty_project_prints_empty_state(self, cache_dir, capsys):
        csv_path = cache_csv_path("org-demo", "2026-06-10", "2026-06-14", cache_dir)
        shutil.copy(SAMPLE_CSV, csv_path)

        result = handle(_args(project_id="proj-missing"))
        assert result == 0
        out = capsys.readouterr().out
        assert "No usage data found for project proj-missing" in out
        assert "WORKFLOW_NAME" not in out

    def test_rate_limit_fails_without_cache(self, cache_dir, capsys):
        write_export_timestamps("org-demo", "2026-06-01", "2026-06-02", cache_dir)

        with patch("src.top.export_usage_report") as export:
            result = handle(_args())

        assert result == 1
        export.assert_not_called()
        err = capsys.readouterr().err
        assert "10 per hour" in err
        assert RATE_LIMIT_BLOCK in err

    def test_ensure_usage_csv_writes_timestamp_after_export(self, cache_dir):
        def fake_export(org_id, api_token, start_date, end_date, output, quiet=False):
            shutil.copy(SAMPLE_CSV, output)
            return 0

        with patch("src.top.export_usage_report", side_effect=fake_export):
            path, reused = ensure_usage_csv(
                "org-demo", "token", "2026-06-10", "2026-06-14", cache_dir
            )

        assert reused is False
        assert os.path.exists(path)
        assert os.path.exists(org_last_export_path("org-demo", cache_dir))

    def test_resolves_project_and_token_from_env(self, cache_dir, monkeypatch, capsys):
        csv_path = cache_csv_path("org-demo", "2026-06-10", "2026-06-14", cache_dir)
        shutil.copy(SAMPLE_CSV, csv_path)
        monkeypatch.setenv("CIRCLE_PROJECT_ID", "proj-alpha")
        monkeypatch.setenv("CIRCLE_TOKEN", "env-token")
        monkeypatch.delenv("CIRCLECI_API_TOKEN", raising=False)
        monkeypatch.delenv("CIRCLECI_TOKEN", raising=False)

        result = handle(_args(project_id=None, api_token=None))
        assert result == 0
        assert "build" in capsys.readouterr().out

    def test_resolves_org_from_project_api(self, cache_dir, capsys):
        csv_path = cache_csv_path("resolved-org", "2026-06-10", "2026-06-14", cache_dir)
        shutil.copy(SAMPLE_CSV, csv_path)
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {"references": {"org": {"id": "resolved-org"}}}
        }

        with patch("src.top.requests.get", return_value=mock_response) as get:
            result = handle(_args(org_id=None))

        assert result == 0
        get.assert_called()
        assert "circleci.com/api/v3/projects/proj-alpha" in get.call_args[0][0]
        assert "build" in capsys.readouterr().out

    def test_missing_token_does_not_call_usage_api(self, capsys):
        with patch("src.top.export_usage_report") as export:
            result = handle(_args(api_token=None))
        assert result == 1
        export.assert_not_called()
        assert DISCLAIMER in capsys.readouterr().out


class TestOrgLookup:
    def test_v3_payload(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {"references": {"org": {"id": "org-from-v3"}}}
        }
        with patch("src.top.requests.get", return_value=mock_response):
            assert resolve_org_id_from_project("proj", "token") == "org-from-v3"

    def test_v2_fallback(self):
        v3 = MagicMock()
        v3.status_code = 404
        v2 = MagicMock()
        v2.status_code = 200
        v2.json.return_value = {"organization_id": "org-from-v2"}
        with patch("src.top.requests.get", side_effect=[v3, v2]):
            assert resolve_org_id_from_project("proj", "token") == "org-from-v2"
