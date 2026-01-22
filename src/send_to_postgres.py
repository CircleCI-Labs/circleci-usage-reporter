#!/usr/bin/env python3
"""
PostgreSQL loader for CircleCI Usage API data.

This module provides functionality to load CircleCI usage data from CSV files
into a PostgreSQL database with proper schema and indexing.
"""

import os
import sys
import logging
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
from typing import Optional, Dict, Any, List
from datetime import datetime
import argparse
import gzip
import json
import time
import tempfile
import shutil
import requests
from alembic.config import Config
from alembic import command

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def run_migrations(connection_params: Dict[str, Any]) -> bool:
    """
    Run Alembic migrations to ensure database schema is up to date.
    
    Args:
        connection_params: Database connection parameters
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Build database URL for Alembic
        database_url = (
            f"postgresql://{connection_params['user']}:{connection_params['password']}"
            f"@{connection_params['host']}:{connection_params['port']}"
            f"/{connection_params['database']}"
        )
        
        # Set environment variable for Alembic to use
        os.environ['ALEMBIC_DATABASE_URL'] = database_url
        
        # Get the path to alembic.ini (should be in project root)
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        alembic_cfg = Config(os.path.join(project_root, 'alembic.ini'))
        
        # Run migrations
        logger.info("Running database migrations...")
        command.upgrade(alembic_cfg, "head")
        logger.info("Database migrations completed successfully")
        return True
    except Exception as e:
        logger.error(f"Failed to run migrations: {e}")
        return False
    finally:
        # Clean up environment variable
        if 'ALEMBIC_DATABASE_URL' in os.environ:
            del os.environ['ALEMBIC_DATABASE_URL']


class CircleCIPostgresLoader:
    """PostgreSQL loader for CircleCI usage data."""
    
    def __init__(self, connection_params: Dict[str, Any]):
        """
        Initialize the PostgreSQL loader.
        
        Args:
            connection_params: Database connection parameters including:
                - host: Database host
                - port: Database port (default: 5432)
                - database: Database name
                - user: Username
                - password: Password
        """
        self.connection_params = connection_params
        self.connection = None
        
    def connect(self) -> bool:
        """Establish connection to PostgreSQL database."""
        try:
            self.connection = psycopg2.connect(**self.connection_params)
            logger.info("Successfully connected to PostgreSQL database")
            return True
        except psycopg2.Error as e:
            logger.error(f"Failed to connect to PostgreSQL: {e}")
            return False
    
    def disconnect(self):
        """Close database connection."""
        if self.connection:
            self.connection.close()
            logger.info("Disconnected from PostgreSQL database")
    
    def load_csv_data(self, csv_file_path: str, batch_size: int = 1000) -> bool:
        """
        Load data from CSV file into PostgreSQL database.
        
        Args:
            csv_file_path: Path to the CSV file
            batch_size: Number of records to insert per batch
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            logger.info(f"Loading data from {csv_file_path}")
            
            # Read CSV file in chunks to handle large files
            chunk_iter = pd.read_csv(csv_file_path, chunksize=batch_size, na_values=['\\N'])
            
            total_records = 0
            for chunk_num, chunk in enumerate(chunk_iter):
                logger.info(f"Processing chunk {chunk_num + 1}")
                
                # Clean and prepare data
                cleaned_chunk = self._clean_dataframe(chunk)
                
                # Insert data
                if self._insert_batch(cleaned_chunk):
                    total_records += len(cleaned_chunk)
                    logger.info(f"Inserted {len(cleaned_chunk)} records (total: {total_records})")
                else:
                    logger.error(f"Failed to insert chunk {chunk_num + 1}")
                    return False
            
            logger.info(f"Successfully loaded {total_records} records from {csv_file_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to load CSV data: {e}")
            return False
    
    def _clean_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """Clean and prepare DataFrame for database insertion."""
        # Create a copy to avoid modifying the original
        cleaned_df = df.copy()
        
        # Convert column names to lowercase and replace spaces with underscores
        cleaned_df.columns = [col.lower().replace(' ', '_') for col in cleaned_df.columns]
        
        # Handle datetime columns
        datetime_columns = [
            'organization_created_date', 'project_created_date', 'last_build_finished_at',
            'pipeline_created_at', 'workflow_first_job_queued_at', 'workflow_first_job_started_at',
            'workflow_stopped_at', 'job_run_date', 'job_run_queued_at', 'job_run_started_at',
            'job_run_stopped_at'
        ]
        
        for col in datetime_columns:
            if col in cleaned_df.columns:
                cleaned_df[col] = pd.to_datetime(cleaned_df[col], errors='coerce')
        
        # Convert boolean columns
        boolean_columns = ['is_unregistered_user', 'is_workflow_successful']
        for col in boolean_columns:
            if col in cleaned_df.columns:
                cleaned_df[col] = cleaned_df[col].map({'true': True, 'false': False, 'True': True, 'False': False})
        
        # Convert numeric columns
        numeric_columns = [
            'pipeline_number', 'parallelism', 'job_run_number', 'job_run_seconds',
            'median_cpu_utilization_pct', 'max_cpu_utilization_pct',
            'median_ram_utilization_pct', 'max_ram_utilization_pct',
            'compute_credits', 'dlc_credits', 'user_credits', 'storage_credits',
            'network_credits', 'lease_credits', 'lease_overage_credits',
            'ipranges_credits', 'total_credits'
        ]
        
        for col in numeric_columns:
            if col in cleaned_df.columns:
                cleaned_df[col] = pd.to_numeric(cleaned_df[col], errors='coerce')
                
                # Debug: Check for extremely large values in all numeric columns
                max_val = cleaned_df[col].max()
                min_val = cleaned_df[col].min()
                if pd.notna(max_val) and (max_val > 9223372036854775807 or min_val < -9223372036854775808):
                    logger.warning(f"Column {col} has values outside BIGINT range: min={min_val}, max={max_val}")
                    # Show some examples of problematic values
                    extreme_values = cleaned_df[cleaned_df[col] > 9223372036854775807][col].head(5)
                    if not extreme_values.empty:
                        logger.warning(f"Examples of large values in {col}: {extreme_values.tolist()}")
        
        # Convert parallelism to integer (it should be a small integer)
        if 'parallelism' in cleaned_df.columns:
            cleaned_df['parallelism'] = cleaned_df['parallelism'].astype('Int64')  # Nullable integer type
        
        # Replace NaN and NaT values with None for proper NULL handling in PostgreSQL
        # Do this after all conversions to catch any remaining NaN values
        cleaned_df = cleaned_df.where(pd.notnull(cleaned_df), None)
        
        # Specifically handle NaT values in datetime columns
        for col in datetime_columns:
            if col in cleaned_df.columns:
                cleaned_df[col] = cleaned_df[col].replace({pd.NaT: None})
        
        # Convert any remaining numpy NaN values to None (in case they weren't caught)
        cleaned_df = cleaned_df.replace({pd.NA: None, float('nan'): None})
        
        return cleaned_df
    
    def _insert_batch(self, df: pd.DataFrame) -> bool:
        """Insert a batch of records into the database."""
        if df.empty:
            return True
        
        # Define the column mapping
        column_mapping = {
            'organization_id': 'organization_id',
            'organization_name': 'organization_name',
            'organization_created_date': 'organization_created_date',
            'project_id': 'project_id',
            'project_name': 'project_name',
            'project_created_date': 'project_created_date',
            'last_build_finished_at': 'last_build_finished_at',
            'vcs_name': 'vcs_name',
            'vcs_url': 'vcs_url',
            'vcs_branch': 'vcs_branch',
            'pipeline_id': 'pipeline_id',
            'pipeline_created_at': 'pipeline_created_at',
            'pipeline_number': 'pipeline_number',
            'is_unregistered_user': 'is_unregistered_user',
            'pipeline_trigger_source': 'pipeline_trigger_source',
            'pipeline_trigger_user_id': 'pipeline_trigger_user_id',
            'workflow_id': 'workflow_id',
            'workflow_name': 'workflow_name',
            'workflow_first_job_queued_at': 'workflow_first_job_queued_at',
            'workflow_first_job_started_at': 'workflow_first_job_started_at',
            'workflow_stopped_at': 'workflow_stopped_at',
            'is_workflow_successful': 'is_workflow_successful',
            'job_name': 'job_name',
            'job_run_number': 'job_run_number',
            'job_id': 'job_id',
            'job_run_date': 'job_run_date',
            'job_run_queued_at': 'job_run_queued_at',
            'job_run_started_at': 'job_run_started_at',
            'job_run_stopped_at': 'job_run_stopped_at',
            'job_build_status': 'job_build_status',
            'resource_class': 'resource_class',
            'operating_system': 'operating_system',
            'executor': 'executor',
            'parallelism': 'parallelism',
            'job_run_seconds': 'job_run_seconds',
            'median_cpu_utilization_pct': 'median_cpu_utilization_pct',
            'max_cpu_utilization_pct': 'max_cpu_utilization_pct',
            'median_ram_utilization_pct': 'median_ram_utilization_pct',
            'max_ram_utilization_pct': 'max_ram_utilization_pct',
            'compute_credits': 'compute_credits',
            'dlc_credits': 'dlc_credits',
            'user_credits': 'user_credits',
            'storage_credits': 'storage_credits',
            'network_credits': 'network_credits',
            'lease_credits': 'lease_credits',
            'lease_overage_credits': 'lease_overage_credits',
            'ipranges_credits': 'ipranges_credits',
            'total_credits': 'total_credits'
        }
        
        # Select only the columns that exist in the dataframe
        available_columns = {k: v for k, v in column_mapping.items() if k in df.columns}
        
        if not available_columns:
            logger.warning("No matching columns found in dataframe")
            return True
        
        # Prepare data for insertion
        columns = list(available_columns.values())
        values = []
        
        for _, row in df.iterrows():
            # Convert any NaN/NaT values to None when creating tuples
            value_tuple = tuple(
                None if pd.isna(row.get(col)) else row.get(col, None) 
                for col in available_columns.keys()
            )
            values.append(value_tuple)
        
        # Create the INSERT statement template for execute_values
        insert_sql = f"""
            INSERT INTO circleci_usage ({', '.join(columns)})
            VALUES %s
        """
        
        try:
            with self.connection.cursor() as cursor:
                execute_values(
                    cursor,
                    insert_sql,
                    values,
                    template=None,
                    page_size=1000
                )
                self.connection.commit()
                return True
        except psycopg2.Error as e:
            logger.error(f"Failed to insert batch: {e}")
            
            # Debug: Try to identify problematic values
            logger.info("Attempting to identify problematic values...")
            for i, value_tuple in enumerate(values[:5]):  # Check first 5 rows
                logger.info(f"Row {i} values: {value_tuple}")
            
            self.connection.rollback()
            return False
    
    def get_data_summary(self) -> Optional[Dict[str, Any]]:
        """Get summary statistics about the loaded data."""
        summary_queries = {
            'total_records': "SELECT COUNT(*) FROM circleci_usage",
            'date_range': """
                SELECT 
                    MIN(pipeline_created_at) as earliest_pipeline,
                    MAX(pipeline_created_at) as latest_pipeline,
                    MIN(job_run_started_at) as earliest_job,
                    MAX(job_run_started_at) as latest_job
                FROM circleci_usage
            """,
            'organizations': "SELECT COUNT(DISTINCT organization_id) FROM circleci_usage",
            'projects': "SELECT COUNT(DISTINCT project_id) FROM circleci_usage",
            'total_credits': "SELECT SUM(total_credits) FROM circleci_usage",
            'job_status_breakdown': """
                SELECT job_build_status, COUNT(*) as count
                FROM circleci_usage
                GROUP BY job_build_status
                ORDER BY count DESC
            """,
            'resource_class_breakdown': """
                SELECT resource_class, COUNT(*) as count, SUM(total_credits) as total_credits
                FROM circleci_usage
                GROUP BY resource_class
                ORDER BY total_credits DESC
            """
        }
        
        try:
            summary = {}
            with self.connection.cursor() as cursor:
                for key, query in summary_queries.items():
                    cursor.execute(query)
                    if key in ['total_records', 'organizations', 'projects', 'total_credits']:
                        result = cursor.fetchone()
                        summary[key] = result[0] if result else 0
                    else:
                        result = cursor.fetchall()
                        summary[key] = result
            return summary
        except psycopg2.Error as e:
            logger.error(f"Failed to get data summary: {e}")
            return None


