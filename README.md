# CircleCI Usage API Exporter

This tool helps you analyze CircleCI credit usage by generating usage reports and visualizing the data.

## Prerequisites

- Python 3.x
- Required Python packages:
  - pandas
  - numpy
  - matplotlib
  - seaborn
  - requests

Install the required packages:
```bash
pip install pandas numpy matplotlib seaborn requests
```

## Environment Variables

Set these environment variables before running the scripts:
```bash
export ORG_ID="your-organization-id"  # e.g., c53c93bf-aea8-45c3-9aae-984a3f5229a3
export CIRCLECI_API_TOKEN="your-api-token"  # e.g., CCIPAT_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

## Available Scripts

### 1. Report Generation Scripts

a. **Generate Single Report**
```bash
python src/get_usage_report.py
```
This script will:
- Request a usage report for a specified date range
- Download and save the report in `/tmp/reports/`
- Accepts environment variables:
  - `START_DATE`: Start date for the report
  - `END_DATE`: End date for the report
  - `FILENAME_PREFIX`: Optional prefix for the output file (default: 'usage_report')

b. **Generate Full Year Report**
```bash
python src/get_full_year_report.py
```
This script will:
- Generate reports for each month from July 2024 to May 2025
- Handle API rate limits with retries
- Save each month's report with a unique filename
- Combine all reports into a single file

### 2. Data Processing Scripts

a. **Combine Report Chunks**
```bash
python src/combine_chunks.py
```
This script will:
- Read all chunk files from `/tmp/reports/`
- Combine them into a single file: `/tmp/reports/usage_report_combined.csv`

b. **Merge CSV Files**
```bash
python src/merge.py
```
This script will:
- Merge multiple CSV files into a single file
- Handle duplicate headers

### 3. Analysis Scripts

a. **Weekly Usage Analysis**
```bash
python src/analyze_weekly_usage.py
```
This script will:
- Calculate weekly credit usage (Monday-Sunday)
- Generate a plot with:
  - Weekly credit usage line
  - Trend line showing overall usage direction
- Save as `/tmp/reports/weekly_credit_usage_2024_2025.png`
- Automatically open the plot in Preview

b. **Monthly Usage Analysis**
```bash
python src/analyze_monthly_usage.py
```
This script will:
- Calculate monthly credit usage
- Show month-over-month growth rates
- Generate a bar chart with:
  - Monthly totals
  - Value labels on each bar
  - Month-over-month growth percentages
- Save as `/tmp/reports/monthly_credit_usage.png`
- Automatically open the plot in Preview

c. **Project Credit Analysis**
```bash
python src/create_graph.py
```
This script will:
- Group and sort projects by total credit usage
- Generate a bar graph showing credits per project
- Save sorted project data to `sorted_credits.csv`
- Save visualization as `/tmp/reports/total_credits_per_project.png`

### 4. Integration Scripts

a. **Datadog Integration**
```bash
python src/send_to_datadog.py
```
This script will:
- Parse the merged CSV files
- Send custom metrics to Datadog
- Requires `DATADOG_API_KEY` environment variable

## Output Files

- `/tmp/reports/usage_report_*.csv`: Individual report files
- `/tmp/reports/usage_report_combined.csv`: Combined usage data
- `/tmp/reports/weekly_credit_usage_2024_2025.png`: Weekly usage visualization
- `/tmp/reports/monthly_credit_usage.png`: Monthly usage visualization
- `/tmp/reports/total_credits_per_project.png`: Project-level credit usage visualization
- `sorted_credits.csv`: Sorted project credit usage data

## Notes

- The CircleCI API has a 31-day limit for usage reports, which is why we split the date range into chunks
- All visualizations show actual numbers (not scientific notation) for better readability
- Plots are automatically opened in Preview after generation
- The weekly analysis includes a trend line to show overall usage direction
- The monthly analysis includes growth rates to track usage changes

---
**Disclaimer:**

CircleCI Labs, including this repo, is a collection of solutions developed by members of CircleCI's field engineering teams through our engagement with various customer needs.

-   ✅ Created by engineers @ CircleCI
-   ✅ Used by real CircleCI customers
-   ❌ **not** officially supported by CircleCI support

---

## Introduction

This tool outlines using the CircleCI Usage API to create and download usage reports. The data is then merged and transformed into a graph to show credit usage per project.

For more info on the API itself, visit the docs [here](https://circleci.com/docs/api/v2/index.html#tag/Usage).

All the outputs are saved as an [artifact](https://circleci.com/docs/artifacts/) on CircleCI.

### Just added - Datadog Metrics

The project has been updated to include a script that will parse the merged csv files, and send these as custom metrics to Datadog for analysis.

### Use Cases

While the implementation shown in this project is simple, there are many use cases for implementing the Usage API in this way. 

Some of the advantages include:

- [Scheduling the pipeline](https://circleci.com/docs/scheduled-pipelines/) to run weekly, to enable users to target projects that have a higher credit usage
- Enabling the comparison of weekly results
- Can be combined with the [Slack orb](https://circleci.com/developer/orbs/orb/circleci/slack) to send notifications on specific usage metrics
- Can be amended to target job-level data instead, to track the cost of failing jobs
- Can group projects by team, to enable cross-company billing

## Tools

To learn more about working with `*.csv` files, and transforming the data once it's downloaded, check out [pandas](https://pandas.pydata.org/).

To learn more about graphs using python, check out [Matplotlib](https://matplotlib.org/stable/).

## Requirements

- A CircleCI [personal API token](https://circleci.com/docs/managing-api-tokens/#creating-a-personal-api-token) is required in order to use the API. This is saved with the name `CIRCLECI_API_TOKEN`, in a context.
- A date range is required. These are specified using the `START_DATE` and `END_DATE` environment variables
- An organisation ID is required. This defaults to the ID of the organisation that is executing the job on CircleCI.
- If sending metrics to Datadog, then a `DATADOG_API_KEY` is required.

### Caveats

- My python skillz aren't great.
- If using Datadog, there will be extra charges for storing these custom metrics. See
    - Alternatives include using the [CircleCI Datadog integration](https://docs.datadoghq.com/integrations/circleci/), as well as [outbound  webhooks](https://circleci.com/docs/webhooks/#outbound-webhooks) from CircleCI.