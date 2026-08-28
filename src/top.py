#!/usr/bin/env python3
"""Rank top workflows or jobs for a project from Usage API data."""

import os
import sys
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests

from src.aggregations import load_usage_dataframe
from src.get import (
    BASE_API_URL,
    TEMP_DIR_BASE,
    export_usage_report,
    resolve_api_token,
    resolve_org_id,
)

DEFAULT_DAYS = 30
MAX_DAYS = 32
DEFAULT_LIMIT = 10
MIN_EXPORT_INTERVAL_SECONDS = 360  # 10 exports/hour

DISCLAIMER = (
    "The Usage API allows 10 export requests per hour per organization. "
    "This command may create an export; do not run it frequently."
)
CACHE_REUSED_NOTE = (
    "This run reused a cached export (no new request)."
)
RATE_LIMIT_BLOCK = (
    "Error: A usage export was requested for this organization within the last "
    "6 minutes (limit is 10 per hour). No cached export is available for this "
    "date range. Wait and try again."
)


def _today():
    return datetime.now(timezone.utc).date()


def _add_shared_arguments(parser):
    parser.add_argument(
        '--project-id',
        help='CircleCI project ID (or set CIRCLE_PROJECT_ID)',
    )
    parser.add_argument(
        '--org-id',
        help='CircleCI organization ID (or set CIRCLE_ORGANIZATION_ID or ORG_ID)',
    )
    parser.add_argument(
        '--api-token',
        help='CircleCI API token (or set CIRCLECI_API_TOKEN, CIRCLE_TOKEN, or CIRCLECI_TOKEN)',
    )
    parser.add_argument(
        '--start-date',
        help='Start date YYYY-MM-DD (default: --days ago)',
    )
    parser.add_argument(
        '--end-date',
        help='End date YYYY-MM-DD (default: today, UTC)',
    )
    parser.add_argument(
        '--days',
        type=int,
        default=DEFAULT_DAYS,
        help=f'Lookback window in days (default: {DEFAULT_DAYS}, max: {MAX_DAYS})',
    )
    parser.add_argument(
        '--limit',
        type=int,
        default=DEFAULT_LIMIT,
        help=f'Number of rows to show (default: {DEFAULT_LIMIT})',
    )
    return parser


def add_parser(subparsers):
    """Register top-workflows and top-jobs."""
    workflows = subparsers.add_parser(
        'top-workflows',
        help='Rank workflows by credits for a project',
    )
    _add_shared_arguments(workflows)

    jobs = subparsers.add_parser(
        'top-jobs',
        help='Rank jobs by credits for a project',
    )
    _add_shared_arguments(jobs)
    return workflows


def resolve_project_id(cli_project_id=None):
    return cli_project_id or os.getenv('CIRCLE_PROJECT_ID')


def resolve_org_id_from_project(project_id, api_token):
    """Look up organization ID from a project via the CircleCI API."""
    headers = {"Circle-Token": api_token, "Accept": "application/json"}

    v3 = requests.get(
        f"https://circleci.com/api/v3/projects/{project_id}",
        headers=headers,
    )
    if v3.status_code == 200:
        payload = v3.json()
        org_id = (
            payload.get("data", {}).get("references", {}).get("org", {}).get("id")
            or payload.get("organization_id")
        )
        if org_id:
            return str(org_id)

    v2 = requests.get(
        f"{BASE_API_URL}/project/{project_id}",
        headers=headers,
    )
    if v2.status_code == 200:
        org_id = v2.json().get("organization_id")
        if org_id:
            return str(org_id)

    return None


def resolve_date_range(start_date, end_date, days):
    """Return (start, end) as YYYY-MM-DD strings, or (None, None) on error."""
    if start_date and end_date:
        try:
            start = datetime.strptime(start_date, "%Y-%m-%d").date()
            end = datetime.strptime(end_date, "%Y-%m-%d").date()
        except ValueError:
            print("Error: Dates must be YYYY-MM-DD.", file=sys.stderr)
            return None, None
    elif start_date or end_date:
        print(
            "Error: --start-date and --end-date must be provided together "
            "(or omit both to use --days).",
            file=sys.stderr,
        )
        return None, None
    else:
        if days is None:
            days = DEFAULT_DAYS
        if days < 1 or days > MAX_DAYS:
            print(
                f"Error: --days must be between 1 and {MAX_DAYS}.",
                file=sys.stderr,
            )
            return None, None
        end = _today()
        start = end - timedelta(days=days)

    if start > end:
        print("Error: --start-date must be on or before --end-date.", file=sys.stderr)
        return None, None

    if (end - start).days > MAX_DAYS:
        print(
            f"Error: Usage API date window cannot exceed {MAX_DAYS} days.",
            file=sys.stderr,
        )
        return None, None

    return start.isoformat(), end.isoformat()


def _safe_key_part(value):
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in str(value))


def _cache_dir(cache_dir=None):
    return cache_dir or TEMP_DIR_BASE


