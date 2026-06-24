#!/usr/bin/env python3
"""Store CircleCI usage data in Postgres and push weekly metrics to Prometheus."""

import argparse
import os
import sys
from datetime import date, datetime, time, timezone
from typing import Any, Dict, List, Optional

import pandas as pd
import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from src.aggregations import (
    DB_INSERT_COLUMNS,
    aggregate_project_weekly,
    aggregate_resource_class_weekly,
    dataframe_to_db_rows,
    load_usage_dataframe,
    previous_calendar_week,
)

CIRCLECI_USAGE_COLUMNS = DB_INSERT_COLUMNS + [
    "storage_credits",
    "network_credits",
    "lease_credits",
]


class MetricsStore:
    """Persist usage CSV data to Postgres and push weekly Prometheus metrics."""

    def __init__(
        self,
        database_url: str,
        pushgateway_url: Optional[str] = None,
        credit_cost: float = 0.0006,
    ):
        if not database_url:
            raise ValueError(
                "Database URL required. Use --database-url or set DATABASE_URL."
            )
        self.database_url = database_url
        self.pushgateway_url = pushgateway_url
        self.credit_cost = credit_cost

    def process_csv(self, csv_path: str) -> pd.DataFrame:
        if not os.path.exists(csv_path):
            raise FileNotFoundError(f"CSV file not found: {csv_path}")
        return load_usage_dataframe(csv_path)

    def store(
        self,
        df: pd.DataFrame,
        week_start: date,
        week_end: date,
        org_id: Optional[str] = None,
        replace: bool = True,
    ) -> Dict[str, Any]:
        org_id = org_id or self._infer_org_id(df)
        org_name = self._infer_org_name(df)
        db_rows = []

        with psycopg.connect(self.database_url, row_factory=dict_row) as conn:
            with conn.transaction():
                report_week_id = self._upsert_report_week(
                    conn, week_start, week_end, org_id, org_name, len(df), replace
                )
                db_rows = dataframe_to_db_rows(df, report_week_id)
                self._insert_usage_rows(conn, report_week_id, db_rows, replace)
                project_stats = aggregate_project_weekly(df, self.credit_cost)
                resource_stats = aggregate_resource_class_weekly(df)
                self._upsert_weekly_stats(
                    conn, report_week_id, project_stats, resource_stats, replace
                )

        prometheus_result = None
        if self.pushgateway_url and not project_stats.empty:
            prometheus_result = self._push_prometheus_metrics(
                project_stats, resource_stats, org_name or org_id, week_end
            )

        return {
            "report_week_id": report_week_id,
            "job_count": len(db_rows),
            "project_count": len(project_stats),
            "prometheus": prometheus_result,
        }

    def _infer_org_id(self, df: pd.DataFrame) -> str:
        if "ORGANIZATION_ID" in df.columns and df["ORGANIZATION_ID"].notna().any():
            return str(df["ORGANIZATION_ID"].dropna().iloc[0])
        raise ValueError("org_id not provided and ORGANIZATION_ID not found in CSV")

    def _infer_org_name(self, df: pd.DataFrame) -> Optional[str]:
        if "ORGANIZATION_NAME" in df.columns and df["ORGANIZATION_NAME"].notna().any():
            return str(df["ORGANIZATION_NAME"].dropna().iloc[0])
        return None

    def _upsert_report_week(
        self,
        conn,
        week_start: date,
        week_end: date,
        org_id: str,
        org_name: Optional[str],
        job_count: int,
        replace: bool,
    ) -> int:
        existing = conn.execute(
            """
            SELECT id FROM report_weeks
            WHERE org_id = %s AND week_start = %s
            """,
            (org_id, week_start),
        ).fetchone()

        if existing:
            report_week_id = existing["id"]
            if replace:
                conn.execute(
                    "DELETE FROM circleci_usage WHERE report_week_id = %s",
                    (report_week_id,),
                )
                conn.execute(
                    "DELETE FROM weekly_project_stats WHERE report_week_id = %s",
                    (report_week_id,),
                )
                conn.execute(
                    "DELETE FROM weekly_resource_class_stats WHERE report_week_id = %s",
                    (report_week_id,),
                )
                conn.execute(
                    """
                    UPDATE report_weeks
                    SET week_end = %s, org_name = %s, job_count = %s, ingested_at = NOW()
                    WHERE id = %s
                    """,
                    (week_end, org_name, job_count, report_week_id),
                )
            else:
                raise ValueError(
                    f"Week {week_start} already ingested for org {org_id}. "
                    "Use --replace to overwrite."
                )
            return report_week_id

        row = conn.execute(
            """
            INSERT INTO report_weeks (week_start, week_end, org_id, org_name, job_count)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
            """,
            (week_start, week_end, org_id, org_name, job_count),
        ).fetchone()
        return row["id"]

    def _insert_usage_rows(
        self,
        conn,
        report_week_id: int,
        rows: List[Dict[str, Any]],
        replace: bool,
    ) -> None:
        if not rows:
            return

        columns = CIRCLECI_USAGE_COLUMNS
        placeholders = sql.SQL(", ").join(sql.Placeholder() * len(columns))
        insert_sql = sql.SQL(
            "INSERT INTO circleci_usage ({cols}) VALUES ({vals})"
        ).format(
            cols=sql.SQL(", ").join(map(sql.Identifier, columns)),
            vals=placeholders,
        )

        if not replace:
            insert_sql = sql.SQL("{} ON CONFLICT (job_id, report_week_id) DO NOTHING").format(
                insert_sql
            )

        values = [
            tuple(row.get(col) for col in columns)
            for row in rows
        ]

        with conn.cursor() as cur:
            cur.executemany(insert_sql, values)

    def _upsert_weekly_stats(
        self,
        conn,
        report_week_id: int,
        project_stats: pd.DataFrame,
        resource_stats: pd.DataFrame,
        replace: bool,
    ) -> None:
        for _, row in project_stats.iterrows():
            conn.execute(
                """
                INSERT INTO weekly_project_stats (
                    report_week_id, project_name, total_credits, compute_credits,
                    user_credits, dlc_credits, total_cost, job_count, avg_duration_seconds
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (report_week_id, project_name) DO UPDATE SET
                    total_credits = EXCLUDED.total_credits,
                    compute_credits = EXCLUDED.compute_credits,
                    user_credits = EXCLUDED.user_credits,
                    dlc_credits = EXCLUDED.dlc_credits,
                    total_cost = EXCLUDED.total_cost,
                    job_count = EXCLUDED.job_count,
                    avg_duration_seconds = EXCLUDED.avg_duration_seconds
                """,
                (
                    report_week_id,
                    row["project_name"],
                    float(row.get("total_credits") or 0),
                    float(row.get("compute_credits") or 0),
                    float(row.get("user_credits") or 0),
                    float(row.get("dlc_credits") or 0),
                    float(row.get("total_cost") or 0),
                    int(row.get("job_count") or 0),
                    float(row["avg_duration_seconds"])
                    if pd.notna(row.get("avg_duration_seconds"))
                    else None,
                ),
            )

        for _, row in resource_stats.iterrows():
            conn.execute(
                """
                INSERT INTO weekly_resource_class_stats (
                    report_week_id, project_name, resource_class, job_count,
                    total_credits, avg_cpu_utilization, avg_ram_utilization
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (report_week_id, project_name, resource_class) DO UPDATE SET
                    job_count = EXCLUDED.job_count,
                    total_credits = EXCLUDED.total_credits,
                    avg_cpu_utilization = EXCLUDED.avg_cpu_utilization,
                    avg_ram_utilization = EXCLUDED.avg_ram_utilization
                """,
                (
                    report_week_id,
                    row["project_name"],
                    row["resource_class"],
                    int(row.get("job_count") or 0),
                    float(row.get("total_credits") or 0),
                    float(row["avg_cpu_utilization"])
                    if pd.notna(row.get("avg_cpu_utilization"))
                    else None,
                    float(row["avg_ram_utilization"])
                    if pd.notna(row.get("avg_ram_utilization"))
                    else None,
                ),
            )

    def _push_prometheus_metrics(
        self,
        project_stats: pd.DataFrame,
        resource_stats: pd.DataFrame,
        organization: str,
        week_end: date,
    ) -> Dict[str, Any]:
        from prometheus_client import CollectorRegistry, Gauge, push_to_gateway

        registry = CollectorRegistry()
        week_timestamp = datetime.combine(
            week_end, time(23, 59, 59), tzinfo=timezone.utc
        ).timestamp()

        credits_gauge = Gauge(
            "circleci_weekly_credits_total",
            "Total credits consumed per project for the week",
            ["organization", "project"],
            registry=registry,
        )
        compute_gauge = Gauge(
            "circleci_weekly_compute_credits",
            "Compute credits per project for the week",
            ["organization", "project"],
            registry=registry,
        )
        cost_gauge = Gauge(
            "circleci_weekly_cost_usd",
            "Estimated USD cost per project for the week",
            ["organization", "project"],
            registry=registry,
        )
        jobs_gauge = Gauge(
            "circleci_weekly_job_count",
            "Job count per project for the week",
            ["organization", "project"],
            registry=registry,
        )
        resource_jobs_gauge = Gauge(
            "circleci_weekly_resource_class_jobs",
            "Job count per project and resource class for the week",
            ["organization", "project", "resource_class"],
            registry=registry,
        )

        for _, row in project_stats.iterrows():
            project = str(row["project_name"])
            credits_gauge.labels(organization=organization, project=project).set(
                float(row.get("total_credits") or 0)
            )
            compute_gauge.labels(organization=organization, project=project).set(
                float(row.get("compute_credits") or 0)
            )
            cost_gauge.labels(organization=organization, project=project).set(
                float(row.get("total_cost") or 0)
            )
            jobs_gauge.labels(organization=organization, project=project).set(
                float(row.get("job_count") or 0)
            )

        for _, row in resource_stats.iterrows():
            resource_jobs_gauge.labels(
                organization=organization,
                project=str(row["project_name"]),
                resource_class=str(row["resource_class"]),
            ).set(float(row.get("job_count") or 0))

        job_name = f"circleci_usage_{organization}_{week_end.isoformat()}"
        push_to_gateway(
            self.pushgateway_url,
            job=job_name,
            registry=registry,
            grouping_key={"week_end": week_end.isoformat()},
        )
        return {"status": "success", "job": job_name, "timestamp": week_timestamp}


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def _add_arguments(parser):
    parser.add_argument("csv_file", help="Path to the merged usage CSV file")
    parser.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL"),
        help="Postgres connection URL (or set DATABASE_URL)",
    )
    parser.add_argument(
        "--pushgateway-url",
        default=os.environ.get("PROMETHEUS_PUSHGATEWAY_URL"),
        help="Prometheus Pushgateway URL (or set PROMETHEUS_PUSHGATEWAY_URL)",
    )
    parser.add_argument("--week-start", help="Week start date (YYYY-MM-DD)")
    parser.add_argument("--week-end", help="Week end date (YYYY-MM-DD, exclusive)")
    parser.add_argument(
        "--previous-week",
        action="store_true",
        help="Use the previous calendar week (Mon–Sun)",
    )
    parser.add_argument(
        "--org-id",
        default=os.environ.get("ORG_ID"),
        help="CircleCI organization ID (or set ORG_ID; inferred from CSV if omitted)",
    )
    parser.add_argument(
        "--credit-cost",
        type=float,
        default=0.0006,
        help="Cost per credit in USD (default: 0.0006)",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        default=True,
        help="Replace existing data for the same org/week (default: true)",
    )
    parser.add_argument(
        "--no-replace",
        action="store_false",
        dest="replace",
        help="Fail if the week was already ingested",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and aggregate without writing to Postgres or Prometheus",
    )
    return parser


