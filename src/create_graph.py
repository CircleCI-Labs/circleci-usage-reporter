#!/usr/bin/env python3
"""
Create visualization graphs from usage data.
"""

import argparse
import os
import sys

import pandas as pd


def _add_arguments(parser):
    """Add create-graph arguments to a parser."""
    parser.add_argument(
        'csv_file',
        help='Path to the merged CSV file'
    )
    parser.add_argument(
        '--output',
        default='/tmp/reports/total_credits_per_project.png',
        help='Output file path for the graph (default: /tmp/reports/total_credits_per_project.png)'
    )
    return parser


def add_parser(subparsers):
    """Add create-graph command parser."""
    parser = subparsers.add_parser(
        'create-graph',
        help='Create visualization graphs from usage data'
    )
    return _add_arguments(parser)


def handle(args):
    """Execute the create-graph command."""
    # Lazy import matplotlib only when actually creating graphs
    import matplotlib.pyplot as plt
    
    try:
        print(f"Reading CSV file: {args.csv_file}")
        df = pd.read_csv(args.csv_file)

        print("Grouping and processing data...")
        grouped_df = df.groupby(['PROJECT_NAME', 'VCS_URL'])['TOTAL_CREDITS'].sum()
        sorted_df = grouped_df.sort_values(ascending=False)

        # Save sorted data
        sorted_file = args.csv_file.replace('.csv', '_sorted.csv')
        sorted_df.to_csv(sorted_file, header=True)
        print(f"Sorted data saved to {sorted_file}")

        # Filter out zero credits
        print("Filtering out projects with 0 credits...")
        grouped_df = grouped_df[grouped_df != 0]

        # Create visualization
        print("Creating graph...")
        plt.figure(figsize=(15, 10))
        grouped_df.plot(kind='bar')
        plt.ylabel('Total Credits')
        plt.xlabel('Project')
        plt.title('Total Credits per Project')

        # Ensure output directory exists
        output_dir = os.path.dirname(args.output)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)

        plt.savefig(args.output, bbox_inches='tight')
        print(f"Graph saved to {args.output}")

        return 0

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def main():
    """Standalone entry point."""
    parser = argparse.ArgumentParser(description='Create visualization graphs from usage data')
    _add_arguments(parser)
    args = parser.parse_args()
    sys.exit(handle(args))


if __name__ == '__main__':
    main()
