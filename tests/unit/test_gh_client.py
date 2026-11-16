import unittest
from unittest.mock import patch, MagicMock
import json
import subprocess
from github_star_organizer.gh_client import run_query, GitHubAPIError, GitHubAuthError


class TestRunQuery(unittest.TestCase):
    @patch("subprocess.run")
    def test_run_query_bad_credentials_raises_auth_error(self, mock_run):
        """401 maps to GitHubAuthError with an actionable message"""
        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="gh: Bad credentials (HTTP 401)")
        with self.assertRaises(GitHubAuthError) as ctx:
            run_query("query { viewer { login } }")
        self.assertIn("Rotate the GH_TOKEN", str(ctx.exception))
        self.assertIsInstance(ctx.exception, GitHubAPIError)

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


class TestListVariables(unittest.TestCase):
    @patch("subprocess.run")
    def test_list_values_become_array_args(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="{}", stderr="")
        run_query("mutation($ids: [ID!]!) { x }", {"ids": ["a", "b"], "n": "1"})
        cmd = mock_run.call_args[0][0]
        self.assertIn("ids[]=a", cmd)
        self.assertIn("ids[]=b", cmd)
        self.assertIn("n=1", cmd)


class TestRetry(unittest.TestCase):
    def fail(self, msg):
        return MagicMock(returncode=1, stdout="", stderr=msg)

    @patch("time.sleep")
    @patch("subprocess.run")
    def test_retries_502_then_succeeds(self, mock_run, mock_sleep):
        mock_run.side_effect = [self.fail("gh: HTTP 502"), self.fail("gh: HTTP 502"),
                                MagicMock(returncode=0, stdout='{"data": {}}', stderr="")]
        self.assertEqual(run_query("query { x }"), {"data": {}})
        self.assertEqual(mock_run.call_count, 3)
        self.assertEqual([c.args[0] for c in mock_sleep.call_args_list], [2.0, 4.0])

    @patch("time.sleep")
    @patch("subprocess.run")
    def test_gives_up_after_max_attempts(self, mock_run, mock_sleep):
        mock_run.return_value = self.fail("gh: HTTP 502")
        with self.assertRaises(GitHubAPIError):
            run_query("query { x }")
        self.assertEqual(mock_run.call_count, 4)

    @patch("time.sleep")
    @patch("subprocess.run")
    def test_does_not_retry_client_errors(self, mock_run, mock_sleep):
        mock_run.return_value = self.fail("gh: HTTP 422 Unprocessable")
        with self.assertRaises(GitHubAPIError):
            run_query("query { x }")
        self.assertEqual(mock_run.call_count, 1)
        mock_sleep.assert_not_called()

    @patch("time.sleep")
    @patch("subprocess.run")
    def test_auth_error_not_retried(self, mock_run, mock_sleep):
        mock_run.return_value = self.fail("gh: Bad credentials (HTTP 401)")
        with self.assertRaises(GitHubAuthError):
            run_query("query { x }")
        self.assertEqual(mock_run.call_count, 1)
