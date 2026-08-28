<h1 align="center">
  <br>
  <a href="https://www.circleci.com/"><img src="./circleci-logo.png" alt="CircleCI" width="200"></a>
  <br>
  Usage API Reporter
  <br>
</h1>

<h4 align="center">Open-source tools and examples for working with CircleCI's <a href="https://circleci.com/docs/api/v2/index.html#tag/Usage" target="_blank">Usage API</a> to optimize costs and improve pipeline performance.</h4>

<p align="center">
  <a href="#introduction">Introduction</a> •
  <a href="#quick-start">Quick Start</a> •
  <a href="#whats-included">What's Included</a> •
  <a href="#minimum-requirements">Minimum Requirements</a> •
    <a href="#documentation">Documentation</a> •
  <a href="#contributing">Contributing</a>
</p>


> This repository is part of CircleCI Labs - solutions developed by CircleCI's field engineering team based on real customer needs.
> 
> ✅ **Created by Field Engineers @ CircleCI**  
> ✅ **Used by real CircleCI customers**  
> ❌ **NOT officially supported by CircleCI support**

## Introduction

CircleCI's Usage API provides powerful data about your CI/CD pipelines. This toolkit helps you quickly turn that data into actionable insights with ready-to-use scripts, analysis templates, and visualization integrations.

### What you can discover:

* Which jobs are burning through your budget 💰
* Where your pipelines are slowest 🐌
* Which resources are underutilized 📉
* How to right-size your compute classes ⚡

## Quick Start

### Install with pip

```bash
git clone git@github.com:CircleCI-Labs/circleci-usage-reporter.git
cd circleci-usage-reporter
pip install -e .
```

After installation, the `circleci-usage-reporter` command is available system-wide:

```bash
circleci-usage-reporter --help
```

> **Note:** Requires Python 3.8+. Use a virtual environment or a version manager such as pyenv, conda, or asdf if needed.

### With Docker

```bash
git clone git@github.com:CircleCI-Labs/circleci-usage-reporter.git
cd circleci-usage-reporter
docker build . -t circleci-usage-reporter:latest
docker run --rm circleci-usage-reporter --help
```

## Commands

All commands share a common CLI entry point: `circleci-usage-reporter <command> [options]`.

### `get` — Download a usage report

Requests a usage export from the CircleCI API, waits for it to be ready using exponential backoff, downloads all result files, and automatically merges them into a single CSV.

```bash
circleci-usage-reporter get \
  --org-id <your-org-id> \
  --start-date 2024-01-01 \
  --end-date 2024-01-31 \
  --output usage_report.csv
```

| Flag | Default | Description |
|------|---------|-------------|
| `--org-id` | `$ORG_ID` | CircleCI organisation ID |
| `--api-token` | `$CIRCLECI_API_TOKEN` | CircleCI personal API token |
| `--start-date` | required | Report start date (YYYY-MM-DD) |
| `--end-date` | required | Report end date (YYYY-MM-DD) |
| `--output` | `usage_report.csv` | Output file path |

**Using environment variables instead of flags:**

```bash
export ORG_ID="a1b2c3d4-e5f6-7890-abcd-ef1234567890"
export CIRCLECI_API_TOKEN="your-personal-api-token"

circleci-usage-reporter get \
  --start-date 2024-01-01 \
  --end-date 2024-01-31
```

**Saving to a specific directory:**

```bash
circleci-usage-reporter get \
  --org-id a1b2c3d4-e5f6-7890-abcd-ef1234567890 \
  --start-date 2024-01-01 \
  --end-date 2024-01-31 \
  --output ~/reports/january_2024.csv
```

> **Finding your Org ID:** Go to **app.circleci.com → Organization Settings** — the ID is shown at the top of the page.  
> **Getting an API token:** Go to **app.circleci.com → User Settings → Personal API Tokens**.

---

### `top-workflows` / `top-jobs` — Rank a project's usage

Prints a credits table for the last 30 days. Token: `$CIRCLECI_API_TOKEN`, `$CIRCLE_TOKEN`, or `$CIRCLECI_TOKEN`.

```bash
circleci-usage-reporter top-workflows --project-id "$CIRCLE_PROJECT_ID"
circleci-usage-reporter top-jobs --project-id "$CIRCLE_PROJECT_ID"
```

