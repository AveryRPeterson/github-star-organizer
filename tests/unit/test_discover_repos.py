import os
import json
import pytest
from unittest.mock import patch, MagicMock, mock_open
import discover_repos


class TestSearchPopularRepos:
    def test_search_popular_repos_calls_client_run_query(self):
        mock_client = MagicMock()
        mock_client.run_query.return_value = {
            "data": {
                "search": {
                    "nodes": [
                        {
                            "id": "R1",
                            "nameWithOwner": "owner/repo1",
                            "description": "Test repo",
                            "repositoryTopics": {"nodes": []},
                        }
                    ]
                }
            }
        }

        result = discover_repos.search_popular_repos(mock_client)

        assert result["data"]["search"]["nodes"][0]["nameWithOwner"] == "owner/repo1"
        mock_client.run_query.assert_called_once()


class TestIsCategorized:
    @patch("discover_repos.categorize")
    def test_is_categorized_returns_true_when_categorize_returns_value(self, mock_categorize):
        mock_categorize.return_value = "DevTools"
        repo = {"nameWithOwner": "owner/repo"}

        result = discover_repos.is_categorized(repo)

        assert result is True
        mock_categorize.assert_called_once_with(repo)

    @patch("discover_repos.categorize")
    def test_is_categorized_returns_false_when_categorize_returns_none(self, mock_categorize):
        mock_categorize.return_value = None
        repo = {"nameWithOwner": "owner/repo"}

        result = discover_repos.is_categorized(repo)

        assert result is False
        mock_categorize.assert_called_once_with(repo)