def _fetch_usage_data(org_id: str, api_token: str, start_date: str, end_date: str) -> Optional[str]:
    """
    Fetch usage data from CircleCI API and return path to temporary CSV file.
    
    Args:
        org_id: CircleCI organization ID
        api_token: CircleCI API token
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        
    Returns:
        Path to temporary CSV file, or None if failed
    """
    post_data = {
        "start": f"{start_date}T00:00:01Z",
        "end": f"{end_date}T00:00:01Z",
        "shared_org_ids": []
    }

    logger.info(f"Requesting usage report for org {org_id} from {start_date} to {end_date}...")

    response = requests.post(
        f"https://circleci.com/api/v2/organizations/{org_id}/usage_export_job",
        headers={"Circle-Token": api_token, "Content-Type": "application/json"},
        data=json.dumps(post_data)
    )

    if response.status_code != 201:
        logger.error(f"Failed to request report. Status: {response.status_code}")
        logger.error(f"Response: {response.text}")
        return None

    data = response.json()
    report_id = data.get("usage_export_job_id")
    logger.info(f"Report requested successfully. Report ID: {report_id}")

    # Check if the report is ready for downloading
    for i in range(5):
        logger.info("Checking if report can be downloaded...")
        report = requests.get(
            f"https://circleci.com/api/v2/organizations/{org_id}/usage_export_job/{report_id}",
            headers={"Circle-Token": api_token}
        ).json()

        report_status = report.get("state")

        # Download the report and save it
        if report_status == "completed":
            logger.info("Report generated. Downloading...")
            download_urls = report.get("download_urls", [])

            if not download_urls:
                logger.error("No download URLs found in report")
                return None

            # Create temporary directory for CSV files
            temp_dir = tempfile.mkdtemp(prefix="circleci_usage_")
            csv_files = []

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
                csv_files.append(csv_path)
                logger.info(f"File {idx} downloaded and extracted")

            # If multiple files, merge them into one
            if len(csv_files) > 1:
                logger.info(f"Merging {len(csv_files)} CSV files...")
                merged_path = os.path.join(temp_dir, "merged_usage_report.csv")
                with open(merged_path, 'w') as merged_file:
                    for i, csv_file in enumerate(csv_files):
                        with open(csv_file, 'r') as f:
                            # Skip header if not the first file
                            if i > 0:
                                next(f)
                            for line in f:
                                merged_file.write(line)
                # Clean up individual files
                for csv_file in csv_files:
                    os.remove(csv_file)
                return merged_path
            else:
                return csv_files[0]
                
        elif report_status == "processing":
            logger.info("Report still processing. Retrying in 1 minute...")
            time.sleep(60)  # Wait for 60 seconds before retrying
        else:
            logger.error(f"Report status: {report_status}. Error occurred.")
            return None
    
    logger.error("Report is still in processing state after 5 retries.")
    return None


