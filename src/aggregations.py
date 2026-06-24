#!/usr/bin/env python3
"""Aggregation helpers for Postgres storage and Prometheus metrics."""

from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

import pandas as pd

# Usage API CSV column -> circleci_usage table column
CSV_TO_DB_COLUMNS = {
    "ORGANIZATION_ID": "organization_id",
    "ORGANIZATION_NAME": "organization_name",
    "PROJECT_ID": "project_id",
    "PROJECT_NAME": "project_name",
    "PIPELINE_ID": "pipeline_id",
    "PIPELINE_NUMBER": "pipeline_number",
    "PIPELINE_CREATED_AT": "pipeline_created_at",
    "PIPELINE_TRIGGER_SOURCE": "pipeline_trigger_source",
    "PIPELINE_TRIGGER_USER_ID": "pipeline_trigger_user_id",
    "WORKFLOW_ID": "workflow_id",
    "WORKFLOW_NAME": "workflow_name",
    "IS_WORKFLOW_SUCCESSFUL": "is_workflow_successful",
    "WORKFLOW_FIRST_JOB_QUEUED_AT": "workflow_first_job_queued_at",
    "WORKFLOW_FIRST_JOB_STARTED_AT": "workflow_first_job_started_at",
    "WORKFLOW_STOPPED_AT": "workflow_stopped_at",
    "JOB_ID": "job_id",
    "JOB_NAME": "job_name",
    "JOB_BUILD_STATUS": "job_build_status",
    "JOB_RUN_NUMBER": "job_run_number",
    "JOB_RUN_STARTED_AT": "job_run_started_at",
    "JOB_RUN_STOPPED_AT": "job_run_stopped_at",
    "JOB_RUN_SECONDS": "job_run_seconds",
    "RESOURCE_CLASS": "resource_class",
    "EXECUTOR": "executor",
    "OPERATING_SYSTEM": "operating_system",
    "PARALLELISM": "parallelism",
    "VCS_NAME": "vcs_name",
    "VCS_URL": "vcs_url",
    "VCS_BRANCH": "vcs_branch",
    "TOTAL_CREDITS": "total_credits",
    "COMPUTE_CREDITS": "compute_credits",
    "USER_CREDITS": "user_credits",
    "DLC_CREDITS": "dlc_credits",
    "MEDIAN_CPU_UTILIZATION_PCT": "median_cpu_utilization_pct",
    "MAX_CPU_UTILIZATION_PCT": "max_cpu_utilization_pct",
    "MEDIAN_RAM_UTILIZATION_PCT": "median_ram_utilization_pct",
    "MAX_RAM_UTILIZATION_PCT": "max_ram_utilization_pct",
    "IS_UNREGISTERED_USER": "is_unregistered_user",
    "LAST_BUILD_FINISHED_AT": "last_build_finished_at",
}

DB_INSERT_COLUMNS = list(CSV_TO_DB_COLUMNS.values()) + ["report_week_id"]

DATETIME_DB_COLUMNS = {
    "pipeline_created_at",
    "workflow_first_job_queued_at",
    "workflow_first_job_started_at",
    "workflow_stopped_at",
    "job_run_started_at",
    "job_run_stopped_at",
    "last_build_finished_at",
}

FLOAT_DB_COLUMNS = {
    "job_run_seconds",
    "total_credits",
    "compute_credits",
    "user_credits",
    "dlc_credits",
    "median_cpu_utilization_pct",
    "max_cpu_utilization_pct",
    "median_ram_utilization_pct",
    "max_ram_utilization_pct",
}

INT_DB_COLUMNS = {"pipeline_number", "job_run_number", "parallelism"}

BOOL_DB_COLUMNS = {"is_workflow_successful", "is_unregistered_user"}


def previous_calendar_week(reference: Optional[date] = None) -> tuple:
    """Return (week_start, week_end) for the previous Mon–Sun calendar week."""
    today = reference or date.today()
    days_since_monday = today.weekday()
    this_monday = today - timedelta(days=days_since_monday)
    week_end = this_monday
    week_start = week_end - timedelta(days=7)
    return week_start, week_end


def load_usage_dataframe(csv_path: str) -> pd.DataFrame:
    """Load Usage API CSV into a pandas DataFrame."""
    na_values = ["\\N"]
    return pd.read_csv(csv_path, escapechar="\\", na_values=na_values)


def _coerce_value(db_col: str, value: Any) -> Any:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if db_col in DATETIME_DB_COLUMNS:
        if isinstance(value, pd.Timestamp):
            return value.to_pydatetime()
        if isinstance(value, datetime):
            return value
        parsed = pd.to_datetime(value, errors="coerce")
        if pd.isna(parsed):
            return None
        return parsed.to_pydatetime()
    if db_col in BOOL_DB_COLUMNS:
        if isinstance(value, bool):
            return value
        return str(value).lower() == "true"
    if db_col in INT_DB_COLUMNS:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
    if db_col in FLOAT_DB_COLUMNS:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    return value


