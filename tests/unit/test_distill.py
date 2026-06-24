import unittest
from unittest.mock import patch, MagicMock
import json

from distill import format_uncategorized_repos, main


class TestFormatUncategorizedRepos(unittest.TestCase):
    def test_format_includes_name_description_topics(self):
        repos = [
            {"name_with_owner": "user/repo1", "description": "First repo", "topics": "python, cli"},
            {"name_with_owner": "user/repo2", "description": None, "topics": ""},
        ]
        result = format_uncategorized_repos(repos)
        self.assertIn("user/repo1", result)
        self.assertIn("First repo", result)
        self.assertIn("python, cli", result)
        self.assertIn("user/repo2", result)
        self.assertIn("No description", result)


class TestDistillMain(unittest.TestCase):
    @patch("distill.state_db")
    def test_no_pending_repos_skips(self, mock_state_db):
        mock_state_db.get_uncategorized_repos_full.return_value = []
        main()
        mock_state_db.clear_uncategorized_repos.assert_not_called()

    @patch("distill.call_deepseek")
    @patch("builtins.open")
    @patch("distill.state_db")
    def test_success_clears_processed_repos(self, mock_state_db, mock_open, mock_call_deepseek):
        mock_state_db.get_uncategorized_repos_full.return_value = [
            {"name_with_owner": "user/repo1", "description": "Desc", "topics": "python"}
        ]

        config = {"keywords": {"Existing": ["foo"]}}
        new_config = {"keywords": {"Existing": ["foo", "bar"]}}

        read_handle = MagicMock()
        read_handle.__enter__.return_value.read.return_value = json.dumps(config)
        write_handle = MagicMock()
        mock_open.side_effect = [read_handle, write_handle]

        with patch("json.load", return_value=config):
            mock_call_deepseek.return_value = json.dumps(new_config)
            main()

        mock_state_db.clear_uncategorized_repos.assert_called_once_with(["user/repo1"])

    @patch("distill.call_deepseek")
    @patch("builtins.open")
    @patch("distill.state_db")
    def test_failure_keeps_pending_repos(self, mock_state_db, mock_open, mock_call_deepseek):
        mock_state_db.get_uncategorized_repos_full.return_value = [
            {"name_with_owner": "user/repo1", "description": "Desc", "topics": "python"}
        ]

        config = {"keywords": {"Existing": ["foo"]}}
        read_handle = MagicMock()
        mock_open.return_value = read_handle

        with patch("json.load", return_value=config):
            mock_call_deepseek.return_value = None
            main()

        mock_state_db.clear_uncategorized_repos.assert_not_called()


if __name__ == "__main__":
    unittest.main()