def _add_arguments(parser, database_required=True, database_default=None, user_required=True, user_default=None):
    """Add arguments to a parser object."""
    # Input source group - mutually exclusive
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        '--input',
        dest='csv_file',
        help='Path to the CSV file to load (cannot be used with --start-date)'
    )
    input_group.add_argument(
        '--start-date',
        help='Start date for fetching data from API (YYYY-MM-DD). Cannot be used with --input. Requires --end-date, --org-id, and --api-token'
    )
    
    # API fetch arguments (only needed when using --start-date)
    parser.add_argument(
        '--end-date',
        help='End date for fetching data from API (YYYY-MM-DD). Requires --start-date'
    )
    parser.add_argument(
        '--org-id',
        help='CircleCI organization ID (or set ORG_ID env var). Required when using --start-date'
    )
    parser.add_argument(
        '--api-token',
        help='CircleCI API token (or set CIRCLECI_API_TOKEN env var). Required when using --start-date'
    )
    
    # PostgreSQL connection arguments
    parser.add_argument(
        '--host',
        default='localhost',
        help='PostgreSQL host (default: localhost)'
    )
    parser.add_argument(
        '--port',
        type=int,
        default=5432,
        help='PostgreSQL port (default: 5432)'
    )
    parser.add_argument(
        '--database',
        required=database_required,
        default=database_default,
        help='PostgreSQL database name' + (f' (default: {database_default})' if database_default else '')
    )
    parser.add_argument(
        '--user',
        required=user_required,
        default=user_default,
        help='PostgreSQL username' + (f' (default: {user_default})' if user_default else '')
    )
    parser.add_argument(
        '--password',
        help='PostgreSQL password (or set PGPASSWORD env var)'
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=1000,
        help='Batch size for loading (default: 1000)'
    )
    parser.add_argument(
        '--skip-migrations',
        action='store_true',
        help='Skip running database migrations before loading data'
    )
    parser.add_argument(
        '--summary',
        action='store_true',
        help='Show data summary after loading'
    )
    return parser


