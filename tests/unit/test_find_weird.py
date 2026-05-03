import os
import json
import pytest
from unittest.mock import patch, MagicMock, mock_open
import find_weird


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

        result = find_weird.search_popular_repos(mock_client)

        assert result["data"]["search"]["nodes"][0]["nameWithOwner"] == "owner/repo1"
        mock_client.run_query.assert_called_once()


class TestIsCategorized:
    @patch("find_weird.categorize")
    def test_is_categorized_returns_true_when_categorize_returns_value(self, mock_categorize):
        mock_categorize.return_value = "DevTools"
        repo = {"nameWithOwner": "owner/repo"}

        result = find_weird.is_categorized(repo)

        assert result is True
        mock_categorize.assert_called_once_with(repo)

    @patch("find_weird.categorize")
    def test_is_categorized_returns_false_when_categorize_returns_none(self, mock_categorize):
        mock_categorize.return_value = None
        repo = {"nameWithOwner": "owner/repo"}

        result = find_weird.is_categorized(repo)

        assert result is False
        mock_categorize.assert_called_once_with(repo)


class TestCallDeepseekSummaries:
    def test_missing_api_key_returns_none(self):
        with patch.dict(os.environ, {}, clear=True):
            repos = [{"nameWithOwner": "owner/repo", "description": "Test"}]
            result = find_weird.call_deepseek_summaries(repos)
            assert result is None

    @patch("find_weird.requests.post")
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
            result = find_weird.call_deepseek_summaries(repos)

        assert result is not None
        assert "owner/repo" in result
        assert result["owner/repo"]["purpose"] == "Test tool"
        assert len(result["owner/repo"]["unusual_applications"]) == 3

    @patch("find_weird.requests.post")
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
            result = find_weird.call_deepseek_summaries(repos)

        assert result is None

    @patch("find_weird.requests.post")
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
            result = find_weird.call_deepseek_summaries(repos)

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
        summaries = {
            "owner/repo": {
                "purpose": "A testing framework",
                "use_case": "Unit testing",
                "unusual_applications": ["Load testing", "Chaos testing", "Contract testing"],
            }
        }

        result = find_weird.format_discovery_comment(repos, summaries)

        assert "### New Discovery Batch" in result
        assert "- **owner/repo**" in result
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
        summaries = {}

        result = find_weird.format_discovery_comment(repos, summaries)

        assert "- **owner/repo**" in result
        assert "**Description:** Test repo" in result
        assert "**Purpose:**" not in result

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
        summaries = {}

        result = find_weird.format_discovery_comment(repos, summaries)

        assert "- **org1/repo1**" in result
        assert "- **org2/repo2**" in result


class TestFindWeirdMain:
    @patch("find_weird.report_uncategorized_repos")
    @patch("find_weird.call_deepseek_summaries")
    @patch("find_weird.get_already_reported_repos")
    @patch("find_weird.get_or_create_weekly_discovery_issue")
    @patch("find_weird.get_or_create_weekly_issue")
    @patch("find_weird.search_popular_repos")
    @patch("find_weird.GitHubClient")
    def test_deepseek_failure_still_reports_uncategorized(
        self,
        mock_client_class,
        mock_search,
        mock_get_issue,
        mock_get_discovery,
        mock_get_reported,
        mock_deepseek,
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
        mock_deepseek.return_value = None  # DeepSeek failure

        with patch("find_weird.is_categorized", return_value=False):
            find_weird.main()

        # Should still call report_uncategorized_repos even if DeepSeek failed
        mock_report.assert_called_once()

    @patch("find_weird.GitHubClient")
    @patch("find_weird.search_popular_repos")
    def test_empty_uncategorized_returns_early(self, mock_search, mock_client_class):
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

        with patch("find_weird.is_categorized", return_value=True):
            find_weird.main()

        # Should not try to create issues if no uncategorized repos

    @patch("builtins.open", new_callable=mock_open)
    @patch("find_weird.report_uncategorized_repos")
    @patch("find_weird.call_deepseek_summaries")
    @patch("find_weird.get_already_reported_repos")
    @patch("find_weird.get_or_create_weekly_discovery_issue")
    @patch("find_weird.get_or_create_weekly_issue")
    @patch("find_weird.search_popular_repos")
    @patch("find_weird.GitHubClient")
    def test_github_output_written_when_env_set(
        self,
        mock_client_class,
        mock_search,
        mock_get_issue,
        mock_get_discovery,
        mock_get_reported,
        mock_deepseek,
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
        mock_deepseek.return_value = {}

        with patch.dict(os.environ, {"GITHUB_OUTPUT": "/tmp/output"}):
            with patch("find_weird.is_categorized", return_value=False):
                find_weird.main()

        # Should write to GITHUB_OUTPUT
        mock_file.assert_called()
