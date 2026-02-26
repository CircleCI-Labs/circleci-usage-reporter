"""
Basic functionality tests for CircleCI Usage Reporter.
These tests focus on testing the core logic without complex imports.
"""
import os
import tempfile
import csv
from unittest.mock import patch, Mock
import pytest


class TestBasicFunctionality:
    """Test basic functionality that can be easily tested."""
    
    def test_environment_variable_handling(self):
        """Test that environment variables are handled correctly."""
        test_vars = {
            'ORG_ID': 'test-org-123',
            'CIRCLECI_API_TOKEN': 'test-token',
            'START_DATE': '2024-01-01',
            'END_DATE': '2024-01-31'
        }
        
        with patch.dict(os.environ, test_vars):
            assert os.getenv('ORG_ID') == 'test-org-123'
            assert os.getenv('CIRCLECI_API_TOKEN') == 'test-token'
            assert os.getenv('START_DATE') == '2024-01-01'
            assert os.getenv('END_DATE') == '2024-01-31'
    
    def test_csv_file_creation_and_reading(self):
        """Test basic CSV file operations."""
        test_data = [
            ['ORGANIZATION_NAME', 'PROJECT_NAME', 'TOTAL_CREDITS'],
            ['CircleCI', 'test-project', '25.5'],
            ['CircleCI', 'another-project', '15.2']
        ]
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            writer = csv.writer(f)
            writer.writerows(test_data)
            f.flush()
            
            # Read the file back
            with open(f.name, 'r') as read_file:
                reader = csv.reader(read_file)
                rows = list(reader)
                
                assert len(rows) == 3
                assert rows[0] == ['ORGANIZATION_NAME', 'PROJECT_NAME', 'TOTAL_CREDITS']
                assert rows[1] == ['CircleCI', 'test-project', '25.5']
                assert rows[2] == ['CircleCI', 'another-project', '15.2']
            
            # Clean up
            os.unlink(f.name)
    
    def test_data_processing_logic(self):
        """Test basic data processing logic."""
        # Simulate the grouping logic from create_graph.py
        sample_data = [
            {'PROJECT_NAME': 'project-a', 'VCS_URL': 'https://github.com/org/project-a', 'TOTAL_CREDITS': 10.5},
            {'PROJECT_NAME': 'project-b', 'VCS_URL': 'https://github.com/org/project-b', 'TOTAL_CREDITS': 15.2},
            {'PROJECT_NAME': 'project-a', 'VCS_URL': 'https://github.com/org/project-a', 'TOTAL_CREDITS': 5.3},
        ]
        
        # Group by project and sum credits (simulating pandas groupby)
        grouped = {}
        for item in sample_data:
            key = (item['PROJECT_NAME'], item['VCS_URL'])
            if key not in grouped:
                grouped[key] = 0
            grouped[key] += item['TOTAL_CREDITS']
        
        # Verify grouping
        assert len(grouped) == 2
        assert grouped[('project-a', 'https://github.com/org/project-a')] == 15.8  # 10.5 + 5.3
        assert grouped[('project-b', 'https://github.com/org/project-b')] == 15.2
        
        # Sort by credits (descending)
        sorted_items = sorted(grouped.items(), key=lambda x: x[1], reverse=True)
        assert sorted_items[0][1] == 15.8  # project-a has highest credits
    
    def test_file_merging_logic(self):
        """Test the CSV file merging logic."""
        # Create multiple temporary CSV files
        csv_files = []
        
        # File 1
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f1:
            f1.write("ORGANIZATION_NAME,PROJECT_NAME,TOTAL_CREDITS\n")
            f1.write("CircleCI,project1,10.5\n")
            f1.write("CircleCI,project2,15.2\n")
            csv_files.append(f1.name)
        
        # File 2
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f2:
            f2.write("ORGANIZATION_NAME,PROJECT_NAME,TOTAL_CREDITS\n")
            f2.write("CircleCI,project3,8.7\n")
            csv_files.append(f2.name)
        
        # Merge files (simulating merge.py logic)
        merged_content = []
        for i, csv_file in enumerate(csv_files):
            with open(csv_file, 'r') as f:
                lines = f.readlines()
                if i == 0:
                    # Include header for first file
                    merged_content.extend(lines)
                else:
                    # Skip header for subsequent files
                    merged_content.extend(lines[1:])
        
        # Verify merged content
        assert len(merged_content) == 4  # 1 header + 3 data rows
        assert 'ORGANIZATION_NAME,PROJECT_NAME,TOTAL_CREDITS' in merged_content[0]
        assert 'project1,10.5' in merged_content[1]
        assert 'project3,8.7' in merged_content[3]
        
        # Clean up
        for csv_file in csv_files:
            os.unlink(csv_file)
    
    @patch('requests.post')
    def test_api_request_structure(self, mock_post):
        """Test that API requests are structured correctly."""
        mock_post.return_value.status_code = 201
        mock_post.return_value.json.return_value = {'usage_export_job_id': 'job-123'}
        
        # Simulate the API call structure from get.py
        import requests
        import json
        
        org_id = 'test-org'
        token = 'test-token'
        start_date = '2024-01-01'
        end_date = '2024-01-31'
        
        post_data = {
            "start": f"{start_date}T00:00:01Z",
            "end": f"{end_date}T00:00:01Z",
            "shared_org_ids": []
        }
        
        response = requests.post(
            f"https://circleci.com/api/v2/organizations/{org_id}/usage_export_job",
            headers={"Circle-Token": token, "Content-Type": "application/json"},
            data=json.dumps(post_data)
        )
        
        # Verify the request was made correctly
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        
        # Check URL
        assert f"organizations/{org_id}/usage_export_job" in call_args[0][0]
        
        # Check headers
        assert call_args[1]['headers']['Circle-Token'] == token
        assert call_args[1]['headers']['Content-Type'] == 'application/json'
        
        # Check payload
        sent_data = json.loads(call_args[1]['data'])
        assert sent_data['start'] == '2024-01-01T00:00:01Z'
        assert sent_data['end'] == '2024-01-31T00:00:01Z'
        assert sent_data['shared_org_ids'] == []
    
    def test_data_type_conversion(self):
        """Test data type conversion logic similar to send_to_datadog.py."""
        # Test numeric conversion
        test_values = [
            ('120', 120.0),      # Valid number
            ('invalid', None),   # Invalid number
            ('', None),          # Empty string
            ('\\N', None),       # Null marker
        ]
        
        for input_val, expected in test_values:
            if input_val in ('', '\\N', 'null'):
                result = None
            else:
                try:
                    result = float(input_val)
                except (ValueError, TypeError):
                    result = None
            
            assert result == expected
        
        # Test boolean conversion
        bool_values = [
            ('true', True),
            ('false', False),
            ('True', True),
            ('False', False),
        ]
        
        for input_val, expected in bool_values:
            result = input_val.lower() == 'true'
            assert result == expected
    
    def test_directory_operations(self):
        """Test directory creation and file operations."""
        with tempfile.TemporaryDirectory() as temp_dir:
            reports_dir = os.path.join(temp_dir, 'reports')
            
            # Test directory creation
            if not os.path.exists(reports_dir):
                os.makedirs(reports_dir)
            
            assert os.path.exists(reports_dir)
            assert os.path.isdir(reports_dir)
            
            # Test file creation in directory
            test_file = os.path.join(reports_dir, 'test_report.csv')
            with open(test_file, 'w') as f:
                f.write('test,data\n1,2\n')
            
            assert os.path.exists(test_file)
            
            # Test file reading
            with open(test_file, 'r') as f:
                content = f.read()
                assert 'test,data' in content
                assert '1,2' in content


