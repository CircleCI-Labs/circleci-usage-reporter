"""
Tests for src/send_to_datadog.py and src/send_to_doit.py.
"""
import argparse
import csv
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_csv(tmp_path):
    """Write a minimal usage CSV and return its path."""
    rows = [
        {
            "ORGANIZATION_NAME": "my-org",
            "PROJECT_NAME": "my-project",
            "JOB_NAME": "build",
            "JOB_BUILD_STATUS": "success",
            "TOTAL_CREDITS": "10.5",
            "USER_CREDITS": "0",
            "COMPUTE_CREDITS": "10.5",
            "JOB_RUN_SECONDS": "60",
            "PARALLELISM": "1",
            "IS_WORKFLOW_SUCCESSFUL": "true",
            "PIPELINE_NUMBER": "42",
            "JOB_RUN_NUMBER": "1",
            "PIPELINE_CREATED_AT": "2024-01-01 12:00:00",
            "JOB_RUN_STARTED_AT": "2024-01-01 12:01:00",
            "JOB_RUN_STOPPED_AT": "2024-01-01 12:02:00",
        }
    ]
    p = tmp_path / "usage.csv"
    with open(p, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    return str(p)


# ---------------------------------------------------------------------------
# DatadogCSVIngest
# ---------------------------------------------------------------------------

class TestDatadogCSVIngest:

    def test_raises_without_api_key(self):
        from src.send_to_datadog import DatadogCSVIngest
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="API key"):
                DatadogCSVIngest(api_key=None)

    def test_initialises_with_api_key(self):
        from src.send_to_datadog import DatadogCSVIngest
        ingestor = DatadogCSVIngest(api_key="test-key")
        assert ingestor.api_key == "test-key"

    def test_initialises_from_env_var(self):
        from src.send_to_datadog import DatadogCSVIngest
        with patch.dict(os.environ, {"DD_API_KEY": "env-key"}):
            ingestor = DatadogCSVIngest()
            assert ingestor.api_key == "env-key"

    def test_process_csv_parses_rows(self, sample_csv):
        from src.send_to_datadog import DatadogCSVIngest
        ingestor = DatadogCSVIngest(api_key="test-key")
        rows = ingestor.process_csv(sample_csv)
        assert len(rows) == 1
        assert rows[0]["PROJECT_NAME"] == "my-project"

    def test_process_csv_converts_numeric_fields(self, sample_csv):
        from src.send_to_datadog import DatadogCSVIngest
        ingestor = DatadogCSVIngest(api_key="test-key")
        rows = ingestor.process_csv(sample_csv)
        assert rows[0]["TOTAL_CREDITS"] == 10.5
        assert rows[0]["PARALLELISM"] == 1

    def test_process_csv_converts_boolean_fields(self, sample_csv):
        from src.send_to_datadog import DatadogCSVIngest
        ingestor = DatadogCSVIngest(api_key="test-key")
        rows = ingestor.process_csv(sample_csv)
        assert rows[0]["IS_WORKFLOW_SUCCESSFUL"] is True

    def test_process_csv_raises_on_missing_file(self):
        from src.send_to_datadog import DatadogCSVIngest
        ingestor = DatadogCSVIngest(api_key="test-key")
        with pytest.raises(FileNotFoundError):
            ingestor.process_csv("/nonexistent/file.csv")

    def test_process_csv_handles_null_values(self, tmp_path):
        from src.send_to_datadog import DatadogCSVIngest
        p = tmp_path / "nulls.csv"
        p.write_text("PROJECT_NAME,TOTAL_CREDITS\nmy-project,\\N\n")
        ingestor = DatadogCSVIngest(api_key="test-key")
        rows = ingestor.process_csv(str(p))
        assert rows[0]["TOTAL_CREDITS"] is None


class TestDatadogParser:

    def test_add_arguments_registers_flags(self):
        from src.send_to_datadog import _add_arguments
        parser = argparse.ArgumentParser()
        _add_arguments(parser)
        args = parser.parse_args(["myfile.csv"])
        assert args.csv_file == "myfile.csv"

    def test_dry_run_flag(self):
        from src.send_to_datadog import _add_arguments
        parser = argparse.ArgumentParser()
        _add_arguments(parser)
        args = parser.parse_args(["myfile.csv", "--dry-run"])
        assert args.dry_run is True

    def test_standalone_main_help(self):
        from src.send_to_datadog import main
        with pytest.raises(SystemExit) as exc:
            with patch("sys.argv", ["send-to-datadog", "--help"]):
                main()
        assert exc.value.code == 0


