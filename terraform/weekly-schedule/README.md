# Weekly schedule trigger

Creates a Monday 09:00 UTC schedule trigger on `main` that sets `run-weekly-usage=true`.

**Enable once** (does not run on PRs or default pushes):

1. Allow-list URL prefix `https://raw.githubusercontent.com/CircleCI-Labs/circleci-usage-reporter/` at **Org → Orbs**.
2. Trigger the default pipeline with `apply-schedule=true` and `pipeline-definition-id` set to the pipeline UUID from **Project Settings → Project Setup**.
3. Use context `circle-token-cci-labs` (`CIRCLE_TOKEN`). Locally: `export CIRCLE_TOKEN` and `terraform apply -var=project_id=... -var=pipeline_id=...`.
