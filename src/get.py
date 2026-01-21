#!/usr/bin/env python3
"""
Get CircleCI usage report from the API.
"""

import argparse
import gzip
import json
import os
import shutil
import sys
import time
from datetime import datetime

import requests

from src.merge import handle as merge_handle

BASE_API_URL = "https://circleci.com/api/v2"
BASE_DELAY = 10  # Start with 10 seconds for exponential backoff
MAX_WAIT_TIME = 60  # Cap at 1 minute (60 seconds)
TEMP_DIR_BASE = "/tmp/circleci-usage-reporter"


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


def _validate_args(org_id, api_token, start_date, end_date):
    """Validate required arguments."""
    if not api_token:
        print("Error: CircleCI API token required. Use --api-token or set CIRCLECI_API_TOKEN or CIRCLECI_TOKEN env var", file=sys.stderr)
        return False

    if not org_id:
        print("Error: Organization ID required. Use --org-id or set ORG_ID env var", file=sys.stderr)
        return False

    if not start_date:
        print("Error: Start date required. Use --start-date", file=sys.stderr)
        return False

    if not end_date:
        print("Error: End date required. Use --end-date", file=sys.stderr)
        return False

    return True


def _request_report(org_id, api_token, start_date, end_date):
    """Request a usage report from the API."""
    post_data = {
        "start": f"{start_date}T00:00:01Z",
        "end": f"{end_date}T00:00:01Z",
        "shared_org_ids": []
    }

    print(f"Requesting usage report for org {org_id} from {start_date} to {end_date}...")

    response = requests.post(
        f"{BASE_API_URL}/organizations/{org_id}/usage_export_job",
        headers={"Circle-Token": api_token, "Content-Type": "application/json"},
        data=json.dumps(post_data)
    )

    if response.status_code != 201:
        print(f"Error: Failed to request report. Status: {response.status_code}", file=sys.stderr)
        print(f"Response: {response.text}", file=sys.stderr)
        return None

    data = response.json()
    report_id = data.get("usage_export_job_id")
    print(f"Report requested successfully. Report ID: {report_id}")
    return report_id


def _determine_output_path(output):
    """Determine the final output path and directory."""
    if output.endswith('/') or os.path.isdir(output):
        output_dir = output.rstrip('/')
        final_output = os.path.join(output_dir, 'usage_report.csv')
    else:
        output_dir = os.path.dirname(output) if os.path.dirname(output) else '.'
        final_output = output
    
    os.makedirs(output_dir, exist_ok=True)
    return output_dir, final_output


def _create_temp_directory():
    """Create a temporary directory for intermediate CSV files."""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    temp_dir = os.path.join(TEMP_DIR_BASE, timestamp)
    os.makedirs(temp_dir, exist_ok=True)
    return temp_dir


def _download_csv_files(download_urls, temp_dir):
    """Download and extract CSV files from URLs."""
    for idx, url in enumerate(download_urls):
        r = requests.get(url)
        # Save compressed file temporarily
        temp_gz_path = os.path.join(temp_dir, f"usage_report_{idx}.csv.gz")
        with open(temp_gz_path, "wb") as f:
            f.write(r.content)
        
        # Extract and save as CSV
        csv_path = os.path.join(temp_dir, f"usage_report_{idx}.csv")
        with gzip.open(temp_gz_path, "rb") as f_in:
            with open(csv_path, "wb") as f_out:
                f_out.write(f_in.read())
        
        # Remove temporary gzip file
        os.remove(temp_gz_path)

        print(f"File {idx} downloaded and extracted")


def _merge_csv_files(temp_dir, final_output):
    """Merge CSV files using the existing merge functionality."""
    merge_args = argparse.Namespace(
        input_dir=temp_dir,
        output=final_output
    )
    
    return merge_handle(merge_args)


def _get_report_status(org_id, api_token, report_id):
    """Get the current status of a usage report."""
    response = requests.get(
        f"{BASE_API_URL}/organizations/{org_id}/usage_export_job/{report_id}",
        headers={"Circle-Token": api_token}
    )
    return response.json()


def _calculate_wait_time(attempt, base_delay=BASE_DELAY, max_wait_time=MAX_WAIT_TIME):
    """Calculate wait time using exponential backoff."""
    return min(base_delay * (2 ** (attempt - 1)), max_wait_time)


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

    # Validate arguments
    if not _validate_args(org_id, api_token, start_date, end_date):
        return 1

    # Request the report
    report_id = _request_report(org_id, api_token, start_date, end_date)
    if not report_id:
        return 1

    # Determine output paths
    output_dir, final_output = _determine_output_path(output)
    
    # Create temporary directory for intermediate CSV files
    temp_dir = _create_temp_directory()
    
    try:
        # Poll for report completion with exponential backoff
        attempt = 0
        
        while True:
            attempt += 1
            print(f"Checking if report can be downloaded (attempt {attempt})...")
            
            report = _get_report_status(org_id, api_token, report_id)
            report_status = report.get("state")

            if report_status == "completed":
                print("Report generated. Now Downloading...")
                download_urls = report.get("download_urls", [])

                # Download all CSV files to temporary directory
                _download_csv_files(download_urls, temp_dir)

                # Merge all CSV files into one
                merge_result = _merge_csv_files(temp_dir, final_output)
                if merge_result != 0:
                    return merge_result
                
                return 0
            elif report_status == "processing":
                wait_time = _calculate_wait_time(attempt)
                print(f"Report still processing. Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                print(f"Report status: {report_status}. Error occurred.", file=sys.stderr)
                return 1
    finally:
        # Clean up temporary directory
        if os.path.exists(temp_dir):
            print(f"Cleaning up temporary directory: {temp_dir}")
            shutil.rmtree(temp_dir)


def main():
    """Standalone entry point."""
    import argparse
    parser = argparse.ArgumentParser(description='Get CircleCI usage report from the API.')
    _add_arguments(parser)
    args = parser.parse_args()
    sys.exit(handle(args))


if __name__ == '__main__':
    main()