Run both in the same job so they share one Usage export. The Usage API allows 10 exports per hour per org — do not run these commands frequently.

---

### `merge` — Merge CSV files

Merges multiple CSV files from a directory into a single file, deduplicating headers.

```bash
circleci-usage-reporter merge \
  --input-dir /tmp/reports \
  --output merged.csv
```

---

### `send-to-datadog` — Send data to Datadog

Processes a usage CSV and sends metrics to Datadog.

```bash
circleci-usage-reporter send-to-datadog usage_report.csv \
  --api-key <dd-api-key> \
  --app-key <dd-app-key>
```

See [`examples/datadog/`](examples/datadog/README.md) for full setup instructions.

---

### `send-to-doit` — Send data to DoiT

Uploads a usage CSV to the DoiT DataHub API.

```bash
circleci-usage-reporter send-to-doit usage_report.csv \
  --api-key <doit-api-key>
```

See [`examples/doit/`](examples/doit/README.md) for full setup instructions.

---

### `store-metrics` — Store data in Postgres + Prometheus

Loads a usage CSV into Postgres (`circleci_usage` table) and pushes weekly aggregate metrics to Prometheus Pushgateway. Designed for weekly schedule-trigger runs (`terraform/weekly-schedule/`; `get` in CI uses the previous calendar month).

```bash
circleci-usage-reporter store-metrics usage_report.csv \
  --previous-week \
  --database-url postgresql://usage:usage@localhost:5432/circleci_usage \
  --pushgateway-url http://localhost:9091
```

See [`examples/observability/`](examples/observability/README.md) for the full Postgres + Grafana + Prometheus stack.

---

### `create-graph` — Generate a credits graph

Creates a bar chart of total credits consumed per project from a usage CSV.

```bash
circleci-usage-reporter create-graph usage_report.csv \
  --output /tmp/credits_by_project.png
```

---

### `run-analysis` — Generate an HTML analysis report

Runs a Jupyter notebook analysis against a usage CSV and produces a self-contained HTML report.

```bash
circleci-usage-reporter run-analysis \
  --type job \
  --project my-project \
  --input usage_report.csv
```

| `--type` value | Description |
|----------------|-------------|
| `job` | Job-level credit and duration breakdown |
| `project` | Project-level credit usage over time |
| `compute-credits` | Compute credit consumption by resource class |
| `resource` | Resource class utilisation analysis |

---

## Environment variables

| Variable | Used by |
|----------|---------|
| `CIRCLECI_API_TOKEN` / `CIRCLE_TOKEN` / `CIRCLECI_TOKEN` | `get`, `top-workflows`, `top-jobs` |
| `ORG_ID` / `CIRCLE_ORGANIZATION_ID` | `get`, `top-workflows`, `top-jobs` |
| `CIRCLE_PROJECT_ID` | `top-workflows`, `top-jobs` |
| `DD_API_KEY` | `send-to-datadog` |
| `DD_APP_KEY` | `send-to-datadog` |
| `DOIT_API_KEY` | `send-to-doit` |
| `DATABASE_URL` | `store-metrics` |
| `PROMETHEUS_PUSHGATEWAY_URL` | `store-metrics` |

---

## What's Included

* **Unified CLI** — all commands under a single `circleci-usage-reporter` entry point
* **Auto-merging downloads** — `get` downloads and merges report files automatically
* **Exponential backoff** — `get` polls for report readiness efficiently rather than waiting a fixed interval
* **Datadog integration** — send usage metrics directly to Datadog
* **DoiT integration** — upload usage data to DoiT DataHub
* **Analysis reports** — generate HTML reports from Jupyter notebooks
* **Visualization** — credit usage graphs per project

## Minimum Requirements

* Python 3.8+
* A CircleCI personal API token ([get yours here](https://app.circleci.com/settings/user/tokens))
* An organisation ID (found in **Organization Settings** in the CircleCI app)

## Documentation

* [**API Reference**](https://circleci.com/docs/api/v2/index.html#tag/Usage) - Usage API endpoints and data schema
* **[Examples](examples/)** - BI tool templates, analysis notebooks, and integration guides

## Contributing

* Request additions
* Add new visualization templates
* Improve analysis algorithms
* Share real-world optimization stories
* Fix bugs or improve documentation
* Add support for other BI tools