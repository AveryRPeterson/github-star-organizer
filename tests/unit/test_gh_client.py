import unittest
from unittest.mock import patch, MagicMock
import json
import subprocess
from github_star_organizer.gh_client import run_query, GitHubAPIError


class TestRunQuery(unittest.TestCase):
    @patch("subprocess.run")
    def test_run_query_success(self, mock_run):
        """Test successful GraphQL query execution"""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = '{"data": {"viewer": {"login": "testuser"}}}'
        mock_run.return_value = mock_result

        result = run_query("query { viewer { login } }")

        self.assertIn("data", result)
        self.assertEqual(result["data"]["viewer"]["login"], "testuser")

    @patch("subprocess.run")
    def test_run_query_with_variables(self, mock_run):
        """Test query with variables"""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = '{"data": {"repository": {"id": "abc123"}}}'
        mock_run.return_value = mock_result

        result = run_query("query($owner: String!) { ... }", {"owner": "torvalds"})

        # Verify variables were passed to subprocess
        call_args = mock_run.call_args
        self.assertIn("owner=torvalds", str(call_args))

    @patch("subprocess.run")
    def test_run_query_api_error(self, mock_run):
        """Test error handling when gh CLI fails"""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "Authentication failed"
        mock_run.return_value = mock_result

        with self.assertRaises(GitHubAPIError) as context:
            run_query("query { viewer { login } }")

        self.assertIn("Authentication failed", str(context.exception))

    @patch("subprocess.run")
    def test_run_query_invalid_json(self, mock_run):
        """Test error handling for invalid JSON response"""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "not valid json"
        mock_run.return_value = mock_result

        with self.assertRaises(GitHubAPIError):
            run_query("query { viewer { login } }")

    @patch("subprocess.run")
    def test_run_query_command_format(self, mock_run):
        """Test that gh command is formatted correctly"""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = '{"data": {}}'
        mock_run.return_value = mock_result

        run_query("test query")

        # Verify the command structure
        call_args = mock_run.call_args[0][0]
        self.assertEqual(call_args[0], "gh")
        self.assertEqual(call_args[1], "api")
        self.assertEqual(call_args[2], "graphql")


if __name__ == "__main__":
    unittest.main()