def add_parser(subparsers):
    """Add send-to-postgres command parser."""
    parser = subparsers.add_parser(
        'send-to-postgres',
        help='Send CircleCI usage data to PostgreSQL database',
        description='Load CircleCI usage data from CSV file or fetch directly from API. Use either --input OR --start-date (not both).'
    )
    return _add_arguments(parser, database_required=True, user_required=True)


def handle(args):
    """Execute the send-to-postgres command."""
    # Determine input source
    csv_file = args.csv_file
    temp_file = None
    
    # If using date range, fetch data from API
    if args.start_date:
        if not args.end_date:
            logger.error("--end-date is required when using --start-date")
            return 1
        
        # Get org_id and API token
        org_id = args.org_id or os.getenv('ORG_ID')
        api_token = args.api_token or os.getenv('CIRCLECI_API_TOKEN') or os.getenv('CIRCLECI_TOKEN')
        
        if not org_id:
            logger.error("Organization ID required. Use --org-id or set ORG_ID env var")
            return 1
        
        if not api_token:
            logger.error("CircleCI API token required. Use --api-token or set CIRCLECI_API_TOKEN env var")
            return 1
        
        # Fetch data from API
        csv_file = _fetch_usage_data(org_id, api_token, args.start_date, args.end_date)
        if not csv_file:
            logger.error("Failed to fetch usage data from API")
            return 1
        
        temp_file = csv_file  # Mark for cleanup
    
    # Validate CSV file exists
    if not csv_file or not os.path.exists(csv_file):
        logger.error(f"CSV file not found: {csv_file}")
        return 1
    
    # Get password from argument or environment variable
    password = args.password or os.getenv('PGPASSWORD')
    if not password:
        logger.error("PostgreSQL password required. Use --password or set PGPASSWORD env var")
        return 1
    
    # Set up connection parameters
    connection_params = {
        'host': args.host,
        'port': args.port,
        'database': args.database,
        'user': args.user,
        'password': password
    }
    
    # Initialize loader
    loader = CircleCIPostgresLoader(connection_params)
    
    try:
        # Connect to database
        if not loader.connect():
            return 1
        
        # Run migrations unless skipped
        if not args.skip_migrations:
            if not run_migrations(connection_params):
                logger.error("Failed to run database migrations")
                return 1
        
        # Load data
        if not loader.load_csv_data(csv_file, args.batch_size):
            return 1
        
        # Show summary if requested
        if args.summary:
            summary = loader.get_data_summary()
            if summary:
                print("\n=== Data Summary ===")
                print(f"Total records: {summary.get('total_records', 0):,}")
                print(f"Organizations: {summary.get('organizations', 0)}")
                print(f"Projects: {summary.get('projects', 0)}")
                print(f"Total credits: {summary.get('total_credits', 0):,.2f}")
                
                if 'date_range' in summary and summary['date_range']:
                    date_range = summary['date_range'][0]
                    print(f"Pipeline date range: {date_range[0]} to {date_range[1]}")
                    print(f"Job date range: {date_range[2]} to {date_range[3]}")
                
                print("\nJob Status Breakdown:")
                for status, count in summary.get('job_status_breakdown', []):
                    print(f"  {status}: {count:,}")
                
                print("\nResource Class Breakdown:")
                for resource_class, count, credits in summary.get('resource_class_breakdown', []):
                    print(f"  {resource_class}: {count:,} jobs, {credits:,.2f} credits")
        
        logger.info("Data loading completed successfully")
        return 0
        
    except KeyboardInterrupt:
        logger.info("Operation cancelled by user")
        return 1
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return 1
    finally:
        loader.disconnect()
        # Clean up temporary file if we fetched from API
        if temp_file and os.path.exists(temp_file):
            try:
                temp_dir = os.path.dirname(temp_file)
                shutil.rmtree(temp_dir, ignore_errors=True)
                logger.debug(f"Cleaned up temporary directory: {temp_dir}")
            except Exception as e:
                logger.warning(f"Failed to clean up temporary file: {e}")


def main():
    """Main function for command-line usage."""
    parser = argparse.ArgumentParser(
        description='Load CircleCI usage data into PostgreSQL',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    # Use defaults for standalone usage
    _add_arguments(parser, database_required=False, database_default='circleci_usage', 
                  user_required=False, user_default='postgres')
    args = parser.parse_args()
    sys.exit(handle(args))


if __name__ == '__main__':
    main()
