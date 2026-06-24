# Postgres + Grafana + Prometheus Observability

Store CircleCI Usage API data in Postgres and visualize it with the provisioned **CI/CD Platform Health** Grafana dashboard. Run on a **weekly schedule** to build historical trends (credit burn, cost by project, resource utilization, and more).

## Prerequisites

- Docker and Docker Compose
- Python 3.8+ (a virtualenv is created automatically by `demo.sh`)
- CircleCI Personal API Token (`CIRCLECI_API_TOKEN`) — **live mode only**
- CircleCI Organization ID (`ORG_ID`) — **live mode only**

## Quick start

### Fastest path: run the demo script

From the repo root (no CircleCI token required for offline mode). The script creates `.venv` and installs dependencies automatically — do **not** use system `pip install` on macOS/Homebrew Python.

```bash
chmod +x examples/observability/demo.sh
./examples/observability/demo.sh --offline
```

| Mode | Command | What it does |
|------|---------|--------------|
| Offline (default) | `./demo.sh --offline` | Starts compose, loads `fixtures/sample_usage.csv`, opens-ready Grafana |
| Live API | `./demo.sh --live` | Requires `ORG_ID` + `CIRCLECI_API_TOKEN`; runs `get` then `store-metrics` |
| Stack already up | `./demo.sh --offline --no-compose` | Skips `docker compose up` |

**Manual install** (if not using `demo.sh`):

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

### Manual setup

#### 1. Start the observability stack

```bash
docker compose -f examples/observability/docker-compose.yml up -d
```

| Service | URL |
|---------|-----|
| Grafana | http://localhost:3000 (admin / admin) |
| Prometheus | http://localhost:9090 |
| Pushgateway | http://localhost:9091 |
| Postgres | `localhost:5432` (user `usage`, password `usage`, db `circleci_usage`) |

The **CI/CD Platform Health** dashboard loads automatically from `grafana/dashboards/cicd-platform-health.json`.

### 2. Download and store a usage report

```bash
export ORG_ID="your-org-id"
export CIRCLECI_API_TOKEN="your-token"
export DATABASE_URL="postgresql://usage:usage@localhost:5432/circleci_usage"
export PROMETHEUS_PUSHGATEWAY_URL="http://localhost:9091"

# Previous calendar week (Mon–Sun) — macOS
circleci-usage-reporter get \
  --start-date $(date -v-1w -v-mon +%Y-%m-%d) \
  --end-date $(date -v-mon +%Y-%m-%d) \
  --output /tmp/reports/merged.csv

circleci-usage-reporter store-metrics /tmp/reports/merged.csv \
  --previous-week \
  --replace
```

Linux date alternative:

```bash
circleci-usage-reporter get \
  --start-date $(date -d 'last monday - 7 days' +%Y-%m-%d) \
  --end-date $(date -d 'last monday' +%Y-%m-%d) \
  --output /tmp/reports/merged.csv
```

### 3. View dashboards

Open Grafana at http://localhost:3000 and select **CI/CD Platform Health** under the CircleCI folder.

After two or more weekly ingests, use the time picker (`now-30d` default) to compare week-over-week trends in panels like **Daily Credit Burn & Cumulative Usage** and **Activity + Cost Correlation**.

## Weekly schedule (recommended)

Run the ingest every Monday for the previous week:

| Method | How |
|--------|-----|
| **CircleCI schedule** | Use the `weekly-usage-report` workflow in `.circleci/config.yml` (requires `DATABASE_URL` and `PROMETHEUS_PUSHGATEWAY_URL` in a CircleCI context) |
| **Host cron** | `0 9 * * 1` — run `get` + `store-metrics --previous-week` |
| **Docker cron sidecar** | Mount a cron script that calls the reporter container |

## `store-metrics` command

```bash
circleci-usage-reporter store-metrics usage_report.csv \
  --week-start 2026-06-09 \
  --week-end 2026-06-16 \
  --database-url $DATABASE_URL \
  --pushgateway-url $PROMETHEUS_PUSHGATEWAY_URL \
  --replace
```

| Flag | Env var | Description |
|------|---------|-------------|
| `--database-url` | `DATABASE_URL` | Postgres connection URL |
| `--pushgateway-url` | `PROMETHEUS_PUSHGATEWAY_URL` | Optional Prometheus Pushgateway URL |
| `--previous-week` | — | Use previous Mon–Sun calendar week |
| `--week-start` / `--week-end` | — | Explicit date range (end is exclusive) |
| `--org-id` | `ORG_ID` | Org ID (inferred from CSV if omitted) |
| `--credit-cost` | — | USD per credit (default `0.0006`) |
| `--replace` | — | Replace existing week data (default) |
| `--no-replace` | — | Fail if week already ingested |
| `--dry-run` | — | Parse and aggregate without writing |

## Data model

| Table | Purpose |
|-------|---------|
| `circleci_usage` | Full Usage API job rows (powers Grafana SQL panels) |
| `report_weeks` | Ingest metadata per org + week |
| `weekly_project_stats` | Per-project weekly rollups (Prometheus + WoW) |
| `weekly_resource_class_stats` | Per-project resource-class rollups |

## Dashboard sections

| Section | Populated by Usage API |
|---------|------------------------|
| Org Health Scorecard | Yes |
| Pipeline Activity | Yes |
| Performance | Yes |
| Cost & Optimization | Yes |
| Credit Burn & Forecast | Yes |
| Smarter Testing — TIA Burst Demo | No — requires `tia_test_summary` table |
| Flaky Test Fix — Chunk Impact | Yes (when `flaky-todo-list` project exists) |
| Compliance — Audit Log Stream | No — requires `circleci_audit_logs` table |

Optional table schemas are documented as comments in `postgres/init.sql`. Populate them with your own tooling if you need those panels.

## Prometheus metrics

Weekly aggregates are pushed to Pushgateway:

- `circleci_weekly_credits_total`
- `circleci_weekly_compute_credits`
- `circleci_weekly_cost_usd`
- `circleci_weekly_job_count`
- `circleci_weekly_resource_class_jobs`

## Tear down

```bash
docker compose -f examples/observability/docker-compose.yml down -v
```
