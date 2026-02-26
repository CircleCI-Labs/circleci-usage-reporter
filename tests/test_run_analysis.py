"""
Tests for src/run_analysis.py — notebook generation and analysis helpers.
"""
import argparse
import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# _add_arguments / add_parser
# ---------------------------------------------------------------------------

class TestRunAnalysisParser:

    def test_required_type_flag(self):
        from src.run_analysis import _add_arguments
        parser = argparse.ArgumentParser()
        _add_arguments(parser)
        args = parser.parse_args(["--type", "job", "--input", "data.csv"])
        assert args.type == "job"

    def test_all_type_choices_accepted(self):
        from src.run_analysis import _add_arguments
        parser = argparse.ArgumentParser()
        _add_arguments(parser)
        for choice in ["job", "project", "compute-credits", "resource"]:
            args = parser.parse_args(["--type", choice])
            assert args.type == choice

    def test_input_flag_sets_data_file(self):
        from src.run_analysis import _add_arguments
        parser = argparse.ArgumentParser()
        _add_arguments(parser)
        args = parser.parse_args(["--type", "job", "--input", "/tmp/my.csv"])
        assert args.data_file == "/tmp/my.csv"

    def test_defaults(self):
        from src.run_analysis import _add_arguments
        parser = argparse.ArgumentParser()
        _add_arguments(parser)
        args = parser.parse_args(["--type", "job"])
        assert args.credit_cost == 0.0006
        assert args.job == "deploy"

    def test_standalone_main_help(self):
        from src.run_analysis import main
        with pytest.raises(SystemExit) as exc:
            with patch("sys.argv", ["run-analysis", "--help"]):
                main()
        assert exc.value.code == 0


# ---------------------------------------------------------------------------
# setup_environment
# ---------------------------------------------------------------------------

class TestSetupEnvironment:

    def test_creates_output_dir(self, tmp_path):
        from src.run_analysis import setup_environment
        with patch("src.run_analysis.Path", wraps=Path):
            output_dir = setup_environment()
        assert output_dir.exists()

    def test_sets_mplbackend(self):
        from src.run_analysis import setup_environment
        setup_environment()
        assert os.environ.get("MPLBACKEND") == "Agg"


# ---------------------------------------------------------------------------
# Cell generator functions
# ---------------------------------------------------------------------------

class TestCellGenerators:

    def _get_source(self, cells):
        """Flatten all code cell sources into one string."""
        return "\n".join(
            "".join(cell["source"])
            for cell in cells
            if cell["cell_type"] == "code"
        )

    def test_create_job_analysis_cells_contains_data_file(self):
        from src.run_analysis import create_job_analysis_cells
        cells = create_job_analysis_cells("my-project", "build", 0.001, "/tmp/custom.csv")
        assert "/tmp/custom.csv" in self._get_source(cells)

    def test_create_job_analysis_cells_contains_project(self):
        from src.run_analysis import create_job_analysis_cells
        cells = create_job_analysis_cells("my-project", "build", 0.001, "/tmp/data.csv")
        assert "my-project" in self._get_source(cells)

    def test_create_project_analysis_cells_contains_data_file(self):
        from src.run_analysis import create_project_analysis_cells
        cells = create_project_analysis_cells("my-project", 0.001, "/tmp/custom.csv")
        assert "/tmp/custom.csv" in self._get_source(cells)

    def test_create_compute_credits_cells_contains_data_file(self):
        from src.run_analysis import create_compute_credits_cells
        cells = create_compute_credits_cells(0.001, "/tmp/custom.csv")
        assert "/tmp/custom.csv" in self._get_source(cells)

    def test_create_resource_analysis_cells_contains_data_file(self):
        from src.run_analysis import create_resource_analysis_cells
        cells = create_resource_analysis_cells("my-project", 0.001, "/tmp/custom.csv")
        assert "/tmp/custom.csv" in self._get_source(cells)

    def test_cells_are_valid_notebook_structure(self):
        from src.run_analysis import create_job_analysis_cells
        cells = create_job_analysis_cells("proj", "deploy", 0.001, "/tmp/data.csv")
        for cell in cells:
            assert "cell_type" in cell
            assert "source" in cell


# ---------------------------------------------------------------------------
# create_minimal_notebook
# ---------------------------------------------------------------------------

class TestCreateMinimalNotebook:

    @pytest.mark.parametrize("analysis_type", ["job", "project", "compute-credits", "resource"])
    def test_creates_valid_ipynb_file(self, analysis_type, tmp_path):
        from src.run_analysis import create_minimal_notebook
        with patch("src.run_analysis.Path") as mock_path:
            mock_path.return_value.parent = tmp_path
            mock_path.side_effect = lambda x: Path(x)

            notebook_path = create_minimal_notebook(
                analysis_type, "my-project", "deploy", 0.001, str(tmp_path / "data.csv")
            )

        assert notebook_path.endswith(".ipynb")
        with open(notebook_path) as f:
            nb = json.load(f)
        assert nb["nbformat"] == 4
        assert "cells" in nb

        os.unlink(notebook_path)

    def test_raises_on_unknown_type(self):
        from src.run_analysis import create_minimal_notebook
        with pytest.raises(ValueError, match="Unknown analysis type"):
            create_minimal_notebook("unknown-type")


# ---------------------------------------------------------------------------
# handle — argument validation and data_file resolution
# ---------------------------------------------------------------------------

class TestHandleValidation:

    def test_returns_1_when_data_file_missing(self):
        from src.run_analysis import handle
        args = argparse.Namespace(
            data_file="/nonexistent/file.csv",
            type="job",
            project="proj",
            job="build",
            credit_cost=0.001,
            output_dir="/tmp/reports",
        )
        result = handle(args)
        assert result == 1

    def test_resolves_relative_data_file_to_absolute(self, tmp_path):
        """data_file is resolved to absolute before notebook cells are generated."""
        from src.run_analysis import handle

        csv = tmp_path / "data.csv"
        csv.write_text("PROJECT_NAME,TOTAL_CREDITS\nproj,100\n")

        args = argparse.Namespace(
            data_file=str(csv),
            type="job",
            project="proj",
            job="build",
            credit_cost=0.001,
            output_dir="/tmp/reports",
        )

        with patch("src.run_analysis.run_notebook_conversion") as mock_conv:
            mock_conv.side_effect = RuntimeError("skip conversion")
            result = handle(args)

        assert result == 1
        assert Path(args.data_file).is_absolute()