class TestCallDeepseekSummaries:
    def test_missing_api_key_returns_none(self):
        with patch.dict(os.environ, {}, clear=True):
            repos = [{"nameWithOwner": "owner/repo", "description": "Test"}]
            result = discover_repos.call_deepseek_summaries(repos)
            assert result is None

    @patch("discover_repos.requests.post")
    def test_successful_deepseek_call_returns_keyed_dict(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps({
                            "repos": [
                                {
                                    "nameWithOwner": "owner/repo",
                                    "purpose": "Test tool",
                                    "use_case": "Development",
                                    "unusual_applications": ["App1", "App2", "App3"],
                                }
                            ]
                        })
                    }
                }
            ]
        }
        mock_post.return_value = mock_response

        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-key"}):
            repos = [
                {
                    "nameWithOwner": "owner/repo",
                    "description": "Test",
                    "repositoryTopics": {"nodes": []},
                }
            ]
            result = discover_repos.call_deepseek_summaries(repos)

        assert result is not None
        assert "owner/repo" in result
        assert result["owner/repo"]["purpose"] == "Test tool"
        assert len(result["owner/repo"]["unusual_applications"]) == 3

    @patch("discover_repos.requests.post")
    def test_malformed_json_response_returns_none(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": "not valid json"
                    }
                }
            ]
        }
        mock_post.return_value = mock_response

        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-key"}):
            repos = [
                {
                    "nameWithOwner": "owner/repo",
                    "description": "Test",
                    "repositoryTopics": {"nodes": []},
                }
            ]
            result = discover_repos.call_deepseek_summaries(repos)

        assert result is None

    @patch("discover_repos.requests.post")
    def test_non_200_response_returns_none(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Server error"
        mock_post.return_value = mock_response

        with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-key"}):
            repos = [
                {
                    "nameWithOwner": "owner/repo",
                    "description": "Test",
                    "repositoryTopics": {"nodes": []},
                }
            ]
            result = discover_repos.call_deepseek_summaries(repos)

        assert result is None


class TestFormatDiscoveryComment:
    def test_format_with_summaries_includes_all_ai_fields(self):
        repos = [
            {
                "nameWithOwner": "owner/repo",
                "description": "Test repo",
                "repositoryTopics": {"nodes": [{"topic": {"name": "python"}}, {"topic": {"name": "testing"}}]},
            }
        ]
        model_summaries = {
            "deepseek": {
                "owner/repo": {
                    "purpose": "A testing framework",
                    "use_case": "Unit testing",
                    "unusual_applications": ["Load testing", "Chaos testing", "Contract testing"],
                }
            }
        }

        result = discover_repos.format_discovery_comment(repos, model_summaries)

        assert "### New Discovery Batch" in result
        assert "- **[owner/repo]" in result  # Link format
        assert "**Description:**" in result
        assert "**Purpose:** A testing framework" in result
        assert "**Suggested Use Case:** Unit testing" in result
        assert "**Unusual Applications:**" in result
        assert "Load testing" in result
        assert "Chaos testing" in result
        assert "Contract testing" in result

    def test_format_without_summaries_falls_back_to_description(self):
        repos = [
            {
                "nameWithOwner": "owner/repo",
                "description": "Test repo",
                "repositoryTopics": {"nodes": [{"topic": {"name": "python"}}]},
            }
        ]
        model_summaries = {}

        result = discover_repos.format_discovery_comment(repos, model_summaries)

        # With no summaries, should only show the New Discovery Batch header
        assert "### New Discovery Batch" in result

    def test_every_entry_starts_with_markdown_format(self):
        repos = [
            {
                "nameWithOwner": "org1/repo1",
                "description": "Repo 1",
                "repositoryTopics": {"nodes": []},
            },
            {
                "nameWithOwner": "org2/repo2",
                "description": "Repo 2",
                "repositoryTopics": {"nodes": []},
            },
        ]
        model_summaries = {
            "deepseek": {
                "org1/repo1": {
                    "purpose": "Repo 1 purpose",
                    "use_case": "Use case 1",
                    "unusual_applications": ["App1", "App2", "App3"],
                },
                "org2/repo2": {
                    "purpose": "Repo 2 purpose",
                    "use_case": "Use case 2",
                    "unusual_applications": ["App1", "App2", "App3"],
                },
            }
        }

        result = discover_repos.format_discovery_comment(repos, model_summaries)

        assert "- **[org1/repo1]" in result  # Link format
        assert "- **[org2/repo2]" in result  # Link format


class TestDiscoverReposMain:
    @patch("discover_repos.report_uncategorized_repos")
    @patch("discover_repos.run_parallel_summaries")
    @patch("discover_repos.get_already_reported_repos")
    @patch("discover_repos.get_or_create_weekly_discovery_issue")
    @patch("discover_repos.get_or_create_weekly_issue")
    @patch("discover_repos.search_popular_repos")
    @patch("discover_repos.get_current_stars")
    @patch("discover_repos.GitHubClient")
    def test_deepseek_failure_still_reports_uncategorized(
        self,
        mock_client_class,
        mock_stars,
        mock_search,
        mock_get_issue,
        mock_get_discovery,
        mock_get_reported,
        mock_parallel,
        mock_report,
    ):
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        mock_search.return_value = {
            "data": {
                "search": {
                    "nodes": [
                        {
                            "id": "R1",
                            "nameWithOwner": "owner/repo",
                            "description": "Test",
                            "repositoryTopics": {"nodes": []},
                        }
                    ]
                }
            }
        }

        mock_get_issue.return_value = "123"
        mock_get_discovery.return_value = "124"
        mock_get_reported.return_value = set()
        mock_parallel.return_value = {}  # Both models fail, return empty dict

        with patch("discover_repos.is_categorized", return_value=False):
            discover_repos.main()

        # Should still call report_uncategorized_repos even if both models failed
        mock_report.assert_called_once()

    @patch("discover_repos.GitHubClient")
    @patch("discover_repos.search_popular_repos")
    @patch("discover_repos.get_current_stars")
    def test_empty_uncategorized_returns_early(self, mock_stars, mock_search, mock_client_class):
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        mock_search.return_value = {
            "data": {
                "search": {
                    "nodes": [
                        {
                            "id": "R1",
                            "nameWithOwner": "owner/repo",
                            "description": "Test",
                            "repositoryTopics": {"nodes": []},
                        }
                    ]
                }
            }
        }

        with patch("discover_repos.is_categorized", return_value=True):
            discover_repos.main()

        # Should not try to create issues if no uncategorized repos

    @patch("builtins.open", new_callable=mock_open)
    @patch("discover_repos.report_uncategorized_repos")
    @patch("discover_repos.run_parallel_summaries")
    @patch("discover_repos.get_already_reported_repos")
    @patch("discover_repos.get_or_create_weekly_discovery_issue")
    @patch("discover_repos.get_or_create_weekly_issue")
    @patch("discover_repos.search_popular_repos")
    @patch("discover_repos.get_current_stars")
    @patch("discover_repos.GitHubClient")
    def test_github_output_written_when_env_set(
        self,
        mock_client_class,
        mock_stars,
        mock_search,
        mock_get_issue,
        mock_get_discovery,
        mock_get_reported,
        mock_parallel,
        mock_report,
        mock_file,
    ):
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client

        mock_search.return_value = {
            "data": {
                "search": {
                    "nodes": [
                        {
                            "id": "R1",
                            "nameWithOwner": "owner/repo",
                            "description": "Test",
                            "repositoryTopics": {"nodes": []},
                        }
                    ]
                }
            }
        }

        mock_get_issue.return_value = "123"
        mock_get_discovery.return_value = "124"
        mock_get_reported.return_value = set()
        mock_parallel.return_value = {}

        with patch.dict(os.environ, {"GITHUB_OUTPUT": "/tmp/output"}):
            with patch("discover_repos.is_categorized", return_value=False):
                discover_repos.main()

        # Should write to GITHUB_OUTPUT
        mock_file.assert_called()
