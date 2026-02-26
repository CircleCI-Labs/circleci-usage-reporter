"""
Tests for src/create_graph.py
"""
import argparse
import os
from pathlib import Path
from unittest.mock import patch

import matplotlib
matplotlib.use("Agg")  # Must be set before any other matplotlib import

import pytest


@pytest.fixture
def sample_csv(tmp_path):
    p = tmp_path / "usage.csv"
    p.write_text(
        "PROJECT_NAME,VCS_URL,TOTAL_CREDITS\n"
        "proj-a,https://github.com/org/a,100\n"
        "proj-b,https://github.com/org/b,200\n"
        "proj-a,https://github.com/org/a,50\n"
    )
    return str(p)


class TestCreateGraphParser:

    def test_csv_file_positional_argument(self):
        from src.create_graph import _add_arguments
        parser = argparse.ArgumentParser()
        _add_arguments(parser)
        args = parser.parse_args(["data.csv"])
        assert args.csv_file == "data.csv"

    def test_output_flag(self):
        from src.create_graph import _add_arguments
        parser = argparse.ArgumentParser()
        _add_arguments(parser)
        args = parser.parse_args(["data.csv", "--output", "/tmp/my_graph.png"])
        assert args.output == "/tmp/my_graph.png"

    def test_standalone_main_help(self):
        from src.create_graph import main
        with pytest.raises(SystemExit) as exc:
            with patch("sys.argv", ["create-graph", "--help"]):
                main()
        assert exc.value.code == 0


class TestCreateGraphHandle:

    def test_handle_creates_graph(self, sample_csv, tmp_path):
        from src.create_graph import handle
        output = str(tmp_path / "graph.png")
        args = argparse.Namespace(csv_file=sample_csv, output=output)
        result = handle(args)
        assert result == 0
        assert os.path.exists(output)

    def test_handle_returns_1_on_missing_csv(self, tmp_path):
        from src.create_graph import handle
        output = str(tmp_path / "graph.png")
        args = argparse.Namespace(csv_file="/nonexistent/data.csv", output=output)
        result = handle(args)
        assert result == 1

    def test_handle_creates_sorted_csv(self, sample_csv, tmp_path):
        from src.create_graph import handle
        output = str(tmp_path / "graph.png")
        args = argparse.Namespace(csv_file=sample_csv, output=output)
        handle(args)
        sorted_file = sample_csv.replace(".csv", "_sorted.csv")
        assert os.path.exists(sorted_file)

    def test_handle_creates_output_dir_if_missing(self, sample_csv, tmp_path):
        from src.create_graph import handle
        output = str(tmp_path / "subdir" / "graph.png")
        args = argparse.Namespace(csv_file=sample_csv, output=output)
        result = handle(args)
        assert result == 0
        assert os.path.exists(output)