def cache_csv_path(org_id, start_date, end_date, cache_dir=None):
    key = f"{_safe_key_part(org_id)}_{start_date}_{end_date}"
    return os.path.join(_cache_dir(cache_dir), f"{key}.csv")


def cache_sidecar_path(org_id, start_date, end_date, cache_dir=None):
    key = f"{_safe_key_part(org_id)}_{start_date}_{end_date}"
    return os.path.join(_cache_dir(cache_dir), f"{key}.exported_at")


def org_last_export_path(org_id, cache_dir=None):
    return os.path.join(_cache_dir(cache_dir), f"{_safe_key_part(org_id)}.last_export")


def _parse_timestamp(raw):
    try:
        parsed = datetime.fromisoformat(raw.strip())
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def read_last_export_time(org_id, cache_dir=None):
    path = org_last_export_path(org_id, cache_dir)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as handle:
        return _parse_timestamp(handle.read())


def write_export_timestamps(org_id, start_date, end_date, cache_dir=None):
    stamp = datetime.now(timezone.utc).isoformat()
    directory = _cache_dir(cache_dir)
    os.makedirs(directory, exist_ok=True)
    for path in (
        org_last_export_path(org_id, directory),
        cache_sidecar_path(org_id, start_date, end_date, directory),
    ):
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(stamp)


def recent_export_blocks_new_request(org_id, cache_dir=None, now=None):
    last = read_last_export_time(org_id, cache_dir)
    if last is None:
        return False
    current = now or datetime.now(timezone.utc)
    return (current - last).total_seconds() < MIN_EXPORT_INTERVAL_SECONDS


def ensure_usage_csv(org_id, api_token, start_date, end_date, cache_dir=None):
    """Return (csv_path, reused) or (None, False) if export cannot proceed."""
    directory = _cache_dir(cache_dir)
    os.makedirs(directory, exist_ok=True)
    csv_path = cache_csv_path(org_id, start_date, end_date, directory)

    if os.path.exists(csv_path):
        return csv_path, True

    if recent_export_blocks_new_request(org_id, directory):
        print(RATE_LIMIT_BLOCK, file=sys.stderr)
        return None, False

    result = export_usage_report(
        org_id,
        api_token,
        start_date,
        end_date,
        csv_path,
        quiet=True,
    )
    if result != 0:
        return None, False

    write_export_timestamps(org_id, start_date, end_date, directory)
    return csv_path, False


def _numeric(series):
    return pd.to_numeric(series, errors="coerce").fillna(0)


def _workflow_duration_seconds(df):
    """One wall-clock duration per WORKFLOW_ID (not summed job seconds)."""
    work = df.copy()
    if (
        "WORKFLOW_FIRST_JOB_STARTED_AT" in work.columns
        and "WORKFLOW_STOPPED_AT" in work.columns
        and work["WORKFLOW_FIRST_JOB_STARTED_AT"].notna().any()
        and work["WORKFLOW_STOPPED_AT"].notna().any()
    ):
        work["_start"] = pd.to_datetime(
            work["WORKFLOW_FIRST_JOB_STARTED_AT"], errors="coerce"
        )
        work["_stop"] = pd.to_datetime(work["WORKFLOW_STOPPED_AT"], errors="coerce")
    else:
        if "JOB_RUN_STARTED_AT" in work.columns:
            work["_start"] = pd.to_datetime(work["JOB_RUN_STARTED_AT"], errors="coerce")
        else:
            work["_start"] = pd.NaT
        if "JOB_RUN_STOPPED_AT" in work.columns:
            work["_stop"] = pd.to_datetime(work["JOB_RUN_STOPPED_AT"], errors="coerce")
        else:
            work["_stop"] = pd.NaT

    per_run = work.groupby("WORKFLOW_ID", dropna=False).agg(
        start=("_start", "min"),
        stop=("_stop", "max"),
    )
    return (per_run["stop"] - per_run["start"]).dt.total_seconds()


def rank_workflows(df, limit=DEFAULT_LIMIT):
    """Group by WORKFLOW_NAME; runs are distinct WORKFLOW_ID values."""
    if df.empty or "WORKFLOW_NAME" not in df.columns:
        return pd.DataFrame(columns=["WORKFLOW_NAME", "CREDITS", "RUNS", "DURATION_SECONDS"])

    work = df.copy()
    if "TOTAL_CREDITS" in work.columns:
        work["TOTAL_CREDITS"] = _numeric(work["TOTAL_CREDITS"])
    else:
        work["TOTAL_CREDITS"] = 0

    credits = work.groupby(["WORKFLOW_NAME", "WORKFLOW_ID"], dropna=False)["TOTAL_CREDITS"].sum()
    durations = _workflow_duration_seconds(work)

    per_run = credits.reset_index(name="CREDITS")
    duration_df = durations.rename("DURATION_SECONDS").reset_index()
    per_run = per_run.merge(duration_df, on="WORKFLOW_ID", how="left")

    ranked = per_run.groupby("WORKFLOW_NAME", dropna=False).agg(
        CREDITS=("CREDITS", "sum"),
        RUNS=("WORKFLOW_ID", "nunique"),
        DURATION_SECONDS=("DURATION_SECONDS", "sum"),
    ).reset_index()

    return ranked.sort_values("CREDITS", ascending=False).head(limit).reset_index(drop=True)