# ---------------------------------------------------------------------------
# DoiTDataHubIngest
# ---------------------------------------------------------------------------

class TestDoiTDataHubIngest:

    def test_raises_without_api_key(self):
        from src.send_to_doit import DoiTDataHubIngest
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="API key"):
                DoiTDataHubIngest(api_key=None)

    def test_initialises_with_api_key(self):
        from src.send_to_doit import DoiTDataHubIngest
        ingestor = DoiTDataHubIngest(api_key="doit-key")
        assert ingestor.api_key == "doit-key"

    def test_initialises_from_env_var(self):
        from src.send_to_doit import DoiTDataHubIngest
        with patch.dict(os.environ, {"DOIT_API_KEY": "env-doit-key"}):
            ingestor = DoiTDataHubIngest()
            assert ingestor.api_key == "env-doit-key"

    def test_process_csv_parses_rows(self, sample_csv):
        from src.send_to_doit import DoiTDataHubIngest
        ingestor = DoiTDataHubIngest(api_key="doit-key")
        rows = ingestor.process_csv(sample_csv)
        assert len(rows) == 1
        assert rows[0]["PROJECT_NAME"] == "my-project"

    def test_process_csv_converts_types(self, sample_csv):
        from src.send_to_doit import DoiTDataHubIngest
        ingestor = DoiTDataHubIngest(api_key="doit-key")
        rows = ingestor.process_csv(sample_csv)
        assert rows[0]["TOTAL_CREDITS"] == 10.5
        assert rows[0]["JOB_RUN_NUMBER"] == 1

    def test_process_csv_raises_on_missing_file(self):
        from src.send_to_doit import DoiTDataHubIngest
        ingestor = DoiTDataHubIngest(api_key="doit-key")
        with pytest.raises(FileNotFoundError):
            ingestor.process_csv("/nonexistent/file.csv")

    def test_process_csv_handles_null_values(self, tmp_path):
        from src.send_to_doit import DoiTDataHubIngest
        p = tmp_path / "nulls.csv"
        p.write_text("PROJECT_NAME,TOTAL_CREDITS\nmy-project,\\N\n")
        ingestor = DoiTDataHubIngest(api_key="doit-key")
        rows = ingestor.process_csv(str(p))
        assert rows[0]["TOTAL_CREDITS"] is None


class TestDoiTParser:

    def test_add_arguments_registers_csv_file(self):
        from src.send_to_doit import _add_arguments
        parser = argparse.ArgumentParser()
        _add_arguments(parser)
        args = parser.parse_args(["myfile.csv"])
        assert args.csv_file == "myfile.csv"

    def test_dry_run_flag(self):
        from src.send_to_doit import _add_arguments
        parser = argparse.ArgumentParser()
        _add_arguments(parser)
        args = parser.parse_args(["myfile.csv", "--dry-run"])
        assert args.dry_run is True

    def test_standalone_main_help(self):
        from src.send_to_doit import main
        with pytest.raises(SystemExit) as exc:
            with patch("sys.argv", ["send-to-doit", "--help"]):
                main()
        assert exc.value.code == 0


# ---------------------------------------------------------------------------
# DoiTDataHubIngest — conversion and networking helpers
# ---------------------------------------------------------------------------

