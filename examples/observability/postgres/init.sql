-- CircleCI Usage Reporter — Postgres schema for Grafana dashboards
-- Database name: circleci_usage (see docker-compose.yml)

CREATE TABLE IF NOT EXISTS report_weeks (
    id              SERIAL PRIMARY KEY,
    week_start      DATE NOT NULL,
    week_end        DATE NOT NULL,
    org_id          TEXT NOT NULL,
    org_name        TEXT,
    job_count       INTEGER NOT NULL DEFAULT 0,
    ingested_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (org_id, week_start)
);

CREATE TABLE IF NOT EXISTS circleci_usage (
    id                          BIGSERIAL PRIMARY KEY,
    report_week_id              INTEGER NOT NULL REFERENCES report_weeks(id) ON DELETE CASCADE,
    organization_id             TEXT,
    organization_name           TEXT,
    project_id                  TEXT,
    project_name                TEXT,
    pipeline_id                 TEXT,
    pipeline_number             INTEGER,
    pipeline_created_at         TIMESTAMPTZ,
    pipeline_trigger_source     TEXT,
    pipeline_trigger_user_id    TEXT,
    workflow_id                 TEXT,
    workflow_name               TEXT,
    is_workflow_successful      BOOLEAN,
    workflow_first_job_queued_at TIMESTAMPTZ,
    workflow_first_job_started_at TIMESTAMPTZ,
    workflow_stopped_at         TIMESTAMPTZ,
    job_id                      TEXT NOT NULL,
    job_name                    TEXT,
    job_build_status            TEXT,
    job_run_number              INTEGER,
    job_run_started_at          TIMESTAMPTZ,
    job_run_stopped_at          TIMESTAMPTZ,
    job_run_seconds             DOUBLE PRECISION,
    resource_class              TEXT,
    executor                    TEXT,
    operating_system            TEXT,
    parallelism                 INTEGER,
    vcs_name                    TEXT,
    vcs_url                     TEXT,
    vcs_branch                  TEXT,
    total_credits               DOUBLE PRECISION,
    compute_credits             DOUBLE PRECISION,
    user_credits                DOUBLE PRECISION,
    dlc_credits                 DOUBLE PRECISION,
    storage_credits             DOUBLE PRECISION,
    network_credits             DOUBLE PRECISION,
    lease_credits               DOUBLE PRECISION,
    median_cpu_utilization_pct  DOUBLE PRECISION,
    max_cpu_utilization_pct     DOUBLE PRECISION,
    median_ram_utilization_pct  DOUBLE PRECISION,
    max_ram_utilization_pct     DOUBLE PRECISION,
    is_unregistered_user        BOOLEAN,
    last_build_finished_at      TIMESTAMPTZ,
    UNIQUE (job_id, report_week_id)
);

CREATE INDEX IF NOT EXISTS idx_circleci_usage_pipeline_created_at
    ON circleci_usage (pipeline_created_at);
CREATE INDEX IF NOT EXISTS idx_circleci_usage_project_name
    ON circleci_usage (project_name);
CREATE INDEX IF NOT EXISTS idx_circleci_usage_job_name
    ON circleci_usage (job_name);
CREATE INDEX IF NOT EXISTS idx_circleci_usage_resource_class
    ON circleci_usage (resource_class);
CREATE INDEX IF NOT EXISTS idx_circleci_usage_report_week_id
    ON circleci_usage (report_week_id);

CREATE TABLE IF NOT EXISTS weekly_project_stats (
    id                  SERIAL PRIMARY KEY,
    report_week_id      INTEGER NOT NULL REFERENCES report_weeks(id) ON DELETE CASCADE,
    project_name        TEXT NOT NULL,
    total_credits       DOUBLE PRECISION NOT NULL DEFAULT 0,
    compute_credits     DOUBLE PRECISION NOT NULL DEFAULT 0,
    user_credits        DOUBLE PRECISION NOT NULL DEFAULT 0,
    dlc_credits         DOUBLE PRECISION NOT NULL DEFAULT 0,
    total_cost          DOUBLE PRECISION NOT NULL DEFAULT 0,
    job_count           INTEGER NOT NULL DEFAULT 0,
    avg_duration_seconds DOUBLE PRECISION,
    UNIQUE (report_week_id, project_name)
);

CREATE TABLE IF NOT EXISTS weekly_resource_class_stats (
    id                      SERIAL PRIMARY KEY,
    report_week_id          INTEGER NOT NULL REFERENCES report_weeks(id) ON DELETE CASCADE,
    project_name            TEXT NOT NULL,
    resource_class          TEXT NOT NULL,
    job_count               INTEGER NOT NULL DEFAULT 0,
    total_credits           DOUBLE PRECISION NOT NULL DEFAULT 0,
    avg_cpu_utilization     DOUBLE PRECISION,
    avg_ram_utilization     DOUBLE PRECISION,
    UNIQUE (report_week_id, project_name, resource_class)
);

CREATE INDEX IF NOT EXISTS idx_weekly_project_stats_report_week
    ON weekly_project_stats (report_week_id);
CREATE INDEX IF NOT EXISTS idx_weekly_resource_class_stats_report_week
    ON weekly_resource_class_stats (report_week_id);

-- Optional tables (not populated by circleci-usage-reporter).
-- Uncomment and adapt if you ingest TIA or audit log data separately.
--
-- CREATE TABLE IF NOT EXISTS tia_test_summary (
--     id                      BIGSERIAL PRIMARY KEY,
--     pipeline_number         INTEGER,
--     job_name                TEXT,
--     branch                  TEXT,
--     job_status              TEXT,
--     tests_run               INTEGER,
--     job_duration_seconds    DOUBLE PRECISION
-- );
--
-- CREATE TABLE IF NOT EXISTS circleci_audit_logs (
--     id          BIGSERIAL PRIMARY KEY,
--     created_at  TIMESTAMPTZ NOT NULL,
--     actor_name  TEXT,
--     action      TEXT,
--     target_name TEXT,
--     payload     JSONB
-- );
