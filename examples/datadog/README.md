# DataDog Integration

This guide shows how to send CircleCI usage data to Datadog for monitoring and analysis.

## Prerequisites

- CircleCI Personal API Token (**CIRCLECI_API_TOKEN**)
- Datadog API Key (**DD_API_KEY**)
- Datadog Application Key (**DD_APP_KEY**) - Optional, but recommended

## Steps

1. **Download usage report:**
   ```bash
   circleci-usage-reporter get \
     --org-id <your-org-id> \
     --start-date 2024-01-01 \
     --end-date 2024-01-31 \
     --output usage_report.csv
   ```

2. **Send data to Datadog:**
   ```bash
   circleci-usage-reporter send-to-datadog usage_report.csv \
     --api-key <your-datadog-api-key> \
     --app-key <your-datadog-app-key>  # Optional
   ```

## Using Environment Variables

You can also use environment variables for API keys:

```bash
export DD_API_KEY="your-api-key"
export DD_APP_KEY="your-app-key"  # Optional
export CIRCLECI_API_TOKEN="your-circleci-token"
export ORG_ID="your-org-id"

circleci-usage-reporter get --start-date 2024-01-01 --end-date 2024-01-31
circleci-usage-reporter send-to-datadog usage_report.csv
```

## Additional Options

- `--site`: Specify Datadog site (default: `datadoghq.com`, options: `datadoghq.eu`, `us3.datadoghq.com`, `us5.datadoghq.com`)
- `--batch-size`: Number of metrics per batch (default: `1000`)
- `--events`: Also send events to Datadog
- `--dry-run`: Process without sending (for testing)
