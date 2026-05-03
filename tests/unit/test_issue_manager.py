import unittest
from unittest.mock import MagicMock, patch, call
import datetime
from github_star_organizer.issue_manager import (
    get_or_create_weekly_issue,
    get_or_create_weekly_discovery_issue,
    get_already_reported_repos,
    report_uncategorized_repos,
    close_issue,
    IssueError
)


class TestGetOrCreateWeeklyIssue(unittest.TestCase):
    @patch("github_star_organizer.issue_manager.run_command")
    @patch("github_star_organizer.issue_manager.datetime")
    def test_create_new_issue_when_none_exists(self, mock_datetime, mock_run_command):
        """Test creating a new issue when none exists"""
        mock_datetime.date.today.return_value = datetime.date(2026, 5, 2)

        mock_client = MagicMock()
        mock_run_command.side_effect = [
            "[]",  # No existing issues
            "https://github.com/user/repo/issues/42"  # Issue created
        ]

        result = get_or_create_weekly_issue(mock_client)
        self.assertEqual(result, "42")

    @patch("github_star_organizer.issue_manager.run_command")
    @patch("github_star_organizer.issue_manager.datetime")
    def test_return_existing_issue(self, mock_datetime, mock_run_command):
        """Test returning existing issue for this week"""
        mock_datetime.date.today.return_value = datetime.date(2026, 5, 2)

        mock_client = MagicMock()
        mock_run_command.return_value = '[{"number": 42, "title": "Uncategorized Stars: 2026-W18"}]'

        result = get_or_create_weekly_issue(mock_client)
        self.assertEqual(result, "42")

    @patch("github_star_organizer.issue_manager.run_command")
    @patch("github_star_organizer.issue_manager.datetime")
    def test_close_old_duplicate_issues(self, mock_datetime, mock_run_command):
        """Test that old issues are closed and consolidated"""
        mock_datetime.date.today.return_value = datetime.date(2026, 5, 2)

        mock_client = MagicMock()
        mock_run_command.side_effect = [
            '[{"number": 42, "title": "Uncategorized Stars: 2026-W18"}, {"number": 41, "title": "Uncategorized Stars: 2026-W17"}]',
            "success",  # comment on old issue
            "success"   # close old issue
        ]

        result = get_or_create_weekly_issue(mock_client)

        self.assertEqual(result, "42")


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


class TestGetAlreadyReportedRepos(unittest.TestCase):
    @patch("github_star_organizer.issue_manager.run_command")
    def test_extract_reported_repos(self, mock_run_command):
        """Test extracting repo names from issue comments"""
        comment_body = """
        - **owner/repo1**
          - Description: A tool
        - **owner/repo2**
          - Description: Another tool
        """
        mock_run_command.return_value = comment_body
        mock_client = MagicMock()

        result = get_already_reported_repos(mock_client, "42")
        self.assertEqual(result, {"owner/repo1", "owner/repo2"})

    @patch("github_star_organizer.issue_manager.run_command")
    def test_no_comments_returns_empty(self, mock_run_command):
        """Test when issue has no comments"""
        mock_run_command.return_value = ""
        mock_client = MagicMock()

        result = get_already_reported_repos(mock_client, "42")
        self.assertEqual(result, set())

    @patch("github_star_organizer.issue_manager.run_command")
    def test_invalid_issue_number_returns_empty(self, mock_run_command):
        """Test error handling for invalid issue"""
        mock_run_command.side_effect = IssueError("Issue not found")
        mock_client = MagicMock()

        result = get_already_reported_repos(mock_client, "999")
        self.assertEqual(result, set())


class TestReportUncategorizedRepos(unittest.TestCase):
    @patch("github_star_organizer.issue_manager.run_command")
    def test_post_comment_with_repos(self, mock_run_command):
        """Test posting a comment with uncategorized repos"""
        mock_client = MagicMock()
        repos = [
            {
                "nameWithOwner": "owner/repo1",
                "description": "A cool project",
                "repositoryTopics": {"nodes": [{"topic": {"name": "python"}}]}
            }
        ]

        report_uncategorized_repos(mock_client, "42", repos)

        # Verify comment was posted
        mock_run_command.assert_called_once()

    @patch("github_star_organizer.issue_manager.run_command")
    def test_no_op_with_empty_repos(self, mock_run_command):
        """Test that empty repos list is a no-op"""
        mock_client = MagicMock()

        report_uncategorized_repos(mock_client, "42", [])

        # Verify no command was run
        mock_run_command.assert_not_called()


class TestCloseIssue(unittest.TestCase):
    @patch("github_star_organizer.issue_manager.run_command")
    def test_close_issue_with_reason(self, mock_run_command):
        """Test closing an issue"""
        mock_client = MagicMock()

        close_issue(mock_client, "42", "Config updated")

        # Verify close was called
        self.assertTrue(mock_run_command.called)

    @patch("github_star_organizer.issue_manager.run_command")
    def test_close_issue_error_handling(self, mock_run_command):
        """Test error handling when close fails"""
        mock_run_command.side_effect = IssueError("Failed to close")
        mock_client = MagicMock()

        with self.assertRaises(IssueError):
            close_issue(mock_client, "42", "Config updated")


class TestIntegration(unittest.TestCase):
    @patch("github_star_organizer.issue_manager.run_command")
    def test_report_with_multiple_repos(self, mock_run_command):
        """Test reporting multiple uncategorized repos in one comment"""
        mock_client = MagicMock()
        repos = [
            {
                "nameWithOwner": "user/repo1",
                "description": "First repo",
                "repositoryTopics": {"nodes": [{"topic": {"name": "python"}}, {"topic": {"name": "cli"}}]}
            },
            {
                "nameWithOwner": "user/repo2",
                "description": "Second repo",
                "repositoryTopics": {"nodes": []}
            }
        ]

        report_uncategorized_repos(mock_client, "42", repos)
        mock_run_command.assert_called_once()

    @patch("github_star_organizer.issue_manager.run_command")
    @patch("github_star_organizer.issue_manager.datetime")
    def test_duplicate_issue_consolidation(self, mock_datetime, mock_run_command):
        """Test that duplicate issues for same week are consolidated"""
        mock_datetime.date.today.return_value = datetime.date(2026, 5, 2)

        mock_client = MagicMock()
        # Two issues with same week, one old issue
        mock_run_command.side_effect = [
            '[{"number": 42, "title": "Uncategorized Stars: 2026-W18"}, {"number": 43, "title": "Uncategorized Stars: 2026-W18"}, {"number": 41, "title": "Uncategorized Stars: 2026-W17"}]',
            "success",  # comment on duplicate
            "success",  # close duplicate
            "success",  # comment on old
            "success"   # close old
        ]

        result = get_or_create_weekly_issue(mock_client)
        self.assertEqual(result, "42")


if __name__ == "__main__":
    unittest.main()
