variable "project_id" {
  type        = string
  description = "CircleCI project UUID (CIRCLE_PROJECT_ID in CI)."
}

variable "pipeline_id" {
  type        = string
  description = "Pipeline definition UUID from Project Settings → Project Setup."
}

variable "checkout_ref" {
  type        = string
  description = "Branch the schedule checks out and reads config from."
  default     = "main"
}

variable "cron_expression" {
  type        = string
  description = "UTC cron for the weekly trigger (Monday 09:00 matches the old scheduled workflow)."
  default     = "0 9 * * 1"
}
