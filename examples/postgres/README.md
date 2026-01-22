# PostgreSQL Integration

This guide shows how to load CircleCI usage data into a PostgreSQL database for analysis and reporting.

## Prerequisites

- PostgreSQL database (version 9.6 or higher)
- CircleCI Personal API Token (**CIRCLECI_API_TOKEN**) - if fetching data directly from API
- CircleCI Organization ID (**ORG_ID**) - if fetching data directly from API
- PostgreSQL database credentials:
  - Database name
  - Username
  - Password (**PGPASSWORD**)

## Database Setup

### 1. Create Database

First, create a PostgreSQL database:

```bash
createdb circleci_usage
```

Or using `psql`:

```sql
CREATE DATABASE circleci_usage;
```

### 2. Database Migrations

The tool automatically runs database migrations to create the schema. The migrations will:
- Create the `circleci_usage` table with all required columns
- Create indexes for optimal query performance
- Create views for common analysis queries (`job_performance` and `cost_analysis`)

If you want to skip migrations (e.g., schema already exists), use the `--skip-migrations` flag.

## Loading Data

You can load data into PostgreSQL in two ways:

### Method 1: From CSV File

If you already have a CSV file with usage data:

```bash
circleci-usage-reporter send-to-postgres \
  --input usage_report.csv \
  --database circleci_usage \
  --user postgres \
  --password your_password \
  --summary
```

### Method 2: Fetch from API and Load

Fetch data directly from the CircleCI API and load it into PostgreSQL:

```bash
circleci-usage-reporter send-to-postgres \
  --start-date 2024-01-01 \
  --end-date 2024-01-31 \
  --org-id <your-org-id> \
  --api-token <your-circleci-token> \
  --database circleci_usage \
  --user postgres \
  --password your_password \
  --summary
```

**Note:** You cannot use both `--input` and `--start-date` together. They are mutually exclusive.

## Using Environment Variables

You can use environment variables for credentials:

```bash
export PGPASSWORD="your-postgres-password"
export CIRCLECI_API_TOKEN="your-circleci-token"
export ORG_ID="your-org-id"

# From CSV file
circleci-usage-reporter send-to-postgres \
  --input usage_report.csv \
  --database circleci_usage \
  --user postgres \
  --summary

# Or fetch from API
circleci-usage-reporter send-to-postgres \
  --start-date 2024-01-01 \
  --end-date 2024-01-31 \
  --database circleci_usage \
  --user postgres \
  --summary
```

## Connection Options

- `--host`: PostgreSQL host (default: `localhost`)
- `--port`: PostgreSQL port (default: `5432`)
- `--database`: Database name (required)
- `--user`: PostgreSQL username (required)
- `--password`: PostgreSQL password (or set `PGPASSWORD` env var)

## Additional Options

- `--batch-size`: Number of records to insert per batch (default: `1000`)
- `--skip-migrations`: Skip running database migrations before loading data
- `--summary`: Show data summary after loading (includes record counts, date ranges, job status breakdown, etc.)

## Database Schema

The tool creates the following database objects:

### Table: `circleci_usage`

Contains all CircleCI usage data with columns for:
- Organization and project information
- Pipeline and workflow details
- Job execution data
- Resource utilization metrics
- Credit consumption breakdown
- Timestamps for tracking

### Indexes

Multiple indexes are created for optimal query performance:
- `idx_circleci_usage_organization_id`
- `idx_circleci_usage_project_id`
- `idx_circleci_usage_pipeline_id`
- `idx_circleci_usage_workflow_id`
- `idx_circleci_usage_job_name`
- `idx_circleci_usage_job_build_status`
- `idx_circleci_usage_resource_class`
- `idx_circleci_usage_executor`
- `idx_circleci_usage_pipeline_created_at`
- `idx_circleci_usage_job_run_started_at`
- `idx_circleci_usage_total_credits`

### Views

#### `job_performance`

Aggregated job performance metrics grouped by job name, resource class, and executor:
- Job counts
- Duration statistics (avg, median, p95)
- CPU and RAM utilization
- Credit usage
- Success rates

#### `cost_analysis`

Daily cost analysis grouped by organization, project, resource class, and executor:
- Job counts per day
- Total and average credits
- Breakdown by credit type (compute, DLC, user, storage, network, lease)

## Querying the Data

### Example Queries

**Total credits used by organization:**
```sql
SELECT 
    organization_name,
    SUM(total_credits) as total_credits
FROM circleci_usage
GROUP BY organization_name
ORDER BY total_credits DESC;
```

**Job performance analysis:**
```sql
SELECT * FROM job_performance
WHERE job_count > 100
ORDER BY total_credits_used DESC
LIMIT 20;
```

**Daily cost breakdown:**
```sql
SELECT * FROM cost_analysis
WHERE usage_date >= CURRENT_DATE - INTERVAL '30 days'
ORDER BY usage_date DESC, total_credits DESC;
```

**Most expensive jobs:**
```sql
SELECT 
    job_name,
    resource_class,
    COUNT(*) as job_count,
    SUM(total_credits) as total_credits,
    AVG(total_credits) as avg_credits_per_job
FROM circleci_usage
GROUP BY job_name, resource_class
ORDER BY total_credits DESC
LIMIT 10;
```

**Failed jobs analysis:**
```sql
SELECT 
    job_name,
    COUNT(*) as total_jobs,
    SUM(CASE WHEN job_build_status = 'failed' THEN 1 ELSE 0 END) as failed_jobs,
    ROUND(
        SUM(CASE WHEN job_build_status = 'failed' THEN 1 ELSE 0 END)::DECIMAL / COUNT(*) * 100, 
        2
    ) as failure_rate_pct
FROM circleci_usage
GROUP BY job_name
HAVING COUNT(*) > 10
ORDER BY failure_rate_pct DESC;
```

## Database Migrations

The tool uses Alembic for database migrations. Migrations are automatically run when you execute `send-to-postgres` (unless `--skip-migrations` is used).

### Manual Migration Management

If you need to manage migrations manually:

```bash
# Upgrade to latest version
alembic upgrade head

# Check current version
alembic current

# View migration history
alembic history

# Rollback one version
alembic downgrade -1
```

## Notes

- Migrations run within a transaction, so they either succeed completely or roll back
- The `--summary` flag provides a quick overview of loaded data
- Large datasets are loaded in batches (configurable via `--batch-size`)
- The tool automatically handles temporary files when fetching from the API
