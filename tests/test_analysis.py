"""
Tests for src/analysis.py — the core data processing library.
"""
import io
import tempfile
import textwrap
from datetime import datetime, timedelta
from unittest.mock import patch

import pandas as pd
import pytest

from src.analysis import (
    add_computed_fields,
    create_project_datasets,
    load_circleci_data,
    remove_unnecessary_columns,
    summarize_dataset,
    code,
    dollar_amount,
    duration,
    group_by_job_name,
    percentile,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_df(**extra_cols):
    """Return a minimal DataFrame that resembles a real usage export."""
    base = {
        "ORGANIZATION_NAME": ["my-org", "my-org", "my-org"],
        "PROJECT_NAME":       ["proj-a", "proj-a", "proj-b"],
        "JOB_NAME":           ["build", "test", "deploy"],
        "JOB_BUILD_STATUS":   ["success", "failed", "success"],
        "VCS_BRANCH":         ["master", "feature/x", "master"],
        "JOB_RUN_NUMBER":     [1, 2, 3],
        "PIPELINE_ID":        ["p1", "p2", "p3"],
        "TOTAL_CREDITS":      [10.0, 20.0, 5.0],
        "USER_CREDITS":       [0.0, 0.0, 0.0],
        "COMPUTE_CREDITS":    [10.0, 20.0, 5.0],
        "JOB_RUN_SECONDS":    [60, 120, 30],
        "PIPELINE_CREATED_AT": [
            "2024-01-01T00:00:00Z",
            "2024-01-02T00:00:00Z",
            "2024-01-03T00:00:00Z",
        ],
    }
    base.update(extra_cols)
    return pd.DataFrame(base)


@pytest.fixture
def sample_df():
    return _make_df()


@pytest.fixture
def csv_file(tmp_path):
    """Write a minimal CSV file and return its path."""
    df = _make_df()
    p = tmp_path / "usage.csv"
    df.to_csv(p, index=False)
    return str(p)


# ---------------------------------------------------------------------------
# load_circleci_data
# ---------------------------------------------------------------------------

class TestLoadCircleCIData:

    def test_loads_csv_and_returns_dataframe(self, csv_file):
        df, project_dfs = load_circleci_data(csv_file)
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 3

    def test_returns_empty_project_dfs_when_no_project_name(self, csv_file):
        _, project_dfs = load_circleci_data(csv_file)
        assert project_dfs == {}

    def test_returns_project_dfs_when_project_name_given(self, csv_file):
        _, project_dfs = load_circleci_data(csv_file, project_name="proj-a")
        assert "ps_jobs" in project_dfs
        assert len(project_dfs["ps_jobs"]) == 2

    def test_adds_cost_column(self, csv_file):
        df, _ = load_circleci_data(csv_file, credit_cost=0.001)
        assert "COST" in df.columns
        assert df["COST"].sum() > 0

    def test_raises_on_missing_file(self):
        with pytest.raises(Exception):
            load_circleci_data("/nonexistent/path.csv")


# ---------------------------------------------------------------------------
# add_computed_fields
# ---------------------------------------------------------------------------

class TestAddComputedFields:

    def test_adds_cost_from_total_and_user_credits(self, sample_df):
        result = add_computed_fields(sample_df, credit_cost=0.001)
        assert "COST" in result.columns
        assert result["COST"].iloc[0] == pytest.approx(0.01)

    def test_adds_duration_from_seconds(self, sample_df):
        result = add_computed_fields(sample_df, credit_cost=0.001)
        assert "DURATION" in result.columns
        assert result["DURATION"].iloc[0] == timedelta(seconds=60)

    def test_adds_job_url(self, sample_df):
        result = add_computed_fields(sample_df, credit_cost=0.001)
        assert "JOB_URL" in result.columns


# ---------------------------------------------------------------------------
# create_project_datasets
# ---------------------------------------------------------------------------

class TestCreateProjectDatasets:

    def test_filters_to_project(self, sample_df):
        sample_df = add_computed_fields(sample_df, 0.001)
        result = create_project_datasets(sample_df, "proj-a")
        assert len(result["ps_jobs"]) == 2

    def test_splits_master_and_pr_branches(self, sample_df):
        sample_df = add_computed_fields(sample_df, 0.001)
        result = create_project_datasets(sample_df, "proj-a")
        assert len(result["ps_master_jobs"]) == 1
        assert len(result["ps_pr_jobs"]) == 1

    def test_returns_all_keys(self, sample_df):
        sample_df = add_computed_fields(sample_df, 0.001)
        result = create_project_datasets(sample_df, "proj-a")
        for key in ["all_jobs", "ps_jobs", "ps_master_jobs", "ps_master_failed_jobs",
                    "ps_pr_jobs", "ps_pr_passed_jobs", "ps_pr_failed_jobs"]:
            assert key in result

    def test_failed_jobs_filter(self, sample_df):
        sample_df = add_computed_fields(sample_df, 0.001)
        result = create_project_datasets(sample_df, "proj-a")
        assert len(result["ps_master_failed_jobs"]) == 0


# ---------------------------------------------------------------------------
# summarize_dataset
# ---------------------------------------------------------------------------

class TestSummarizeDataset:

    def test_returns_no_data_for_empty_df(self):
        result = summarize_dataset(pd.DataFrame(), name="Test")
        assert "No data" in result

    def test_includes_job_count(self, sample_df):
        sample_df = add_computed_fields(sample_df, 0.001)
        # summarize_dataset calls .date() on datetime columns — drop to avoid AttributeError
        sample_df = sample_df.drop(columns=["PIPELINE_CREATED_AT"], errors="ignore")
        result = summarize_dataset(sample_df, name="All")
        assert "3" in result

    def test_uses_provided_name(self, sample_df):
        sample_df = add_computed_fields(sample_df, 0.001)
        sample_df = sample_df.drop(columns=["PIPELINE_CREATED_AT"], errors="ignore")
        result = summarize_dataset(sample_df, name="MyDataset")
        assert result.startswith("MyDataset:")


# ---------------------------------------------------------------------------
# Formatter helpers
# ---------------------------------------------------------------------------

class TestFormatters:

    def test_code_formats_string(self):
        assert "<code>" in code("hello")
        assert "hello" in code("hello")

    def test_code_handles_nan(self):
        assert "N/A" in code(float("nan"))

    def test_dollar_amount(self):
        assert "$" in dollar_amount(42.5)

    def test_dollar_amount_nan(self):
        result = dollar_amount(float("nan"))
        assert result == "$0.00"

    def test_duration_timedelta(self):
        result = duration(timedelta(hours=1, minutes=30))
        assert "01:30:00" in result

    def test_duration_nan(self):
        result = duration(float("nan"))
        assert "N/A" in result

    def test_duration_invalid_value_returns_error_string(self):
        result = duration("not-a-timedelta")
        assert "<code>" in result


# ---------------------------------------------------------------------------
# group_by_job_name / percentile
# ---------------------------------------------------------------------------

class TestGroupByJobName:

    def test_returns_dataframe_with_num_jobs(self, sample_df):
        df = add_computed_fields(sample_df, 0.001)
        result = group_by_job_name(df)
        assert "NUM_JOBS" in result.columns
        assert len(result) == 3  # 3 distinct job names

    def test_filters_by_status(self, sample_df):
        df = add_computed_fields(sample_df, 0.001)
        result = group_by_job_name(df, status="success")
        # only 2 jobs have success status
        assert len(result) == 2

    def test_empty_status_includes_all(self, sample_df):
        df = add_computed_fields(sample_df, 0.001)
        result_all = group_by_job_name(df)
        result_empty = group_by_job_name(df, status="")
        assert len(result_all) == len(result_empty)


class TestPercentile:

    def test_returns_callable(self):
        fn = percentile(0.95)
        assert callable(fn)

    def test_calculates_correct_percentile(self):
        import pandas as pd
        fn = percentile(0.5)
        series = pd.Series([1, 2, 3, 4, 5])
        assert fn(series) == 3.0

    def test_function_name_is_set(self):
        fn = percentile(0.95)
        assert "95" in fn.__name__


# ---------------------------------------------------------------------------
# find_highest_credit_project (from run_analysis, tested here for coverage)
# ---------------------------------------------------------------------------

class TestFindHighestCreditProject:

    def test_returns_project_with_most_credits(self, tmp_path):
        p = tmp_path / "data.csv"
        p.write_text("PROJECT_NAME,TOTAL_CREDITS\nproj-a,100\nproj-b,500\nproj-a,50\n")
        from src.run_analysis import find_highest_credit_project
        result = find_highest_credit_project(str(p))
        assert result == "proj-b"

    def test_returns_default_on_missing_file(self):
        from src.run_analysis import find_highest_credit_project
        result = find_highest_credit_project("/nonexistent/file.csv")
        assert result == "your-project"

    def test_returns_default_when_no_project_name_column(self, tmp_path):
        p = tmp_path / "data.csv"
        p.write_text("FOO,BAR\n1,2\n")
        from src.run_analysis import find_highest_credit_project
        result = find_highest_credit_project(str(p))
        assert result == "your-project"
