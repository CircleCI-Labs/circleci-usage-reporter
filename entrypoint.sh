#!/bin/bash
set -e

./get_usage_report.py

if [ "${SEND_TO_DATADOG}" = "true" ]; then
  for csv_file in /tmp/reports/*.csv; do
    # Check if the file actually exists (in case the glob didn't match anything)
    if [ -e "$csv_file" ]; then
      ./send_to_datadog.py --site "$DATADOG_SITE" "$csv_file"
    else
      echo "No CSV files found in /tmp/reports, skipping."
      break
    fi
  done
fi
