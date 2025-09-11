#!/usr/bin/env python3
"""
Lightweight script to process a CSV file and send metrics to DoiT DataHub API.
Usage: python send_to_doit.py <path_to_csv> [--api-key <key>] [--batch-size <size>]
"""

import os
import csv
import argparse
from datetime import datetime
from typing import Dict, List, Any
import requests


class DoiTDataHubIngest:
    """Process CSV data and send to DoiT DataHub."""
    
    def __init__(self, api_key=None):
        """Set up DoiT client with API credentials."""
        self.api_key = api_key or os.environ.get("DOIT_API_KEY")
        
        if not self.api_key:
            raise ValueError("DoiT API key required. Use --api-key or set DOIT_API_KEY env variable.")
            
        self.base_url = "https://api.doit.com/datahub/v1"
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }

    def process_csv(self, csv_path: str) -> List[Dict[str, Any]]:
        """Parse CSV file and convert to typed dictionaries."""
        if not os.path.exists(csv_path):
            raise FileNotFoundError(f"CSV file not found: {csv_path}")
            
        data = []
        with open(csv_path, 'r', encoding='utf-8') as file:
            for row in csv.DictReader(file):
                # Process row with appropriate types
                cleaned_row = {}
                for key, value in row.items():
                    # Skip null-like values
                    if not value or value in ("\\N", r'\N', "\\\\N", "null"):
                        cleaned_row[key] = None
                        continue
                    
                    # UUID and string fields - keep as strings
                    if (
                        key in [
                            'ORGANIZATION_ID', 'PROJECT_ID', 'PIPELINE_ID', 'WORKFLOW_ID', 
                            'JOB_ID', 'PIPELINE_TRIGGER_USER_ID'
                        ]
                        or key in [
                            'ORGANIZATION_NAME', 'PROJECT_NAME', 'VCS_NAME', 'VCS_URL',
                            'VCS_BRANCH', 'PIPELINE_TRIGGER_SOURCE', 'WORKFLOW_NAME',
                            'JOB_NAME', 'JOB_BUILD_STATUS', 'RESOURCE_CLASS',
                            'OPERATING_SYSTEM', 'EXECUTOR'
                        ]
                    ):
                        cleaned_row[key] = value
                    
                    # Integer fields
                    elif key in ['PARALLELISM', 'JOB_RUN_NUMBER', 'PIPELINE_NUMBER']:
                        try:
                            cleaned_row[key] = int(value)
                        except (ValueError, TypeError):
                            cleaned_row[key] = None
                    
                    # Float numeric fields
                    elif key.endswith('_PCT') or key.endswith('_CREDITS') or key == 'JOB_RUN_SECONDS':
                        try:
                            cleaned_row[key] = float(value)
                        except (ValueError, TypeError):
                            cleaned_row[key] = None
                    
                    # Boolean fields
                    elif key in ['IS_UNREGISTERED_USER', 'IS_WORKFLOW_SUCCESSFUL']:
                        cleaned_row[key] = value.lower() == 'true'
                    
                    # DateTime fields
                    elif 'DATE' in key or 'AT' in key:
                        try:
                            if ' ' in value:  # Has time component
                                dt_format = '%Y-%m-%d %H:%M:%S.%f' if '.' in value else '%Y-%m-%d %H:%M:%S'
                                dt = datetime.strptime(value, dt_format)
                            else:  # Date only
                                dt = datetime.strptime(value, '%Y-%m-%d')
                            cleaned_row[key] = dt
                        except (ValueError, TypeError):
                            cleaned_row[key] = None
                    
                    # Any other fields - keep as is
                    else:
                        cleaned_row[key] = value
                
                data.append(cleaned_row)
        
        return data

    def convert_to_doit_events(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Convert CSV data to DoiT DataHub events format."""
        events = []
        
        for row in data:
            # Get timestamp (default to now for invalid values)
            timestamp = row.get('JOB_RUN_STOPPED_AT')
            if timestamp is None or not isinstance(timestamp, datetime):
                timestamp = datetime.now()
            
            # Convert to RFC3339 format (properly formatted)
            time_str = timestamp.strftime('%Y-%m-%dT%H:%M:%S.%fZ')
            
            # Create dimensions
            dimensions = []
            
            # Fixed dimensions (using allowed keys from API docs)
            if row.get('PROJECT_NAME'):
                dimensions.append({
                    "key": "project_name",
                    "value": row.get('PROJECT_NAME'),
                    "type": "fixed"
                })
            
            if row.get('ORGANIZATION_NAME'):
                dimensions.append({
                    "key": "project_id",  # Using project_id for organization
                    "value": row.get('ORGANIZATION_NAME'),
                    "type": "fixed"
                })
            
            if row.get('RESOURCE_CLASS'):
                dimensions.append({
                    "key": "service_description",
                    "value": f"CircleCI-{row.get('RESOURCE_CLASS')}",
                    "type": "fixed"
                })
            
            # Use VCS_BRANCH as region if available, otherwise use a default
            region_value = row.get('VCS_BRANCH') or 'default'
            dimensions.append({
                "key": "region",
                "value": region_value,
                "type": "fixed"
            })
            
            # Add zone dimension (same as region for CircleCI)
            dimensions.append({
                "key": "zone",
                "value": region_value,
                "type": "fixed"
            })
            
            # Label dimensions (custom tags)
            if row.get('WORKFLOW_NAME'):
                dimensions.append({
                    "key": "workflow",
                    "value": row.get('WORKFLOW_NAME'),
                    "type": "label"
                })
            
            if row.get('JOB_NAME'):
                dimensions.append({
                    "key": "job",
                    "value": row.get('JOB_NAME'),
                    "type": "label"
                })
            
            if row.get('JOB_BUILD_STATUS'):
                dimensions.append({
                    "key": "status",
                    "value": row.get('JOB_BUILD_STATUS'),
                    "type": "label"
                })
            
            if row.get('OPERATING_SYSTEM'):
                dimensions.append({
                    "key": "os",
                    "value": row.get('OPERATING_SYSTEM'),
                    "type": "label"
                })
            
            # Add environment label
            dimensions.append({
                "key": "env",
                "value": "ci",
                "type": "label"
            })
            
            # Project label dimensions
            if row.get('ORGANIZATION_NAME'):
                dimensions.append({
                    "key": "department",
                    "value": row.get('ORGANIZATION_NAME'),
                    "type": "project_label"
                })
            
            # Create metrics
            metrics = []
            
            # Job runtime (usage metric)
            if row.get('JOB_RUN_SECONDS'):
                metrics.append({
                    "value": float(row.get('JOB_RUN_SECONDS')),
                    "type": "usage"
                })
            
            # Credit metrics (as cost) - only send non-zero values
            for credit_field in ["COMPUTE_CREDITS", "DLC_CREDITS", "USER_CREDITS", "TOTAL_CREDITS"]:
                value = row.get(credit_field)
                if value is not None and value > 0:
                    metrics.append({
                        "value": float(value),
                        "type": "cost"
                    })
            
            # CPU/RAM utilization as custom metrics
            if row.get('MEDIAN_CPU_UTILIZATION_PCT'):
                metrics.append({
                    "value": float(row.get('MEDIAN_CPU_UTILIZATION_PCT')),
                    "type": "custom"
                })
            
            if row.get('MEDIAN_RAM_UTILIZATION_PCT'):
                metrics.append({
                    "value": float(row.get('MEDIAN_RAM_UTILIZATION_PCT')),
                    "type": "custom"
                })
            
            # Create event with proper structure
            event = {
                "provider": "CircleCI",
                "id": f"{row.get('JOB_ID', 'unknown')}-{row.get('JOB_RUN_NUMBER', 'unknown')}",
                "dimensions": dimensions,
                "time": time_str,
                "metrics": metrics
            }
            
            events.append(event)
        
        return events

    def send_events(self, events: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Send events to DoiT DataHub API."""
        if not events:
            return {"status": "warning", "message": "No valid events found"}
        
        # DoiT API limit is 255 events per request
        batch_size = 255
        total_sent = 0
        
        for i in range(0, len(events), batch_size):
            batch = events[i:i + batch_size]
            
            payload = {
                "events": batch
            }
            
            try:
                response = requests.post(
                    f"{self.base_url}/events",
                    headers=self.headers,
                    json=payload,
                    timeout=30
                )
                
                if response.status_code == 201:
                    total_sent += len(batch)
                    print(f"Sent batch of {len(batch)} events successfully")
                else:
                    print(f"Error sending batch: {response.status_code} - {response.text}")
                    return {"status": "error", "message": f"API error: {response.status_code}"}
                    
            except requests.exceptions.RequestException as e:
                print(f"Request error: {str(e)}")
                return {"status": "error", "message": f"Request failed: {str(e)}"}
        
        return {"status": "success", "message": f"Sent {total_sent} events"}

    def send_csv_file(self, csv_path: str) -> Dict[str, Any]:
        """Send CSV file directly to DoiT DataHub API."""
        if not os.path.exists(csv_path):
            return {"status": "error", "message": f"CSV file not found: {csv_path}"}
        
        # Check file size (30MB limit)
        file_size = os.path.getsize(csv_path)
        file_size_mb = file_size / (1024 * 1024)
        
        if file_size_mb > 30:
            return {"status": "error", "message": f"File size {file_size_mb:.1f}MB exceeds 30MB limit. Please compress the file."}
        
        try:
            with open(csv_path, 'rb') as file:
                files = {'file': file}
                data = {'provider': 'CircleCI'}
                
                response = requests.post(
                    f"{self.base_url}/csv/upload",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    files=files,
                    data=data,
                    timeout=60
                )
                
                if response.status_code == 201:
                    result = response.json()
                    return {"status": "success", "message": f"Uploaded {result.get('ingestedRows', 0)} rows"}
                else:
                    return {"status": "error", "message": f"Upload failed: {response.status_code} - {response.text}"}
                    
        except Exception as e:
            return {"status": "error", "message": f"Upload error: {str(e)}"}


def main():
    """Run the script."""
    parser = argparse.ArgumentParser(description='Process a CSV file and send to DoiT DataHub.')
    parser.add_argument('csv_file', help='Path to the CSV file')
    parser.add_argument('--api-key', help='DoiT API key')
    parser.add_argument('--csv-upload', action='store_true', help='Upload CSV file directly instead of processing')
    parser.add_argument('--dry-run', action='store_true', help='Process without sending')
    parser.add_argument('--batch-size', type=int, default=255, help='Batch size (default: 255)')
    
    args = parser.parse_args()
    
    try:
        # Initialize ingestor
        ingestor = DoiTDataHubIngest(args.api_key)
        print("Sending to DoiT DataHub API")
        
        if args.csv_upload:
            # Direct CSV upload
            print(f"Uploading CSV file: {args.csv_file}")
            if args.dry_run:
                print("Dry run - not uploading to DoiT")
                return 0
            
            result = ingestor.send_csv_file(args.csv_file)
            print(f"Upload result: {result['status']} - {result['message']}")
            
        else:
            # Process CSV and send as events
            print(f"Processing CSV: {args.csv_file}")
            data = ingestor.process_csv(args.csv_file)
            total_rows = len(data)
            print(f"Processed {total_rows} rows")
            
            if args.dry_run:
                print("Dry run - not sending to DoiT")
                return 0
            
            # Convert to DoiT events
            print("Converting to DoiT events...")
            events = ingestor.convert_to_doit_events(data)
            print(f"Created {len(events)} events")
            
            # Send events
            print("Sending events to DoiT...")
            result = ingestor.send_events(events)
            print(f"Send result: {result['status']} - {result['message']}")
        
        if result['status'] == 'success':
            print("Processing complete")
            return 0
        else:
            print(f"Processing failed: {result['message']}")
            return 1
        
    except Exception as e:
        print(f"Error: {str(e)}")
        return 1


if __name__ == "__main__":
    exit(main())
