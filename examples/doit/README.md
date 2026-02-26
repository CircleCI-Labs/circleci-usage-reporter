# CircleCI Usage Exporter — DoiT Pipeline Setup

This guide details how to set up and run the CircleCI workflow for exporting usage data to DoiT.

## Prerequisites

- Fork this repository.
- Have a CircleCI account setup
- Obtain both:
  - CircleCI Personal API Token (**CIRCLECI_API_TOKEN**)
  - DoiT API Token (**DOIT_API_KEY**)

## Project Setup

### 1. Fork the Repository

Fork this repository to your own GitHub account.

### 2. Set Up the Project on CircleCI

- Go to CircleCI and Set-Up the project

### 3. Configure CircleCI Context

Create a CircleCI context named, for example, `my-context` (or update the name to match your preferred naming convention).

Add the following environment variables to your context:

- **CIRCLECI_API_TOKEN**: Your personal CircleCI API token.
- **DOIT_API_KEY**: Your DoiT API token.

### 4. Pipeline Environment Variables

The workflow uses parameters in the config file. Ensure your organization ID and desired values are configured:

- `org_id` (default is `${CIRCLE_ORGANIZATION_ID}`)
- `cost_per_credit` (default is `"0.0006"`)
- `job_name` (default is `"unit_tests"`)

### 5. Workflow Components

The main workflow, `use-usage-api`, runs:

- **generate-usage-report**: Downloads usage CSVs, merges, and prepares analysis.
- **generate-resource-class-analysis**: Runs analysis scripts.
- **gather-artifacts**: Collects output artifacts.

To send your metrics to DoiT Please append the following job to the main workflow:
- **send-metrics-to-doit**: Uploads merged data to DoiT.

Your workflow should look like: 

``` 
use-usage-api:
    jobs:
      - generate-usage-report:
          context:
            - my-context
      - generate-resource-class-analysis:
          requires:
            - generate-usage-report
      - send-metrics-to-doit:
          requires:
            - generate-usage-report
      - gather-artifacts:
          requires:
            - generate-resource-class-analysis

```

## Running the Pipeline

Once contexts and environment variables are configured, push a commit to your fork or manually trigger the pipeline in CircleCI.

## Manual CLI Usage

You can also use the CLI commands directly without CircleCI:

### 1. Download Usage Report

```bash
circleci-usage-reporter get \
  --org-id <your-org-id> \
  --start-date 2024-01-01 \
  --end-date 2024-01-31 \
  --output usage_report.csv
```

### 2. Merge Multiple Reports (if needed)

```bash
circleci-usage-reporter merge \
  --input-dir /tmp/reports \
  --output merged.csv
```

### 3. Send to DoiT

```bash
circleci-usage-reporter send-to-doit merged.csv \
  --api-key <your-doit-api-key>
```

### Using Environment Variables

You can use environment variables for API keys:

```bash
export DOIT_API_KEY="your-api-key"
export CIRCLECI_API_TOKEN="your-circleci-token"
export ORG_ID="your-org-id"

circleci-usage-reporter get --start-date 2024-01-01 --end-date 2024-01-31
circleci-usage-reporter send-to-doit usage_report.csv
```

### Additional Options

- `--csv-upload`: Upload CSV file directly instead of processing as events
- `--dry-run`: Process without sending (for testing)
- `--batch-size`: Batch size for events (default: `255`)

## Notes

- For updates, refer to the [main README.md](../../README.md) for changing project structure or installing dependencies.
- If updating the name of the CircleCI context, ensure it matches the value in your workflow under the `context:` key.
- **Note:** The CircleCI workflow configuration (`.circleci/config.yml`) may need to be updated to use the new CLI commands instead of direct Python script execution.

---

**This setup lets you automate exporting CircleCI usage data and uploading it to DoiT's API using CircleCI workflows.**