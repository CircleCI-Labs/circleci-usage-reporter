"""
Tests for CircleCI Usage Reporter.
"""
import argparse
import gzip
import io
import os
import tempfile
from unittest.mock import MagicMock, patch
import pytest


class TestCLI:
    """Test the unified CLI entry point."""

    def test_all_subcommands_registered(self):
        """All expected subcommands are registered in the CLI."""
        from src.cli import create_parser
        parser = create_parser()
        subparsers_action = next(
            a for a in parser._actions if hasattr(a, '_name_parser_map')
        )
        commands = set(subparsers_action._name_parser_map.keys())
        assert commands == {
            'get', 'merge', 'send-to-datadog', 'send-to-doit',
            'create-graph', 'run-analysis', 'store-metrics',
        }

    def test_unknown_command_exits_nonzero(self):
        """An unknown command exits with a non-zero code."""
        from src.cli import main
        with pytest.raises(SystemExit) as exc:
            with patch('sys.argv', ['circleci-usage-reporter', 'nonexistent-command']):
                main()
        assert exc.value.code != 0


class TestMerge:
    """Test src.merge.handle() directly."""

    def test_merges_multiple_csv_files(self):
        """Multiple CSV files are merged with only one header row."""
        with tempfile.TemporaryDirectory() as tmp:
            for i, rows in enumerate([
                "col1,col2\nA,1\nB,2\n",
                "col1,col2\nC,3\n",
            ]):
                with open(os.path.join(tmp, f"file{i}.csv"), 'w') as f:
                    f.write(rows)

            output = os.path.join(tmp, 'merged.csv')
            from src.merge import handle
            result = handle(argparse.Namespace(input_dir=tmp, output=output))

            assert result == 0
            with open(output) as f:
                lines = f.readlines()
            assert lines[0].strip() == 'col1,col2'
            assert len(lines) == 4  # 1 header + 3 data rows

    def test_returns_error_when_no_csv_files(self):
        """Returns exit code 1 when input directory has no CSV files."""
        with tempfile.TemporaryDirectory() as tmp:
            from src.merge import handle
            result = handle(argparse.Namespace(input_dir=tmp, output=os.path.join(tmp, 'out.csv')))
            assert result == 1

    def test_standalone_main_help(self):
        """Standalone main() accepts --help without AttributeError."""
        from src.merge import main
        with pytest.raises(SystemExit) as exc:
            with patch('sys.argv', ['merge', '--help']):
                main()
        assert exc.value.code == 0


class TestGet:
    """Test src.get helper functions."""

    def test_validate_args_passes_with_all_required(self):
        from src.get import _validate_args
        assert _validate_args('org-id', 'token', '2024-01-01', '2024-01-31') is True

    def test_validate_args_fails_without_token(self):
        from src.get import _validate_args
        assert _validate_args('org-id', None, '2024-01-01', '2024-01-31') is False

    def test_validate_args_fails_without_org_id(self):
        from src.get import _validate_args
        assert _validate_args(None, 'token', '2024-01-01', '2024-01-31') is False

    def test_exponential_backoff_values(self):
        """Wait time doubles each attempt and is capped at MAX_WAIT_TIME."""
        from src.get import _calculate_wait_time, BASE_DELAY, MAX_WAIT_TIME
        assert _calculate_wait_time(1) == BASE_DELAY
        assert _calculate_wait_time(2) == BASE_DELAY * 2
        assert _calculate_wait_time(3) == BASE_DELAY * 4
        assert _calculate_wait_time(100) == MAX_WAIT_TIME

    def test_download_raises_on_non_200(self):
        """RuntimeError is raised when a download URL returns a non-200 status."""
        from src.get import _download_csv_files
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.text = 'Forbidden'
        with patch('src.get.requests.get', return_value=mock_response):
            with tempfile.TemporaryDirectory() as tmp:
                with pytest.raises(RuntimeError, match="status 403"):
                    _download_csv_files(['http://fake-url'], tmp)

    def test_download_extracts_gzip_on_success(self):
        """A 200 response is decompressed and saved as a CSV file."""
        from src.get import _download_csv_files
        csv_content = b'col1,col2\nval1,val2\n'
        buf = io.BytesIO()
        with gzip.GzipFile(fileobj=buf, mode='wb') as gz:
            gz.write(csv_content)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = buf.getvalue()

        with patch('src.get.requests.get', return_value=mock_response):
            with tempfile.TemporaryDirectory() as tmp:
                _download_csv_files(['http://fake-url'], tmp)
                files = os.listdir(tmp)
                assert files == ['usage_report_0.csv']
                with open(os.path.join(tmp, files[0])) as f:
                    assert 'col1,col2' in f.read()

    @patch('src.get.requests.post')
    def test_request_report_returns_job_id(self, mock_post):
        """_request_report extracts and returns the job ID from the API response."""
        from src.get import _request_report
        mock_post.return_value.status_code = 201
        mock_post.return_value.json.return_value = {'usage_export_job_id': 'job-abc'}

        job_id = _request_report('org-123', 'token-xyz', '2024-01-01', '2024-01-31')

        assert job_id == 'job-abc'
        call_kwargs = mock_post.call_args
        assert 'org-123' in call_kwargs[0][0]
        assert call_kwargs[1]['headers']['Circle-Token'] == 'token-xyz'

    @patch('src.get.requests.post')
    def test_request_report_returns_none_on_failure(self, mock_post):
        """_request_report returns None when the API returns a non-201 status."""
        from src.get import _request_report
        mock_post.return_value.status_code = 403
        mock_post.return_value.text = 'Forbidden'

        assert _request_report('org', 'token', '2024-01-01', '2024-01-31') is None


class TestStandaloneEntrypoints:
    """Verify all module standalone main() functions accept --help without crashing."""

    @pytest.mark.parametrize("module,argv", [
        ('src.merge', ['merge', '--help']),
        ('src.create_graph', ['create-graph', '--help']),
        ('src.send_to_doit', ['send-to-doit', '--help']),
        ('src.run_analysis', ['run-analysis', '--help']),
    ])
    def test_help_exits_zero(self, module, argv):
        import importlib
        mod = importlib.import_module(module)
        with pytest.raises(SystemExit) as exc:
            with patch('sys.argv', argv):
                mod.main()
        assert exc.value.code == 0