def map_csv_row_to_db(row: Dict[str, Any], report_week_id: int) -> Dict[str, Any]:
    """Map a parsed CSV row dict to circleci_usage column names."""
    mapped: Dict[str, Any] = {"report_week_id": report_week_id}
    for csv_col, db_col in CSV_TO_DB_COLUMNS.items():
        mapped[db_col] = _coerce_value(db_col, row.get(csv_col))
    mapped["storage_credits"] = None
    mapped["network_credits"] = None
    mapped["lease_credits"] = None
    return mapped


def dataframe_to_db_rows(df: pd.DataFrame, report_week_id: int) -> List[Dict[str, Any]]:
    """Convert a DataFrame to a list of circleci_usage row dicts."""
    working = df.copy()
    datetime_columns = [
        col for col in CSV_TO_DB_COLUMNS if CSV_TO_DB_COLUMNS[col] in DATETIME_DB_COLUMNS
    ]
    for col in datetime_columns:
        if col in working.columns:
            working[col] = pd.to_datetime(working[col], format="ISO8601", errors="coerce")

    rows = []
    for record in working.to_dict(orient="records"):
        job_id = record.get("JOB_ID")
        if not job_id or (isinstance(job_id, float) and pd.isna(job_id)):
            continue
        rows.append(map_csv_row_to_db(record, report_week_id))
    return rows


def aggregate_project_weekly(df: pd.DataFrame, credit_cost: float = 0.0006) -> pd.DataFrame:
    """Aggregate per-project stats for a weekly report."""
    if df.empty or "PROJECT_NAME" not in df.columns:
        return pd.DataFrame()

    working = df.copy()
    if "TOTAL_CREDITS" not in working.columns:
        working["TOTAL_CREDITS"] = 0
    if "USER_CREDITS" not in working.columns:
        working["USER_CREDITS"] = 0
    working["billable_credits"] = working["TOTAL_CREDITS"].fillna(0) - working["USER_CREDITS"].fillna(0)
    working["cost"] = working["billable_credits"] * credit_cost

    agg = working.groupby("PROJECT_NAME", dropna=False).agg(
        total_credits=("TOTAL_CREDITS", "sum"),
        compute_credits=("COMPUTE_CREDITS", "sum"),
        user_credits=("USER_CREDITS", "sum"),
        dlc_credits=("DLC_CREDITS", "sum"),
        total_cost=("cost", "sum"),
        job_count=("JOB_ID", "count"),
        avg_duration_seconds=("JOB_RUN_SECONDS", "mean"),
    ).reset_index()

    agg = agg.rename(columns={"PROJECT_NAME": "project_name"})
    return agg


def aggregate_resource_class_weekly(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate per-project resource-class stats for a weekly report."""
    if df.empty or "PROJECT_NAME" not in df.columns:
        return pd.DataFrame()

    working = df.copy()
    working["RESOURCE_CLASS"] = working["RESOURCE_CLASS"].fillna("unknown")

    agg = working.groupby(["PROJECT_NAME", "RESOURCE_CLASS"], dropna=False).agg(
        job_count=("JOB_ID", "count"),
        total_credits=("TOTAL_CREDITS", "sum"),
        avg_cpu_utilization=("MEDIAN_CPU_UTILIZATION_PCT", "mean"),
        avg_ram_utilization=("MEDIAN_RAM_UTILIZATION_PCT", "mean"),
    ).reset_index()

    agg = agg.rename(columns={
        "PROJECT_NAME": "project_name",
        "RESOURCE_CLASS": "resource_class",
    })
    return agg


def detect_resource_class_changes(
    current_df: pd.DataFrame,
    previous_df: pd.DataFrame,
) -> pd.DataFrame:
    """Find projects whose dominant resource class changed between weeks."""
    if current_df.empty or previous_df.empty:
        return pd.DataFrame()

    def dominant_by_project(frame: pd.DataFrame) -> pd.DataFrame:
        working = frame.copy()
        working["RESOURCE_CLASS"] = working["RESOURCE_CLASS"].fillna("unknown")
        counts = (
            working.groupby(["PROJECT_NAME", "RESOURCE_CLASS"])
            .size()
            .reset_index(name="job_count")
        )
        idx = counts.groupby("PROJECT_NAME")["job_count"].idxmax()
        dominant = counts.loc[idx].rename(columns={
            "PROJECT_NAME": "project_name",
            "RESOURCE_CLASS": "resource_class",
        })
        return dominant[["project_name", "resource_class", "job_count"]]

    current = dominant_by_project(current_df).rename(columns={
        "resource_class": "current_resource_class",
        "job_count": "current_job_count",
    })
    previous = dominant_by_project(previous_df).rename(columns={
        "resource_class": "previous_resource_class",
        "job_count": "previous_job_count",
    })

    merged = current.merge(previous, on="project_name", how="inner")
    changed = merged[
        merged["current_resource_class"] != merged["previous_resource_class"]
    ].copy()
    return changed
