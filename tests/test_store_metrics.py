"""Tests for src/store_metrics.py."""

import argparse
import csv
import os
from datetime import date
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest


@pytest.fixture
def sample_csv(tmp_path):
    rows = [
        {
            "ORGANIZATION_ID": "org-1",
            "ORGANIZATION_NAME": "my-org",
            "PROJECT_ID": "proj-1",
            "PROJECT_NAME": "my-project",
            "PIPELINE_ID": "pipe-1",
            "PIPELINE_NUMBER": "1",
            "PIPELINE_CREATED_AT": "2024-01-01 12:00:00",
            "WORKFLOW_ID": "wf-1",
            "WORKFLOW_NAME": "build",
            "IS_WORKFLOW_SUCCESSFUL": "true",
            "JOB_ID": "job-1",
            "JOB_NAME": "build",
            "JOB_BUILD_STATUS": "success",
            "JOB_RUN_NUMBER": "1",
            "JOB_RUN_STARTED_AT": "2024-01-01 12:01:00",
            "JOB_RUN_STOPPED_AT": "2024-01-01 12:02:00",
            "JOB_RUN_SECONDS": "60",
            "RESOURCE_CLASS": "medium",
            "EXECUTOR": "docker",
            "OPERATING_SYSTEM": "linux",
            "TOTAL_CREDITS": "10.5",
            "COMPUTE_CREDITS": "10.5",
            "USER_CREDITS": "0",
            "DLC_CREDITS": "0",
            "PARALLELISM": "1",
            "VCS_BRANCH": "main",
            "MEDIAN_CPU_UTILIZATION_PCT": "40",
            "MEDIAN_RAM_UTILIZATION_PCT": "50",
        }
    ]
    path = tmp_path / "usage.csv"
    with open(path, "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    return str(path)


class TestMetricsStore:

    def test_raises_without_database_url(self):
        from src.store_metrics import MetricsStore
        with pytest.raises(ValueError, match="Database URL"):
            MetricsStore(database_url=None)

    def test_process_csv_loads_rows(self, sample_csv):
        from src.store_metrics import MetricsStore
        store = MetricsStore(database_url="postgresql://usage:usage@localhost/usage")
        df = store.process_csv(sample_csv)
        assert len(df) == 1
        assert df.iloc[0]["PROJECT_NAME"] == "my-project"

    @patch("prometheus_client.push_to_gateway")
    @patch("src.store_metrics.psycopg.connect")
    def test_store_inserts_rows(self, mock_connect, mock_push, sample_csv):
        from src.store_metrics import MetricsStore

        mock_conn = MagicMock()
        mock_tx = MagicMock()
        mock_conn.transaction.return_value.__enter__.return_value = None
        mock_conn.transaction.return_value.__exit__.return_value = False
        mock_connect.return_value.__enter__.return_value = mock_conn
        mock_connect.return_value.__exit__.return_value = False
        mock_conn.execute.return_value.fetchone.side_effect = [
            None,
            {"id": 42},
        ]

        store = MetricsStore(
            database_url="postgresql://usage:usage@localhost/usage",
            pushgateway_url="http://localhost:9091",
        )
        df = store.process_csv(sample_csv)
        result = store.store(
            df,
            week_start=date(2024, 1, 1),
            week_end=date(2024, 1, 8),
            org_id="org-1",
        )
        assert result["report_week_id"] == 42
        assert result["job_count"] == 1
        mock_push.assert_called_once()


class TestStoreMetricsParser:

    def test_add_arguments_registers_flags(self):
        from src.store_metrics import _add_arguments
        parser = argparse.ArgumentParser()
        _add_arguments(parser)
        args = parser.parse_args([
            "usage.csv",
            "--database-url",
            "postgresql://localhost/db",
            "--previous-week",
            "--dry-run",
        ])
        assert args.csv_file == "usage.csv"
        assert args.dry_run is True
        assert args.previous_week is True

    def test_dry_run_returns_0(self, sample_csv):
        from src.store_metrics import handle
        args = argparse.Namespace(
            csv_file=sample_csv,
            database_url="postgresql://usage:usage@localhost/usage",
            pushgateway_url=None,
            week_start=None,
            week_end=None,
            previous_week=True,
            org_id="org-1",
            credit_cost=0.0006,
            replace=True,
            dry_run=True,
        )
        assert handle(args) == 0

    def test_missing_week_dates_returns_1(self, sample_csv):
        from src.store_metrics import handle
        args = argparse.Namespace(
            csv_file=sample_csv,
            database_url="postgresql://usage:usage@localhost/usage",
            pushgateway_url=None,
            week_start=None,
            week_end=None,
            previous_week=False,
            org_id="org-1",
            credit_cost=0.0006,
            replace=True,
            dry_run=True,
        )
        assert handle(args) == 1

    def test_standalone_main_help(self):
        from src.store_metrics import main
        with pytest.raises(SystemExit) as exc:
            with patch("sys.argv", ["store-metrics", "--help"]):
                main()
        assert exc.value.code == 0
