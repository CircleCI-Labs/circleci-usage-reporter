#!/usr/bin/env python3
"""
CircleCI Usage Reporter CLI
A unified command-line interface for CircleCI usage data extraction and processing.
"""

import argparse
import sys


def create_parser():
    """Create and configure the argument parser."""
    parser = argparse.ArgumentParser(
        prog='circleci-usage-reporter',
        description='Tools for extracting, processing, and visualizing CircleCI usage data',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Get usage report
  circleci-usage-reporter get --org-id <id> --start-date 2024-01-01 --end-date 2024-01-31

  # Merge CSV files
  circleci-usage-reporter merge --input-dir /tmp/reports --output merged.csv

  # Send data to Datadog
  circleci-usage-reporter send-to-datadog usage_report.csv --api-key <key>

  # Send data to DoiT
  circleci-usage-reporter send-to-doit usage_report.csv --api-key <key>

  # Run analysis and generate report
  circleci-usage-reporter run-analysis --type job --project my-project --input merged.csv

  # Create visualization graph
  circleci-usage-reporter create-graph /tmp/reports/merged.csv

  # Store weekly metrics in Postgres + Prometheus
  circleci-usage-reporter store-metrics merged.csv --previous-week --database-url $DATABASE_URL
        """
    )

    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    subparsers.required = True

    # Import and register parsers from their respective modules
    from src.get import add_parser as add_get_parser
    from src.merge import add_parser as add_merge_parser
    from src.send_to_datadog import add_parser as add_datadog_parser
    from src.send_to_doit import add_parser as add_doit_parser
    from src.create_graph import add_parser as add_create_graph_parser
    from src.run_analysis import add_parser as add_run_analysis_parser
    from src.store_metrics import add_parser as add_store_metrics_parser

    # Register all command parsers
    add_get_parser(subparsers)
    add_merge_parser(subparsers)
    add_datadog_parser(subparsers)
    add_doit_parser(subparsers)
    add_create_graph_parser(subparsers)
    add_run_analysis_parser(subparsers)
    add_store_metrics_parser(subparsers)

    return parser


def main():
    """Main entry point for the CLI."""
    parser = create_parser()
    args = parser.parse_args()

    # Import and dispatch to appropriate command handler
    from src.get import handle as handle_get
    from src.merge import handle as handle_merge
    from src.send_to_datadog import handle as handle_datadog
    from src.send_to_doit import handle as handle_doit
    from src.create_graph import handle as handle_create_graph
    from src.run_analysis import handle as handle_run_analysis
    from src.store_metrics import handle as handle_store_metrics

    command_handlers = {
        'get': handle_get,
        'send-to-datadog': handle_datadog,
        'send-to-doit': handle_doit,
        'create-graph': handle_create_graph,
        'merge': handle_merge,
        'run-analysis': handle_run_analysis,
        'store-metrics': handle_store_metrics,
    }

    handler = command_handlers.get(args.command)
    if handler:
        sys.exit(handler(args))
    else:
        print(f"Error: Unknown command '{args.command}'", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
