#!/usr/bin/env python3
"""
Get CircleCI usage report from the API.
"""

import gzip
import json
import os
import sys
import time

import requests


def _add_arguments(parser):
    """Add arguments to a parser object."""
    parser.add_argument(
        '--org-id',
        help='CircleCI organization ID (or set ORG_ID env var)'
    )
    parser.add_argument(
        '--start-date',
        required=True,
        help='Start date (YYYY-MM-DD)'
    )
    parser.add_argument(
        '--end-date',
        required=True,
        help='End date (YYYY-MM-DD)'
    )
    parser.add_argument(
        '--api-token',
        help='CircleCI API token (or set CIRCLECI_API_TOKEN env var)'
    )
    parser.add_argument(
        '--output',
        default='usage_report.csv',
        help='Output file path (default: usage_report.csv)'
    )
    return parser


def add_parser(subparsers):
    """Add get command parser."""
    parser = subparsers.add_parser(
        'get',
        help='Request and download a CircleCI usage report'
    )
    return _add_arguments(parser)


def handle(args):
    """Execute the get command."""
    # Get org_id from CLI arg or environment variable
    org_id = args.org_id or os.getenv('ORG_ID')
    
    # Get API token from CLI arg or environment variables
    api_token = args.api_token or os.getenv('CIRCLECI_API_TOKEN') or os.getenv('CIRCLECI_TOKEN')
    
    # Get dates from CLI args (required)
    start_date = args.start_date
    end_date = args.end_date
    
    # Get output from CLI arg (has default)
    output = args.output

    if not api_token:
        print("Error: CircleCI API token required. Use --api-token or set CIRCLECI_API_TOKEN or CIRCLECI_TOKEN env var", file=sys.stderr)
        return 1

    if not org_id:
        print("Error: Organization ID required. Use --org-id or set ORG_ID env var", file=sys.stderr)
        return 1

    if not start_date:
        print("Error: Start date required. Use --start-date", file=sys.stderr)
        return 1

    if not end_date:
        print("Error: End date required. Use --end-date", file=sys.stderr)
        return 1

    post_data = {
        "start": f"{start_date}T00:00:01Z",
        "end": f"{end_date}T00:00:01Z",
        "shared_org_ids": []
    }

    print(f"Requesting usage report for org {org_id} from {start_date} to {end_date}...")

    response = requests.post(
        f"https://circleci.com/api/v2/organizations/{org_id}/usage_export_job",
        headers={"Circle-Token": api_token, "Content-Type": "application/json"},
        data=json.dumps(post_data)
    )

    if response.status_code != 201:
        print(f"Error: Failed to request report. Status: {response.status_code}", file=sys.stderr)
        print(f"Response: {response.text}", file=sys.stderr)
        return 1

    data = response.json()
    report_id = data.get("usage_export_job_id")
    print(f"Report requested successfully. Report ID: {report_id}")

    # Poll for report completion
    for attempt in range(5):
        print(f"Checking if report is ready (attempt {attempt + 1}/5)...")
        time.sleep(10)

        report = requests.get(
            f"https://circleci.com/api/v2/organizations/{org_id}/usage_export_job/{report_id}",
            headers={"Circle-Token": api_token}
        ).json()

        if report.get("state") == "completed":
            print("Report generated. Downloading...")
            download_url = report.get("download_urls")[0]

            download_response = requests.get(download_url)
            decompressed_data = gzip.decompress(download_response.content).decode('utf-8')

            with open(output, 'w') as f:
                f.write(decompressed_data)

            print(f"Report saved to {output}")
            return 0
        elif report.get("state") == "failed":
            print("Error: Report generation failed", file=sys.stderr)
            return 1
        else:
            print(f"Report status: {report.get('state')}")

    print("Error: Report generation timed out", file=sys.stderr)
    return 1


def main():
    """Standalone entry point."""
    import argparse
    parser = argparse.ArgumentParser(description='Get CircleCI usage report from the API.')
    _add_arguments(parser)
    args = parser.parse_args()
    sys.exit(handle(args))


if __name__ == '__main__':
    main()