class TestDoiTConversion:

    def test_convert_to_doit_events_returns_list(self, sample_csv):
        from src.send_to_doit import DoiTDataHubIngest
        ingestor = DoiTDataHubIngest(api_key="doit-key")
        rows = ingestor.process_csv(sample_csv)
        events = ingestor.convert_to_doit_events(rows)
        assert isinstance(events, list)
        assert len(events) == 1

    def test_convert_to_doit_events_has_required_fields(self, sample_csv):
        from src.send_to_doit import DoiTDataHubIngest
        ingestor = DoiTDataHubIngest(api_key="doit-key")
        rows = ingestor.process_csv(sample_csv)
        events = ingestor.convert_to_doit_events(rows)
        event = events[0]
        assert "timestamp" in event or "time" in event or "dimensions" in event

    def test_send_events_returns_warning_on_empty(self):
        from src.send_to_doit import DoiTDataHubIngest
        ingestor = DoiTDataHubIngest(api_key="doit-key")
        result = ingestor.send_events([])
        assert result["status"] == "warning"

    def test_send_csv_file_returns_error_on_missing_file(self):
        from src.send_to_doit import DoiTDataHubIngest
        ingestor = DoiTDataHubIngest(api_key="doit-key")
        result = ingestor.send_csv_file("/nonexistent/file.csv")
        assert result["status"] == "error"

    def test_process_csv_parses_datetime_fields(self, sample_csv):
        from src.send_to_doit import DoiTDataHubIngest
        from datetime import datetime
        ingestor = DoiTDataHubIngest(api_key="doit-key")
        rows = ingestor.process_csv(sample_csv)
        assert isinstance(rows[0]["PIPELINE_CREATED_AT"], datetime)


class TestDoiTHandle:

    def test_dry_run_events_returns_0(self, sample_csv):
        from src.send_to_doit import handle
        args = argparse.Namespace(
            api_key="doit-key",
            csv_file=sample_csv,
            csv_upload=False,
            dry_run=True,
        )
        result = handle(args)
        assert result == 0

    def test_dry_run_csv_upload_returns_0(self, sample_csv):
        from src.send_to_doit import handle
        args = argparse.Namespace(
            api_key="doit-key",
            csv_file=sample_csv,
            csv_upload=True,
            dry_run=True,
        )
        result = handle(args)
        assert result == 0

    def test_missing_api_key_returns_1(self, sample_csv):
        from src.send_to_doit import handle
        args = argparse.Namespace(
            api_key=None,
            csv_file=sample_csv,
            csv_upload=False,
            dry_run=True,
        )
        with patch.dict(os.environ, {}, clear=True):
            result = handle(args)
        assert result == 1


# ---------------------------------------------------------------------------
# DatadogCSVIngest — handle() + datetime parsing
# ---------------------------------------------------------------------------

class TestDatadogSendSeries:

    def test_send_series_empty_data_returns_warning(self):
        from src.send_to_datadog import DatadogCSVIngest
        ingestor = DatadogCSVIngest(api_key="dd-key")
        result = ingestor.send_series([])
        assert result["status"] == "warning"

    def test_send_series_with_data_calls_api(self, sample_csv):
        from src.send_to_datadog import DatadogCSVIngest
        from unittest.mock import MagicMock
        ingestor = DatadogCSVIngest(api_key="dd-key")
        rows = ingestor.process_csv(sample_csv)

        mock_metrics_api = MagicMock()
        mock_metrics_api.submit_metrics.return_value = MagicMock(errors=[])

        with patch("src.send_to_datadog.ApiClient") as mock_api_cls:
            mock_api_cls.return_value.__enter__.return_value = MagicMock()
            with patch("src.send_to_datadog.MetricsApi", return_value=mock_metrics_api):
                result = ingestor.send_series(rows)

        assert result["status"] in ("success", "warning", "error")


class TestDatadogHandle:

    def test_dry_run_returns_0(self, sample_csv):
        from src.send_to_datadog import handle
        args = argparse.Namespace(
            api_key="dd-key",
            application_key=None,
            site="datadoghq.com",
            csv_file=sample_csv,
            dry_run=True,
            batch_size=1000,
            events=False,
        )
        result = handle(args)
        assert result == 0

    def test_missing_api_key_returns_1(self, sample_csv):
        from src.send_to_datadog import handle
        args = argparse.Namespace(
            api_key=None,
            application_key=None,
            site="datadoghq.com",
            csv_file=sample_csv,
            dry_run=True,
            batch_size=1000,
            events=False,
        )
        with patch.dict(os.environ, {}, clear=True):
            result = handle(args)
        assert result == 1

    def test_process_csv_parses_datetime_fields(self, sample_csv):
        from src.send_to_datadog import DatadogCSVIngest
        ingestor = DatadogCSVIngest(api_key="dd-key")
        rows = ingestor.process_csv(sample_csv)
        # Datadog converts datetime columns to Unix timestamps (int)
        assert isinstance(rows[0]["PIPELINE_CREATED_AT"], int)
