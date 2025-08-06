# CircleCI Usage API Exporter

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
- If sending metrics to Datadog, then a `DD_API_KEY` is required.

### Caveats

- My python skillz aren't great.
- If using Datadog, there will be extra charges for storing these custom metrics. See
    - Alternatives include using the [CircleCI Datadog integration](https://docs.datadoghq.com/integrations/circleci/), as well as [outbound  webhooks](https://circleci.com/docs/webhooks/#outbound-webhooks) from CircleCI.