import unittest
from unittest.mock import patch, MagicMock, call
import json
import sys

# Mock requests before importing distill
sys.modules['requests'] = MagicMock()

import distill
import categorize

class TestSecurityFix(unittest.TestCase):

    @patch('distill.run_command')
    def test_distill_get_latest_uncategorized_issue_filters_by_author_me(self, mock_run):
        # Setup mock to return a list of issues
        mock_run.return_value = json.dumps([{"number": 1, "body": "test body", "title": "Uncategorized Stars: 2026-W16"}])

        issue = distill.get_latest_uncategorized_issue()

        # Verify the command called contains the author:@me filter
        args, _ = mock_run.call_args
        cmd = args[0]
        self.assertIn("author:@me", cmd[6])
        self.assertEqual(issue["number"], 1)

    @patch('distill.run_command')
    def test_distill_get_issue_comments_filters_by_dynamic_user(self, mock_run):
        # First call is for user lookup, second for issue view
        mock_run.side_effect = ["current_user", "comment body"]

        distill.get_issue_comments(1)

        # Verify first call was user lookup
        self.assertEqual(mock_run.call_args_list[0], call(["gh", "api", "user", "--json", "login", "-q", ".login"]))

        # Verify second call contains the jq filter for current_user
        args, _ = mock_run.call_args_list[1]
        cmd = args[0]
        self.assertTrue(any(".author.login == \"current_user\"" in arg for arg in cmd))

    @patch('subprocess.run')
    def test_categorize_get_or_create_issue_filters_by_author_me(self, mock_run):
        # Mocking subprocess.run for the search part
        mock_run.return_value = MagicMock(returncode=0, stdout="123")

        issue_num = categorize.get_or_create_issue()

        # Verify the command called contains the author:@me filter
        args, _ = mock_run.call_args_list[0]
        cmd = args[0]
        self.assertIn("author:@me", cmd[6])
        self.assertEqual(issue_num, "123")

if __name__ == '__main__':
    unittest.main()
