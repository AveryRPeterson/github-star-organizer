import unittest
from unittest.mock import MagicMock, patch, call
import datetime
import json
from github_star_organizer.issue_manager import (
    get_or_create_weekly_discovery_issue,
    close_issue,
    run_command,
    IssueError
)


class TestRunCommand(unittest.TestCase):
    @patch("subprocess.run")
    def test_run_command_success(self, mock_run):
        """Test successful command execution"""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "output"
        mock_run.return_value = mock_result

        result = run_command(["echo", "test"])
        self.assertEqual(result, "output")

    @patch("subprocess.run")
    def test_run_command_failure_raises_error(self, mock_run):
        """Test that command failure raises IssueError"""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "Command failed"
        mock_run.return_value = mock_result

        with self.assertRaises(IssueError) as context:
            run_command(["bad", "command"])
        self.assertIn("Command failed", str(context.exception))


class TestGetOrCreateWeeklyDiscoveryIssue(unittest.TestCase):
    @patch("github_star_organizer.issue_manager.run_command")
    @patch("github_star_organizer.issue_manager.datetime")
    def test_create_new_discovery_issue_when_none_exists(self, mock_datetime, mock_run_command):
        """Test creating a new discovery issue when none exists"""
        mock_datetime.date.today.return_value = datetime.date(2026, 5, 2)

        mock_client = MagicMock()
        mock_run_command.side_effect = [
            "[]",  # No existing issues
            "https://github.com/user/repo/issues/99"  # Issue created
        ]

        result = get_or_create_weekly_discovery_issue(mock_client)
        self.assertEqual(result, "99")

    @patch("github_star_organizer.issue_manager.run_command")
    @patch("github_star_organizer.issue_manager.datetime")
    def test_return_existing_discovery_issue(self, mock_datetime, mock_run_command):
        """Test returning existing discovery issue for this week"""
        mock_datetime.date.today.return_value = datetime.date(2026, 5, 2)

        mock_client = MagicMock()
        mock_run_command.return_value = '[{"number": 99, "title": "Interesting Discoveries: 2026-W18"}]'

        result = get_or_create_weekly_discovery_issue(mock_client)
        self.assertEqual(result, "99")


class TestCreateIssueErrors(unittest.TestCase):
    @patch("github_star_organizer.issue_manager.run_command")
    @patch("github_star_organizer.issue_manager.datetime")
    def test_discovery_list_issues_json_error_handled(self, mock_datetime, mock_run_command):
        """Test discovery issues JSON decode error handling"""
        mock_datetime.date.today.return_value = datetime.date(2026, 5, 2)
        mock_client = MagicMock()
        mock_run_command.return_value = "invalid json"

        result = get_or_create_weekly_discovery_issue(mock_client)
        self.assertIsNotNone(result)

    @patch("github_star_organizer.issue_manager.run_command")
    @patch("github_star_organizer.issue_manager.datetime")
    def test_discovery_create_failure_raises_error(self, mock_datetime, mock_run_command):
        """Test discovery issue creation failure raises IssueError"""
        mock_datetime.date.today.return_value = datetime.date(2026, 5, 2)
        mock_client = MagicMock()
        mock_run_command.side_effect = [
            "[]",
            IssueError("Failed to create discovery")
        ]

        with self.assertRaises(IssueError):
            get_or_create_weekly_discovery_issue(mock_client)


class TestCloseIssue(unittest.TestCase):
    @patch("github_star_organizer.issue_manager.run_command")
    def test_close_issue_with_reason(self, mock_run_command):
        """Test closing an issue"""
        mock_client = MagicMock()

        close_issue(mock_client, "42", "Config updated")

        # Verify close was called
        self.assertTrue(mock_run_command.called)

    @patch("github_star_organizer.issue_manager.run_command")
    def test_close_issue_without_reason(self, mock_run_command):
        """Test closing an issue without adding a reason comment"""
        mock_client = MagicMock()

        close_issue(mock_client, "42", "")

        # Should only close, not comment
        call_count = mock_run_command.call_count
        self.assertEqual(call_count, 1)


if __name__ == "__main__":
    unittest.main()