def rank_jobs(df, limit=DEFAULT_LIMIT):
    """Group by JOB_NAME; runs are job rows / distinct JOB_ID values."""
    if df.empty or "JOB_NAME" not in df.columns:
        return pd.DataFrame(columns=["JOB_NAME", "CREDITS", "RUNS", "DURATION_SECONDS"])

    work = df.copy()
    if "TOTAL_CREDITS" in work.columns:
        work["TOTAL_CREDITS"] = _numeric(work["TOTAL_CREDITS"])
    else:
        work["TOTAL_CREDITS"] = 0
    if "JOB_RUN_SECONDS" in work.columns:
        work["JOB_RUN_SECONDS"] = _numeric(work["JOB_RUN_SECONDS"])
    else:
        work["JOB_RUN_SECONDS"] = 0

    if "JOB_ID" in work.columns:
        runs = ("JOB_ID", "nunique")
    else:
        runs = ("JOB_NAME", "count")

    ranked = work.groupby("JOB_NAME", dropna=False).agg(
        CREDITS=("TOTAL_CREDITS", "sum"),
        RUNS=runs,
        DURATION_SECONDS=("JOB_RUN_SECONDS", "sum"),
    ).reset_index()

    return ranked.sort_values("CREDITS", ascending=False).head(limit).reset_index(drop=True)


def format_duration(seconds):
    if seconds is None or pd.isna(seconds):
        return "--"
    total = int(round(float(seconds)))
    if total < 0:
        return "--"
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def print_ranking_table(ranked, name_column, title):
    print(title)
    display = ranked.copy()
    display["CREDITS"] = display["CREDITS"].map(lambda value: f"{float(value):.2f}")
    display["RUNS"] = display["RUNS"].astype(int)
    display["DURATION"] = display["DURATION_SECONDS"].map(format_duration)
    print(display[[name_column, "CREDITS", "RUNS", "DURATION"]].to_string(index=False))


def filter_project(df, project_id):
    if "PROJECT_ID" not in df.columns:
        return df.iloc[0:0]
    return df[df["PROJECT_ID"].astype(str) == str(project_id)]


def handle(args):
    """Execute top-workflows or top-jobs."""
    kind = "workflows" if args.command == "top-workflows" else "jobs"
    print(DISCLAIMER)
    print()

    api_token = resolve_api_token(args.api_token)
    project_id = resolve_project_id(args.project_id)
    start_date, end_date = resolve_date_range(
        args.start_date, args.end_date, args.days
    )
    limit = args.limit if args.limit is not None else DEFAULT_LIMIT

    if not api_token:
        print(
            "Error: CircleCI API token required. Use --api-token or set "
            "CIRCLECI_API_TOKEN, CIRCLE_TOKEN, or CIRCLECI_TOKEN",
            file=sys.stderr,
        )
        return 1

    if not project_id:
        print(
            "Error: Project ID required. Use --project-id or set CIRCLE_PROJECT_ID",
            file=sys.stderr,
        )
        return 1

    if start_date is None:
        return 1

    if limit < 1:
        print("Error: --limit must be at least 1.", file=sys.stderr)
        return 1

    org_id = resolve_org_id(args.org_id)
    if not org_id:
        org_id = resolve_org_id_from_project(project_id, api_token)
    if not org_id:
        print(
            "Error: Organization ID required. Use --org-id, set "
            "CIRCLE_ORGANIZATION_ID or ORG_ID, or pass --project-id so it "
            "can be resolved from the CircleCI API.",
            file=sys.stderr,
        )
        return 1

    csv_path = cache_csv_path(org_id, start_date, end_date)
    reused = os.path.exists(csv_path)
    if reused:
        print(CACHE_REUSED_NOTE)
        print()

    if not reused:
        csv_path, _ = ensure_usage_csv(org_id, api_token, start_date, end_date)
        if csv_path is None:
            return 1

    df = load_usage_dataframe(csv_path)
    project_df = filter_project(df, project_id)
    if project_df.empty:
        print(
            f"No usage data found for project {project_id} "
            f"from {start_date} to {end_date}."
        )
        return 0

    if kind == "workflows":
        ranked = rank_workflows(project_df, limit=limit)
        print_ranking_table(
            ranked,
            "WORKFLOW_NAME",
            f"Top workflows by credits ({start_date} to {end_date})",
        )
    else:
        ranked = rank_jobs(project_df, limit=limit)
        print_ranking_table(
            ranked,
            "JOB_NAME",
            f"Top jobs by credits ({start_date} to {end_date})",
        )
    return 0
