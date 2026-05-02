import unittest
from unittest.mock import MagicMock
from github_star_organizer.categorizer import categorize, get_categorized_ids, get_recent_stars


class TestCategorize(unittest.TestCase):
    def test_categorize_ai_agents(self):
        """Test categorization by repo name"""
        repo = {
            "nameWithOwner": "user/my-llm-project",
            "description": "An awesome project",
            "repositoryTopics": {"nodes": []}
        }
        result = categorize(repo)
        self.assertEqual(result, "AI Agents & LLMs")

    def test_categorize_3d_printing(self):
        """Test categorization by description"""
        repo = {
            "nameWithOwner": "user/repo",
            "description": "A 3d printer mesh tool",
            "repositoryTopics": {"nodes": []}
        }
        result = categorize(repo)
        self.assertEqual(result, "3D Printing & CAD")

    def test_categorize_by_topic(self):
        """Test categorization by repository topics"""
        repo = {
            "nameWithOwner": "user/repo",
            "description": "none",
            "repositoryTopics": {"nodes": [
                {"topic": {"name": "mechanical-keyboard"}},
                {"topic": {"name": "zmk"}}
            ]}
        }
        result = categorize(repo)
        self.assertEqual(result, "Hardware & Keyboards")

    def test_categorize_case_insensitive(self):
        """Test that categorization is case-insensitive"""
        repo = {
            "nameWithOwner": "USER/ANDROID-TOOL",
            "description": "DESC",
            "repositoryTopics": {"nodes": []}
        }
        result = categorize(repo)
        self.assertEqual(result, "Android & Termux")

    def test_categorize_priority_ordering(self):
        """Test that priority categories are checked first"""
        # Repo matches both AI (gpt) and Tools (cli)
        # AI should win due to priority ordering
        repo = {
            "nameWithOwner": "user/gpt-cli",
            "description": "A tool",
            "repositoryTopics": {"nodes": []}
        }
        result = categorize(repo)
        self.assertEqual(result, "AI Agents & LLMs")

    def test_categorize_dynamic_category(self):
        """Test categorization with dynamic categories from config"""
        repo = {
            "nameWithOwner": "user/q-sim",
            "description": "A quantum simulator",
            "repositoryTopics": {"nodes": []}
        }
        result = categorize(repo)
        self.assertEqual(result, "Quantum Computing")

    def test_categorize_no_match(self):
        """Test when no category matches"""
        repo = {
            "nameWithOwner": "user/unknown",
            "description": "just some random text",
            "repositoryTopics": {"nodes": []}
        }
        result = categorize(repo)
        self.assertIsNone(result)

    def test_categorize_empty_repo(self):
        """Test with minimal repo data"""
        repo = {}
        result = categorize(repo)
        self.assertIsNone(result)

    def test_categorize_missing_description(self):
        """Test when description is None"""
        repo = {
            "nameWithOwner": "user/ai-bot",
            "description": None,
            "repositoryTopics": {"nodes": []}
        }
        result = categorize(repo)
        self.assertEqual(result, "AI Agents & LLMs")


class TestGetCategorizedIds(unittest.TestCase):
    def test_get_categorized_ids(self):
        """Test fetching already-categorized repo IDs"""
        mock_client = MagicMock()
        mock_client.run_query.return_value = {
            "data": {
                "viewer": {
                    "lists": {
                        "nodes": [
                            {
                                "items": {
                                    "nodes": [
                                        {"id": "repo1"},
                                        {"id": "repo2"}
                                    ]
                                }
                            }
                        ]
                    }
                }
            }
        }

        result = get_categorized_ids(mock_client)
        self.assertEqual(result, {"repo1", "repo2"})

    def test_get_categorized_ids_api_error(self):
        """Test error handling when API fails"""
        mock_client = MagicMock()
        mock_client.run_query.return_value = None

        result = get_categorized_ids(mock_client)
        self.assertEqual(result, set())


class TestGetRecentStars(unittest.TestCase):
    def test_get_recent_stars(self):
        """Test fetching recent starred repositories"""
        mock_client = MagicMock()
        mock_client.run_query.return_value = {
            "data": {
                "viewer": {
                    "starredRepositories": {
                        "nodes": [
                            {
                                "id": "repo1",
                                "nameWithOwner": "owner/repo1",
                                "description": "A cool repo",
                                "repositoryTopics": {"nodes": []}
                            }
                        ]
                    }
                }
            }
        }

        result = get_recent_stars(mock_client)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["nameWithOwner"], "owner/repo1")


if __name__ == "__main__":
    unittest.main()
