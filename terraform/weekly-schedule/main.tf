resource "circleci_trigger" "weekly_usage" {
  project_id                              = var.project_id
  pipeline_id                             = var.pipeline_id
  event_source_provider                   = "schedule"
  event_name                              = "weekly-usage"
  checkout_ref                            = var.checkout_ref
  config_ref                              = var.checkout_ref
  event_source_schedule_cron_expression   = var.cron_expression
  event_source_schedule_attribution_actor = "system"

  # Only the weekly-usage workflow runs (see .circleci/config.yml when:).
  parameters = {
    run-weekly-usage = true
  }
}
