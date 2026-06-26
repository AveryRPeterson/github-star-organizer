import unittest
from unittest.mock import patch, MagicMock

import categorize


class TestCategorizeMain(unittest.TestCase):
    @patch("categorize.state_db")
    @patch("categorize.load_config")
    @patch("categorize.GitHubClient")
    @patch("categorize.get_categorized_ids")
    @patch("categorize.categorize")
    def test_new_uncategorized_repo_is_inserted(
        self, mock_categorize, mock_get_categorized_ids, mock_client_class, mock_load_config, mock_state_db
    ):
        mock_load_config.return_value = {"lists": {}}
        mock_get_categorized_ids.return_value = set()
        mock_state_db.get_uncategorized_repos.return_value = set()

        client = MagicMock()
        client.run_query.return_value = {
            "data": {
                "viewer": {
                    "starredRepositories": {
                        "nodes": [
                            {
                                "id": "R1",
                                "nameWithOwner": "owner/repo",
                                "description": "desc",
                                "repositoryTopics": {"nodes": []},
                            }
                        ]
                    }
                }
            }
        }
        mock_client_class.return_value = client
        mock_categorize.return_value = None

        categorize.main()

        mock_state_db.insert_uncategorized_repos.assert_called_once()
        inserted = mock_state_db.insert_uncategorized_repos.call_args[0][0]
        self.assertEqual(inserted[0]["nameWithOwner"], "owner/repo")

    @patch("categorize.state_db")
    @patch("categorize.load_config")
    @patch("categorize.GitHubClient")
    @patch("categorize.get_categorized_ids")
    @patch("categorize.categorize")
    def test_already_reported_repo_is_skipped(
        self, mock_categorize, mock_get_categorized_ids, mock_client_class, mock_load_config, mock_state_db
    ):
        mock_load_config.return_value = {"lists": {}}
        mock_get_categorized_ids.return_value = set()
        mock_state_db.get_uncategorized_repos.return_value = {"owner/repo"}

        client = MagicMock()
        client.run_query.return_value = {
            "data": {
                "viewer": {
                    "starredRepositories": {
                        "nodes": [
                            {
                                "id": "R1",
                                "nameWithOwner": "owner/repo",
                                "description": "desc",
                                "repositoryTopics": {"nodes": []},
                            }
                        ]
                    }
                }
            }
        }
        mock_client_class.return_value = client
        mock_categorize.return_value = None

        categorize.main()

        mock_state_db.insert_uncategorized_repos.assert_not_called()


if __name__ == "__main__":
    unittest.main()