def add_parser(subparsers):
    parser = subparsers.add_parser(
        "store-metrics",
        help="Store usage data in Postgres and push weekly metrics to Prometheus",
    )
    return _add_arguments(parser)


def handle(args):
    try:
        if args.previous_week:
            week_start, week_end = previous_calendar_week()
        else:
            if not args.week_start or not args.week_end:
                print(
                    "Error: --week-start and --week-end required "
                    "(or use --previous-week)",
                    file=sys.stderr,
                )
                return 1
            week_start = _parse_date(args.week_start)
            week_end = _parse_date(args.week_end)

        store = MetricsStore(
            database_url=args.database_url,
            pushgateway_url=args.pushgateway_url,
            credit_cost=args.credit_cost,
        )

        print(f"Processing CSV: {args.csv_file}")
        df = store.process_csv(args.csv_file)
        print(f"Loaded {len(df):,} rows for week {week_start} to {week_end}")

        if args.dry_run:
            project_stats = aggregate_project_weekly(df, args.credit_cost)
            resource_stats = aggregate_resource_class_weekly(df)
            print(
                f"Dry run — {len(project_stats)} projects, "
                f"{len(resource_stats)} resource-class groups"
            )
            return 0

        result = store.store(
            df,
            week_start=week_start,
            week_end=week_end,
            org_id=args.org_id,
            replace=args.replace,
        )
        print(
            f"Stored week {week_start}: {result['job_count']} jobs, "
            f"{result['project_count']} projects (report_week_id={result['report_week_id']})"
        )
        if result.get("prometheus"):
            print(f"Prometheus push: {result['prometheus']['status']}")
        elif args.pushgateway_url:
            print("No Prometheus metrics pushed (no project aggregates)")
        else:
            print("Prometheus push skipped (no --pushgateway-url)")
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


def main():
    parser = argparse.ArgumentParser(
        description="Store CircleCI usage data in Postgres and push Prometheus metrics."
    )
    _add_arguments(parser)
    args = parser.parse_args()
    sys.exit(handle(args))


if __name__ == "__main__":
    main()