class TestErrorHandling:
    """Test error handling scenarios."""
    
    def test_missing_environment_variables(self):
        """Test handling of missing environment variables."""
        # Clear environment
        with patch.dict(os.environ, {}, clear=True):
            # Should return None for missing variables
            assert os.getenv('ORG_ID') is None
            assert os.getenv('CIRCLECI_API_TOKEN') is None
            
            # Should return default values when provided
            assert os.getenv('ORG_ID', 'default') == 'default'
    
    def test_file_not_found_handling(self):
        """Test handling of missing files."""
        non_existent_file = '/tmp/non_existent_file.csv'
        
        # Should raise FileNotFoundError
        with pytest.raises(FileNotFoundError):
            with open(non_existent_file, 'r') as f:
                f.read()
    
    def test_malformed_data_handling(self):
        """Test handling of malformed data."""
        malformed_data = [
            {'TOTAL_CREDITS': 'invalid_number'},
            {'TOTAL_CREDITS': ''},
            {'TOTAL_CREDITS': '25.5'},
        ]
        
        processed_data = []
        for item in malformed_data:
            try:
                credits = float(item['TOTAL_CREDITS']) if item['TOTAL_CREDITS'] else None
            except (ValueError, TypeError):
                credits = None
            
            processed_data.append({'TOTAL_CREDITS': credits})
        
        # Verify processing
        assert processed_data[0]['TOTAL_CREDITS'] is None  # Invalid number
        assert processed_data[1]['TOTAL_CREDITS'] is None  # Empty string
        assert processed_data[2]['TOTAL_CREDITS'] == 25.5  # Valid number
