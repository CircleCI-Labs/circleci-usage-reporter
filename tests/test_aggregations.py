"""Tests for src/aggregations.py."""

from datetime import date

import pandas as pd
import pytest

from src.aggregations import (
    aggregate_project_weekly,
    aggregate_resource_class_weekly,
    detect_resource_class_changes,
    map_csv_row_to_db,
    previous_calendar_week,
)


@pytest.fixture
def sample_df():
    return pd.DataFrame([
        {
            "ORGANIZATION_ID": "org-1",
            "ORGANIZATION_NAME": "my-org",
            "PROJECT_NAME": "project-a",
            "JOB_ID": "job-1",
            "JOB_NAME": "build",
            "RESOURCE_CLASS": "medium",
            "TOTAL_CREDITS": 10.0,
            "COMPUTE_CREDITS": 8.0,
            "USER_CREDITS": 1.0,
            "DLC_CREDITS": 1.0,
            "JOB_RUN_SECONDS": 120.0,
            "MEDIAN_CPU_UTILIZATION_PCT": 25.0,
            "MEDIAN_RAM_UTILIZATION_PCT": 30.0,
            "PIPELINE_CREATED_AT": "2024-01-01 12:00:00",
        },
        {
            "ORGANIZATION_ID": "org-1",
            "ORGANIZATION_NAME": "my-org",
            "PROJECT_NAME": "project-a",
            "JOB_ID": "job-2",
            "JOB_NAME": "test",
            "RESOURCE_CLASS": "large",
            "TOTAL_CREDITS": 20.0,
            "COMPUTE_CREDITS": 18.0,
            "USER_CREDITS": 2.0,
            "DLC_CREDITS": 0.0,
            "JOB_RUN_SECONDS": 60.0,
            "MEDIAN_CPU_UTILIZATION_PCT": 55.0,
            "MEDIAN_RAM_UTILIZATION_PCT": 60.0,
            "PIPELINE_CREATED_AT": "2024-01-02 12:00:00",
        },
        {
            "ORGANIZATION_ID": "org-1",
            "ORGANIZATION_NAME": "my-org",
            "PROJECT_NAME": "project-b",
            "JOB_ID": "job-3",
            "JOB_NAME": "deploy",
            "RESOURCE_CLASS": "small",
            "TOTAL_CREDITS": 5.0,
            "COMPUTE_CREDITS": 5.0,
            "USER_CREDITS": 0.0,
            "DLC_CREDITS": 0.0,
            "JOB_RUN_SECONDS": 30.0,
            "MEDIAN_CPU_UTILIZATION_PCT": 80.0,
            "MEDIAN_RAM_UTILIZATION_PCT": 70.0,
            "PIPELINE_CREATED_AT": "2024-01-03 12:00:00",
        },
    ])


class TestColumnMapping:

    def test_map_csv_row_to_db_renames_columns(self):
        row = {
            "ORGANIZATION_NAME": "my-org",
            "PROJECT_NAME": "my-project",
            "JOB_ID": "job-123",
            "TOTAL_CREDITS": 10.5,
            "IS_WORKFLOW_SUCCESSFUL": "true",
        }
        mapped = map_csv_row_to_db(row, report_week_id=1)
        assert mapped["organization_name"] == "my-org"
        assert mapped["project_name"] == "my-project"
        assert mapped["job_id"] == "job-123"
        assert mapped["total_credits"] == 10.5
        assert mapped["is_workflow_successful"] is True
        assert mapped["report_week_id"] == 1
        assert mapped["storage_credits"] is None

    def test_previous_calendar_week_returns_monday_boundaries(self):
        week_start, week_end = previous_calendar_week(date(2026, 6, 22))
        assert week_start.weekday() == 0
        assert week_end.weekday() == 0
        assert (week_end - week_start).days == 7


class TestAggregations:

    def test_aggregate_project_weekly(self, sample_df):
        result = aggregate_project_weekly(sample_df, credit_cost=0.0006)
        assert len(result) == 2
        project_a = result[result["project_name"] == "project-a"].iloc[0]
        assert project_a["total_credits"] == 30.0
        assert project_a["job_count"] == 2
        assert project_a["total_cost"] == pytest.approx((9.0 + 18.0) * 0.0006)

    def test_aggregate_resource_class_weekly(self, sample_df):
        result = aggregate_resource_class_weekly(sample_df)
        assert len(result) == 3
        assert set(result["resource_class"]) == {"medium", "large", "small"}

    def test_detect_resource_class_changes(self, sample_df):
        current = sample_df.copy()
        previous = sample_df.copy()
        previous.loc[previous["PROJECT_NAME"] == "project-a", "RESOURCE_CLASS"] = "small"
        changed = detect_resource_class_changes(current, previous)
        assert len(changed) >= 1
        row = changed[changed["project_name"] == "project-a"].iloc[0]
        assert row["previous_resource_class"] == "small"
        assert row["current_resource_class"] != "small"
