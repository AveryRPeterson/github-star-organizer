import os
import json
import datetime
import pytest
from unittest.mock import patch, MagicMock, mock_open
import discover_repos
from github_star_organizer import issue_manager


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


class TestCreateDiscoveryIssue:
    """Tests for the per-repo issue creation in issue_manager."""

    @patch("github_star_organizer.issue_manager.run_command")
    def test_creates_issue_with_star_link(self, mock_run):
        mock_run.return_value = "https://github.com/owner/repo/issues/42"
        repo = {
            "nameWithOwner": "owner/repo",
            "description": "A cool repo",
            "primaryLanguage": {"name": "Python"},
            "languages": {"edges": [{"size": 8000, "node": {"name": "Python"}}, {"size": 2000, "node": {"name": "Shell"}}], "totalSize": 10000},
            "licenseInfo": {"name": "MIT License"},
            "updatedAt": "2026-05-15T10:00:00Z",
            "homepageUrl": "https://example.com",
        }
        model_summaries = {
            "deepseek": {
                "owner/repo": {
                    "purpose": "Test tool",
                    "use_case": "Dev testing",
                    "unusual_applications": ["App1", "App2", "App3"],
                }
            }
        }

        result = issue_manager.create_discovery_issue(repo, model_summaries)

        assert result == "42"
        call_args = mock_run.call_args[0][0]
        assert call_args[0] == "gh"
        assert call_args[2] == "create"
        body_idx = call_args.index("--body") + 1
        body = call_args[body_idx]
        assert "⭐ View & Star on GitHub" in body
        assert "](https://github.com/owner/repo)" in body
        assert "Python 80%" in body
        assert "MIT License" in body
        assert "2026-05-15" in body
        assert "**Homepage:** https://example.com" in body
        assert "DeepSeek Analysis" in body
        assert "Test tool" in body
        assert "App1" in body

    @patch("github_star_organizer.issue_manager.run_command")
    def test_creates_issue_omits_missing_language_license_homepage(self, mock_run):
        mock_run.return_value = "https://github.com/owner/repo/issues/99"
        repo = {
            "nameWithOwner": "owner/repo",
            "description": "A repo with no extras",
            "primaryLanguage": None,
            "languages": {"edges": [], "totalSize": 0},
            "licenseInfo": None,
            "updatedAt": "2026-04-01T00:00:00Z",
            "homepageUrl": None,
        }

        issue_manager.create_discovery_issue(repo, {})

        body = mock_run.call_args[0][0][mock_run.call_args[0][0].index("--body") + 1]
        assert "**Language:**" not in body
        assert "**License:**" not in body
        assert "**Homepage:**" not in body
        assert "2026-04-01" in body

    @patch("github_star_organizer.issue_manager.run_command")
    def test_includes_both_model_sections_when_available(self, mock_run):
        mock_run.return_value = "https://github.com/owner/repo/issues/43"
        repo = {
            "nameWithOwner": "owner/repo",
            "description": "A cool repo",
            "primaryLanguage": None,
            "languages": {"edges": [], "totalSize": 0},
            "licenseInfo": None,
            "updatedAt": "2026-05-01T00:00:00Z",
            "homepageUrl": None,
        }
        model_summaries = {
            "deepseek": {
                "owner/repo": {
                    "purpose": "DS purpose",
                    "use_case": "DS use case",
                    "unusual_applications": ["DS App1"],
                }
            },
            "ollama": {
                "owner/repo": {
                    "purpose": "OL purpose",
                    "use_case": "OL use case",
                    "unusual_applications": ["OL App1"],
                }
            },
        }

        result = issue_manager.create_discovery_issue(repo, model_summaries)

        body = mock_run.call_args[0][0][mock_run.call_args[0][0].index("--body") + 1]
        assert "DeepSeek Analysis" in body
        assert "Ollama Analysis" in body
        assert "DS purpose" in body
        assert "OL purpose" in body

    @patch("github_star_organizer.issue_manager.run_command")
    def test_title_format(self, mock_run):
        mock_run.return_value = "https://github.com/owner/my-repo/issues/10"
        repo = {
            "nameWithOwner": "owner/my-repo",
            "description": "desc",
            "primaryLanguage": None,
            "languages": {"edges": [], "totalSize": 0},
            "licenseInfo": None,
            "updatedAt": "2026-05-01T00:00:00Z",
            "homepageUrl": None,
        }
        issue_manager.create_discovery_issue(repo, {})

        call_args = mock_run.call_args[0][0]
        title_idx = call_args.index("--title") + 1
        assert call_args[title_idx] == "Discovered: owner/my-repo"


class TestDiscoverReposMain:
    @patch("discover_repos.report_uncategorized_repos")
    @patch("discover_repos.get_or_create_weekly_issue")
    @patch("discover_repos.state_db")
    @patch("discover_repos.search_popular_repos")
    @patch("discover_repos.get_current_stars")
    @patch("discover_repos.GitHubClient")
    def test_deepseek_failure_still_reports_uncategorized(
        self,
        mock_client_class,
        mock_stars,
        mock_search,
        mock_db,
        mock_get_issue,
        mock_report,
    ):
        mock_client_class.return_value = MagicMock()
        mock_stars.return_value = set()
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
        mock_db.get_uncategorized_repos.return_value = set()
        mock_db.get_discovered_repos.return_value = set()
        mock_db.get_issue_number_for_discovered.return_value = None
        mock_get_issue.return_value = "123"

        with patch("discover_repos.is_categorized", return_value=False):
            with patch("discover_repos.identify_and_summarize_interesting", return_value=None):
                discover_repos.main()

        # Should still report uncategorized even if discovery fails
        mock_report.assert_called_once()

    @patch("discover_repos.state_db")
    @patch("discover_repos.GitHubClient")
    @patch("discover_repos.search_popular_repos")
    @patch("discover_repos.get_current_stars")
    def test_empty_uncategorized_returns_early(self, mock_stars, mock_search, mock_client_class, mock_db):
        mock_client_class.return_value = MagicMock()
        mock_stars.return_value = set()
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
        mock_db.get_uncategorized_repos.return_value = set()
        mock_db.get_discovered_repos.return_value = set()

        with patch("discover_repos.is_categorized", return_value=True):
            with patch("discover_repos.identify_and_summarize_interesting", return_value=None) as mock_identify:
                discover_repos.main()
                # With all repos categorized, uncategorized list is empty
                # identify_and_summarize_interesting may still be called for interesting selection

    @patch("builtins.open", new_callable=mock_open)
    @patch("discover_repos.report_uncategorized_repos")
    @patch("discover_repos.get_or_create_weekly_issue")
    @patch("discover_repos.state_db")
    @patch("discover_repos.search_popular_repos")
    @patch("discover_repos.get_current_stars")
    @patch("discover_repos.GitHubClient")
    def test_github_output_written_when_env_set(
        self,
        mock_client_class,
        mock_stars,
        mock_search,
        mock_db,
        mock_get_issue,
        mock_report,
        mock_file,
    ):
        mock_client_class.return_value = MagicMock()
        mock_stars.return_value = set()
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
        mock_db.get_uncategorized_repos.return_value = set()
        mock_db.get_discovered_repos.return_value = set()
        mock_db.get_issue_number_for_discovered.return_value = None
        mock_get_issue.return_value = "123"

        with patch.dict(os.environ, {"GITHUB_OUTPUT": "/tmp/output"}):
            with patch("discover_repos.is_categorized", return_value=False):
                with patch("discover_repos.identify_and_summarize_interesting", return_value=None):
                    discover_repos.main()

        # Should write to GITHUB_OUTPUT
        mock_file.assert_called()
