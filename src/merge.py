#!/usr/bin/env python3
"""
Merge multiple CSV files into one.
"""

import argparse
import glob
import os
import sys


def _add_arguments(parser):
    """Add merge arguments to a parser."""
    parser.add_argument(
        '--input-dir',
        default='/tmp/reports',
        help='Directory containing CSV files to merge (default: /tmp/reports)'
    )
    parser.add_argument(
        '--output',
        default='/tmp/reports/merged.csv',
        help='Output file path for merged CSV (default: /tmp/reports/merged.csv)'
    )
    return parser


def add_parser(subparsers):
    """Add merge command parser."""
    parser = subparsers.add_parser(
        'merge',
        help='Merge multiple CSV files into one'
    )
    return _add_arguments(parser)


def handle(args):
    """Execute the merge command."""
    try:
        csv_files = glob.glob(os.path.join(args.input_dir, '*.csv'))

        quiet = getattr(args, 'quiet', False)

        if not csv_files:
            print(f"Error: No CSV files found in {args.input_dir}", file=sys.stderr)
            return 1

        if not quiet:
            print(f"Found {len(csv_files)} CSV files to merge...")

        # Ensure output directory exists
        output_dir = os.path.dirname(args.output)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)

        with open(args.output, 'w') as merged_file:
            for i, csv_file in enumerate(csv_files):
                if not quiet:
                    print(f"Processing {csv_file}...")
                with open(csv_file, 'r') as f:
                    # Skip header if not the first file
                    if i > 0:
                        next(f)
                    for line in f:
                        merged_file.write(line)

        if not quiet:
            print(f"Merged {len(csv_files)} files into {args.output}")
        return 0

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def main():
    """Standalone entry point."""
    parser = argparse.ArgumentParser(description='Merge multiple CSV files into one')
    _add_arguments(parser)
    args = parser.parse_args()
    sys.exit(handle(args))


if __name__ == '__main__':
    main()
