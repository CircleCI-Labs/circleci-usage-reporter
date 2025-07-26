#!/usr/bin/env python3
"""
Lightweight script to process a CSV file and send metrics to Datadog API.
Usage: python send_to_datadog.py <path_to_csv> [--api-key <key>] [--batch-size <size>] [--site <site>]
"""

import os, csv, argparse, time, math
from datetime import datetime
from typing import Dict, List, Any, Optional

from datadog_api_client import ApiClient, Configuration
from datadog_api_client.v2.api.metrics_api import MetricsApi
from datadog_api_client.v1.api.events_api import EventsApi
from datadog_api_client.v2.model.metric_intake_type import MetricIntakeType
from datadog_api_client.v2.model.metric_payload import MetricPayload
from datadog_api_client.v2.model.metric_point import MetricPoint
from datadog_api_client.v2.model.metric_resource import MetricResource
from datadog_api_client.v2.model.metric_series import MetricSeries
from datadog_api_client.v1.model.event_create_request import EventCreateRequest


class DatadogCSVIngest:
    """Process CSV data and send to Datadog."""
    
    def __init__(self, api_key=None, application_key=None, site="datadoghq.eu"):
        """Set up Datadog client with API credentials."""
        self.api_key = api_key or os.environ.get("DATADOG_API_KEY")
        self.application_key = application_key or os.environ.get("DATADOG_APP_KEY")
        
        if not self.api_key:
            raise ValueError("Datadog API key required. Use --api-key or set DATADOG_API_KEY env variable.")
            
        # Configure Datadog client
        self.configuration = Configuration()
        self.configuration.server_variables["site"] = site
        self.configuration.api_key["apiKeyAuth"] = self.api_key
        if self.application_key:
            self.configuration.api_key["appKeyAuth"] = self.application_key

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
                    if (key in ['ORGANIZATION_ID', 'PROJECT_ID', 'PIPELINE_ID', 'WORKFLOW_ID', 'JOB_ID', 'PIPELINE_TRIGGER_USER_ID'] or
                        key in ['ORGANIZATION_NAME', 'PROJECT_NAME', 'VCS_NAME', 'VCS_URL', 'VCS_BRANCH', 
                              'PIPELINE_TRIGGER_SOURCE', 'WORKFLOW_NAME', 'JOB_NAME', 'JOB_BUILD_STATUS',
                              'RESOURCE_CLASS', 'OPERATING_SYSTEM', 'EXECUTOR']):
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
                            cleaned_row[key] = int(dt.timestamp())
                        except (ValueError, TypeError):
                            cleaned_row[key] = None
                    
                    # Any other fields - keep as is
                    else:
                        cleaned_row[key] = value
                
                data.append(cleaned_row)
        
        return data

    def send_series(self, data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Convert data to Datadog metrics and send."""
        now = int(time.time())
        series_list = []
        
        for row in data:
            # Get timestamp (default to now for invalid values)
            timestamp = row.get('JOB_RUN_STOPPED_AT')
            if timestamp is None or not isinstance(timestamp, int) or timestamp > now + 86400 or timestamp < 946684800:
                timestamp = now
            
            # Create resources
            org_name = row.get('ORGANIZATION_NAME') or 'unknown'
            project_name = row.get('PROJECT_NAME') or 'unknown'
            resources = [
                MetricResource(name=org_name, type="organization"),
                MetricResource(name=project_name, type="project")
            ]
            
            # Helper for tag values
            def safe_tag(key, default="unknown"):
                return str(row.get(key) or default)
            
            # Create tags
            tags = [
                f"organization:{safe_tag('ORGANIZATION_NAME')}",
                f"project:{safe_tag('PROJECT_NAME')}",
                f"workflow:{safe_tag('WORKFLOW_NAME')}",
                f"job:{safe_tag('JOB_NAME')}",
                f"resource_class:{safe_tag('RESOURCE_CLASS')}",
                f"build_status:{safe_tag('JOB_BUILD_STATUS')}"
            ]
            
            # Define metrics to send
            metrics_to_send = []
            
            # Job performance metrics
            for metric_name, field_name in [
                ("ci.job.runtime_seconds", "JOB_RUN_SECONDS"),
                ("ci.job.parallelism", "PARALLELISM"),
                ("ci.job.cpu.median_utilization", "MEDIAN_CPU_UTILIZATION_PCT"),
                ("ci.job.cpu.max_utilization", "MAX_CPU_UTILIZATION_PCT"),
                ("ci.job.ram.median_utilization", "MEDIAN_RAM_UTILIZATION_PCT"),
                ("ci.job.ram.max_utilization", "MAX_RAM_UTILIZATION_PCT")
            ]:
                value = row.get(field_name)
                if value is not None:
                    metrics_to_send.append({"name": metric_name, "value": value})
            
            # Credit metrics (only non-zero)
            for field_name in ["COMPUTE_CREDITS", "DLC_CREDITS", "USER_CREDITS", "TOTAL_CREDITS"]:
                value = row.get(field_name)
                if value is not None and value > 0:
                    metric_name = f"ci.credits.{field_name.lower().replace('_credits', '')}"
                    metrics_to_send.append({"name": metric_name, "value": value})
            
            # Create series for each metric
            for metric_info in metrics_to_send:
                try:
                    metric_value = float(metric_info["value"])
                    if not math.isfinite(metric_value):
                        continue
                    
                    series = MetricSeries(
                        metric=metric_info["name"],
                        type=MetricIntakeType.GAUGE,
                        points=[MetricPoint(timestamp=timestamp, value=metric_value)],
                        resources=resources,
                        tags=tags
                    )
                    series_list.append(series)
                except (ValueError, TypeError):
                    continue
        
        # Skip if no valid series
        if not series_list:
            return {"status": "warning", "message": "No valid metrics found"}
            
        # Send to Datadog
        with ApiClient(self.configuration) as api_client:
            api_instance = MetricsApi(api_client)
            response = api_instance.submit_metrics(body=MetricPayload(series=series_list))
            return {"status": "success", "response": response}
    
    def send_events(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Send events to Datadog for completed jobs."""
        results = []
        
        with ApiClient(self.configuration) as api_client:
            api_instance = EventsApi(api_client)
            
            for row in data:
                if row.get('JOB_RUN_STOPPED_AT') is None:
                    continue
                
                # Job details
                job_status = row.get('JOB_BUILD_STATUS', '').lower()
                job_name = row.get('JOB_NAME', 'Unknown Job')
                
                # Set alert type
                alert_type = "info"
                if job_status == 'success': alert_type = "success"
                elif job_status == 'failed': alert_type = "error"
                elif job_status in ['canceled', 'cancelled']: alert_type = "warning"
                
                # Calculate duration
                duration = ""
                if row.get('JOB_RUN_SECONDS'):
                    m, s = divmod(int(row.get('JOB_RUN_SECONDS')), 60)
                    duration = f"Duration: {m}m {s}s"
                
                # Create event text
                text = f"""### CI Job: {job_name} - {job_status.upper()}
**Project**: {row.get('PROJECT_NAME', 'N/A')}
**Workflow**: {row.get('WORKFLOW_NAME', 'N/A')}
{duration}

**Resources**: {row.get('RESOURCE_CLASS', 'N/A')} ({row.get('OPERATING_SYSTEM', 'N/A')}, {row.get('EXECUTOR', 'N/A')})
**Performance**: CPU {row.get('MEDIAN_CPU_UTILIZATION_PCT', 'N/A')}% / RAM {row.get('MEDIAN_RAM_UTILIZATION_PCT', 'N/A')}%
**Credits**: {row.get('TOTAL_CREDITS', 0)} (Compute: {row.get('COMPUTE_CREDITS', 0)})
**Branch**: {row.get('VCS_BRANCH', 'N/A')}
"""
                
                # Create tags
                tags = [
                    f"organization:{row.get('ORGANIZATION_NAME', 'unknown')}",
                    f"project:{row.get('PROJECT_NAME', 'unknown')}",
                    f"workflow:{row.get('WORKFLOW_NAME', 'unknown')}",
                    f"job:{job_name}",
                    f"status:{job_status}",
                    f"branch:{row.get('VCS_BRANCH', 'unknown')}"
                ]
                
                # Get timestamp
                timestamp = row.get('JOB_RUN_STOPPED_AT') or int(time.time())
                
                try:
                    # Create event
                    body = EventCreateRequest(
                        title=f"CI Job: {job_name} - {job_status.upper()}",
                        text=text,
                        tags=tags,
                        alert_type=alert_type,
                        source_type_name="CI",
                        date_happened=timestamp,
                        priority="normal"
                    )
                    
                    response = api_instance.create_event(body=body)
                    results.append({"status": "success", "event_id": response.get('id')})
                except Exception as e:
                    print(f"Failed to create event: {str(e)}")
        
        return results


def main():
    """Run the script."""
    parser = argparse.ArgumentParser(description='Process a CSV file and send to Datadog.')
    parser.add_argument('csv_file', help='Path to the CSV file')
    parser.add_argument('--api-key', help='Datadog API key')
    parser.add_argument('--application-key', help='Datadog Application key')
    parser.add_argument('--events', action='store_true', help='Send events to Datadog')
    parser.add_argument('--dry-run', action='store_true', help='Process without sending')
    parser.add_argument('--batch-size', type=int, default=100, help='Batch size (default: 100)')
    parser.add_argument('--site', default='datadoghq.eu', 
                       choices=['datadoghq.com', 'datadoghq.eu', 'us3.datadoghq.com', 'us5.datadoghq.com'],
                       help='Datadog site (default: datadoghq.eu)')
    
    args = parser.parse_args()
    
    try:
        # Initialize ingestor
        ingestor = DatadogCSVIngest(args.api_key, args.application_key, args.site)
        print(f"Sending to Datadog site: {args.site}")
        
        # Process CSV
        print(f"Processing CSV: {args.csv_file}")
        data = ingestor.process_csv(args.csv_file)
        total_rows = len(data)
        print(f"Processed {total_rows} rows")
        
        if args.dry_run:
            print("Dry run - not sending to Datadog")
            return 0
        
        # Process in batches
        batch_size = args.batch_size
        row_index = 0
        batch_number = 1
        
        while row_index < total_rows:
            end_idx = min(row_index + batch_size, total_rows)
            batch = data[row_index:end_idx]
            
            print(f"Batch {batch_number}: rows {row_index+1}-{end_idx} of {total_rows}")
            
            # Send metrics with retry logic
            retry_count = 0
            success = False
            
            while not success and retry_count < 3:
                try:
                    print("Sending metrics...")
                    ingestor.send_series(batch)
                    success = True
                    print("Metrics sent successfully")
                    
                    # Send events if requested
                    if args.events:
                        print("Sending events...")
                        events = ingestor.send_events(batch)
                        print(f"Sent {len(events)} events")
                        
                except Exception as e:
                    error_str = str(e)
                    print(f"Error: {error_str}")
                    
                    # If payload too large, reduce batch size
                    if 'maximum payload size' in error_str.lower() or 'request entity too large' in error_str.lower():
                        batch_size = max(1, batch_size // 2)
                        retry_count += 1
                        end_idx = min(row_index + batch_size, total_rows)
                        batch = data[row_index:end_idx]
                        print(f"Reducing batch to {batch_size} rows")
                    else:
                        break
            
            # Move to next batch
            if success or batch_size == 1:
                row_index = end_idx
                batch_number += 1
            else:
                # Skip this row if all retries failed
                row_index += 1
                print("Skipping problematic data and continuing")
            
            # Avoid rate limiting
            if row_index < total_rows:
                time.sleep(1)
        
        print("Processing complete")
        
    except Exception as e:
        print(f"Error: {str(e)}")
        return 1
        
    return 0


if __name__ == "__main__":
    exit(main())