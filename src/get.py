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

    # Determine output directory
    # If output ends with / or is an existing directory, use it as directory
    # Otherwise, extract directory from the path
    if output.endswith('/') or os.path.isdir(output):
        output_dir = output.rstrip('/')
    else:
        output_dir = os.path.dirname(output) if os.path.dirname(output) else '.'
    
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)

    # Check if the report is ready for downloading as it can take a while to process
    # Use exponential backoff with a maximum wait time cap
    base_delay = 10  # Start with 10 seconds
    max_wait_time = 60  # Cap at 1 minute (60 seconds)
    attempt = 0
    
    while True:
        attempt += 1
        print(f"Checking if report can be downloaded (attempt {attempt})...")
        report = requests.get(
            f"https://circleci.com/api/v2/organizations/{org_id}/usage_export_job/{report_id}",
            headers={"Circle-Token": api_token}
        ).json()

        report_status = report.get("state")

        # Download the report and save it
        if report_status == "completed":
            print("Report generated. Now Downloading...")
            download_urls = report.get("download_urls", [])

            for idx, url in enumerate(download_urls):
                r = requests.get(url)
                # Save compressed file temporarily
                temp_gz_path = os.path.join(output_dir, f"usage_report_{idx}.csv.gz")
                with open(temp_gz_path, "wb") as f:
                    f.write(r.content)
                
                # Extract and save as CSV
                csv_path = os.path.join(output_dir, f"usage_report_{idx}.csv")
                with gzip.open(temp_gz_path, "rb") as f_in:
                    with open(csv_path, "wb") as f_out:
                        f_out.write(f_in.read())
                
                # Remove temporary gzip file
                os.remove(temp_gz_path)

                print(f"File {idx} downloaded and extracted")

            print(f"All files downloaded and extracted to the {output_dir} directory")
            return 0
        elif report_status == "processing":
            # Exponential backoff: wait time doubles with each attempt, capped at max_wait_time
            wait_time = min(base_delay * (2 ** (attempt - 1)), max_wait_time)
            print(f"Report still processing. Retrying in {wait_time} seconds...")
            time.sleep(wait_time)
        else:
            print(f"Report status: {report_status}. Error occurred.", file=sys.stderr)
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
