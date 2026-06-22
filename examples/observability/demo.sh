#!/usr/bin/env bash
# Local smoke test for the Postgres + Grafana + Prometheus observability stack.
#
# Usage:
#   ./demo.sh --offline          # fixture CSV, no CircleCI API (default)
#   ./demo.sh --live             # download real data via Usage API, then ingest
#   ./demo.sh --offline --no-compose   # skip docker compose up (stack already running)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
COMPOSE_FILE="$SCRIPT_DIR/docker-compose.yml"
FIXTURE_CSV="$SCRIPT_DIR/fixtures/sample_usage.csv"
OUTPUT_CSV="/tmp/reports/observability-demo.csv"

MODE="offline"
START_COMPOSE=1

DATABASE_URL="${DATABASE_URL:-postgresql://usage:usage@localhost:5432/circleci_usage}"
PROMETHEUS_PUSHGATEWAY_URL="${PROMETHEUS_PUSHGATEWAY_URL:-http://localhost:9091}"

# Fixture week: Mon 2026-06-09 through Mon 2026-06-16 (matches sample_usage.csv dates)
OFFLINE_WEEK_START="2026-06-09"
OFFLINE_WEEK_END="2026-06-16"

usage() {
  cat <<'EOF'
Usage: demo.sh [--offline | --live] [--no-compose]

  --offline     Load fixtures/sample_usage.csv (default, no API token required)
  --live        Run get + store-metrics for the previous calendar week
  --no-compose  Do not run docker compose up (use when stack is already running)
  -h, --help    Show this help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --offline) MODE="offline" ;;
    --live) MODE="live" ;;
    --no-compose) START_COMPOSE=0 ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
  shift
done

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Error: '$1' is required but not installed." >&2
    exit 1
  fi
}

previous_calendar_week() {
  if date -v-1d >/dev/null 2>&1; then
    WEEK_END="$(date -v-mon +%Y-%m-%d)"
    WEEK_START="$(date -v-1w -v-mon +%Y-%m-%d)"
  else
    WEEK_END="$(date -u -d 'last monday' +%Y-%m-%d)"
    WEEK_START="$(date -u -d 'last monday - 7 days' +%Y-%m-%d)"
  fi
}

VENV_DIR="$REPO_ROOT/.venv"

ensure_cli() {
  if command -v circleci-usage-reporter >/dev/null 2>&1; then
    return 0
  fi

  if [[ -x "$VENV_DIR/bin/circleci-usage-reporter" ]]; then
    export PATH="$VENV_DIR/bin:$PATH"
    return 0
  fi

  echo "Setting up Python virtualenv at $VENV_DIR ..."
  python3 -m venv "$VENV_DIR"
  # shellcheck disable=SC1091
  source "$VENV_DIR/bin/activate"
  python -m pip install --upgrade pip
  python -m pip install -e "$REPO_ROOT"
  export PATH="$VENV_DIR/bin:$PATH"
}

cli() {
  ensure_cli
  circleci-usage-reporter "$@"
}

wait_for_postgres() {
  echo "Waiting for Postgres..."
  for _ in $(seq 1 30); do
    if docker compose -f "$COMPOSE_FILE" exec -T postgres \
      pg_isready -U usage -d circleci_usage >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done
  echo "Error: Postgres did not become ready in time." >&2
  exit 1
}

print_urls() {
  cat <<EOF

Stack is ready:
  Grafana:     http://localhost:3000  (admin / admin)
  Prometheus:  http://localhost:9090
  Pushgateway: http://localhost:9091

Open Dashboards → CircleCI → CI/CD Platform Health
Set the time range to cover your ingested data (fixture: June 2026).

Verify Postgres:
  docker compose -f examples/observability/docker-compose.yml exec postgres \\
    psql -U usage -d circleci_usage -c "SELECT COUNT(*) FROM circleci_usage;"

Tear down:
  docker compose -f examples/observability/docker-compose.yml down -v
EOF
}

require_cmd docker
require_cmd python3

if [[ "$START_COMPOSE" -eq 1 ]]; then
  echo "Starting observability stack..."
  docker compose -f "$COMPOSE_FILE" up -d
fi

wait_for_postgres

mkdir -p "$(dirname "$OUTPUT_CSV")"

if [[ "$MODE" == "offline" ]]; then
  echo "Offline mode: loading fixture CSV..."
  cp "$FIXTURE_CSV" "$OUTPUT_CSV"
  WEEK_START="$OFFLINE_WEEK_START"
  WEEK_END="$OFFLINE_WEEK_END"
else
  echo "Live mode: downloading usage report from CircleCI API..."
  if [[ -z "${ORG_ID:-}" || -z "${CIRCLECI_API_TOKEN:-}" ]]; then
    echo "Error: set ORG_ID and CIRCLECI_API_TOKEN for --live mode." >&2
    exit 1
  fi
  previous_calendar_week
  cli get \
    --org-id "$ORG_ID" \
    --start-date "$WEEK_START" \
    --end-date "$WEEK_END" \
    --output "$OUTPUT_CSV"
fi

export DATABASE_URL PROMETHEUS_PUSHGATEWAY_URL

echo "Storing metrics (week $WEEK_START → $WEEK_END)..."
cli store-metrics "$OUTPUT_CSV" \
  --week-start "$WEEK_START" \
  --week-end "$WEEK_END" \
  --replace

ROW_COUNT="$(docker compose -f "$COMPOSE_FILE" exec -T postgres \
  psql -U usage -d circleci_usage -t -A -c "SELECT COUNT(*) FROM circleci_usage;")"

echo "Ingested $ROW_COUNT row(s) into circleci_usage."
print_urls
