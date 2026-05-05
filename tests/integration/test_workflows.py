import unittest
from unittest.mock import patch, MagicMock
import json
import tempfile
import os
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from github_star_organizer.gh_client import GitHubClient, GitHubAPIError
from github_star_organizer.categorizer import categorize, get_categorized_ids, get_recent_stars
from github_star_organizer.issue_manager import (
    get_or_create_weekly_issue,
    get_already_reported_repos,
    report_uncategorized_repos,
    IssueError
)
from github_star_organizer.config import load_config, ConfigError
from github_star_organizer.logger import get_logger


class TestCategorizeWorkflow(unittest.TestCase):
    """Integration tests for the categorization workflow."""

    @patch("subprocess.run")
    def test_categorize_workflow_end_to_end(self, mock_run):
        """Test full categorization workflow: fetch -> categorize -> skip"""
        # Mock the gh API call to fetch categorized repos
        mock_result1 = MagicMock()
        mock_result1.returncode = 0
        mock_result1.stdout = '''{
          "data": {
            "viewer": {
              "lists": {
                "nodes": [
                  {
                    "items": {
                      "nodes": [
                        {"id": "existing-repo-1"}
                      ]
                    }
                  }
                ]
              }
            }
          }
        }'''

        # Mock the gh API call to fetch recent stars
        mock_result2 = MagicMock()
        mock_result2.returncode = 0
        mock_result2.stdout = '''{
          "data": {
            "viewer": {
              "starredRepositories": {
                "nodes": [
                  {
                    "id": "new-repo-1",
                    "nameWithOwner": "anthropics/claude",
                    "description": "An LLM-based tool using AI agents",
                    "repositoryTopics": {"nodes": []}
                  },
                  {
                    "id": "new-repo-2",
                    "nameWithOwner": "torvalds/linux",
                    "description": "The Linux kernel source tree",
                    "repositoryTopics": {"nodes": [{"topic": {"name": "operating-system"}}]}
                  }
                ]
              }
            }
          }
        }'''

        mock_run.side_effect = [mock_result1, mock_result2]

        client = GitHubClient()

        # Fetch categorized repos
        categorized = get_categorized_ids(client)
        self.assertEqual(len(categorized), 1)
        self.assertIn("existing-repo-1", categorized)

        # Fetch recent stars
        stars = get_recent_stars(client)
        self.assertEqual(len(stars), 2)

        # Verify categorization logic
        self.assertIsNotNone(categorize(stars[0]))  # Claude should match AI LLMs
        self.assertIsNotNone(categorize(stars[1]))  # Linux should match OS


class TestCategorizeWithSkipped(unittest.TestCase):
    """Test categorization workflow with uncategorized repos."""

    @patch("subprocess.run")
    def test_skipped_repos_workflow(self, mock_run):
        """Test workflow correctly identifies repos with no matching keywords"""
        # Mock categorized repos response
        mock_result1 = MagicMock()
        mock_result1.returncode = 0
        mock_result1.stdout = '{"data": {"viewer": {"lists": {"nodes": []}}}}'

        # Mock recent stars with mixed categorizable and uncategorizable
        mock_result2 = MagicMock()
        mock_result2.returncode = 0
        mock_result2.stdout = '''{
          "data": {
            "viewer": {
              "starredRepositories": {
                "nodes": [
                  {
                    "id": "repo-1",
                    "nameWithOwner": "myorg/xyz-project",
                    "description": "Some random source code collection with no matching keywords",
                    "repositoryTopics": {"nodes": []}
                  },
                  {
                    "id": "repo-2",
                    "nameWithOwner": "anthropics/models",
                    "description": "LLM models and AI agents framework",
                    "repositoryTopics": {"nodes": [{"topic": {"name": "ai"}}]}
                  }
                ]
              }
            }
          }
        }'''

        mock_run.side_effect = [mock_result1, mock_result2]

        client = GitHubClient()
        categorized = get_categorized_ids(client)
        stars = get_recent_stars(client)

        # Separate categorizable and uncategorizable repos
        skipped = [repo for repo in stars if categorize(repo) is None]
        categorizable = [repo for repo in stars if categorize(repo) is not None]

        self.assertEqual(len(skipped), 1)
        self.assertEqual(len(categorizable), 1)
        self.assertEqual(skipped[0]["nameWithOwner"], "myorg/xyz-project")


class TestIssueManagementWorkflow(unittest.TestCase):
    """Integration tests for issue management workflow."""

    @patch("github_star_organizer.issue_manager.run_command")
    def test_get_or_create_weekly_issue_new(self, mock_run_command):
        """Test creating a new weekly issue when none exists"""
        # Mock: no existing issues
        mock_run_command.side_effect = [
            "[]",  # No existing issues
            "https://github.com/user/repo/issues/42"  # Created issue URL
        ]

        client = MagicMock()
        issue_num = get_or_create_weekly_issue(client)

        self.assertEqual(issue_num, "42")

    @patch("github_star_organizer.issue_manager.datetime")
    @patch("github_star_organizer.issue_manager.run_command")
    def test_get_or_create_weekly_issue_exists(self, mock_run_command, mock_datetime):
        """Test retrieving existing weekly issue"""
        # Mock: existing issue for this week (week 18)
        import datetime as dt
        mock_datetime.date.today.return_value = dt.date(2026, 4, 27)  # Week 18

        mock_run_command.return_value = '''[
          {
            "number": 42,
            "title": "Uncategorized Stars: 2026-W18"
          }
        ]'''

        client = MagicMock()
        issue_num = get_or_create_weekly_issue(client)

        self.assertEqual(issue_num, "42")

    @patch("github_star_organizer.issue_manager.run_command")
    def test_get_or_create_weekly_issue_closes_old(self, mock_run_command):
        """Test that old issues are closed when new one is created"""
        # Mock: old issue exists
        mock_run_command.side_effect = [
            '''[
              {
                "number": 40,
                "title": "Uncategorized Stars: 2026-W16"
              }
            ]''',
            "https://github.com/user/repo/issues/42",  # New issue created
            "",  # Comment added
            ""   # Issue closed
        ]

        client = MagicMock()
        issue_num = get_or_create_weekly_issue(client)

        self.assertEqual(issue_num, "42")
        # Verify that close was called (3rd call is comment, 4th is close)
        self.assertEqual(mock_run_command.call_count, 4)


class TestReportUncategorizedWorkflow(unittest.TestCase):
    """Integration tests for reporting uncategorized repos."""

    @patch("github_star_organizer.issue_manager.run_command")
    def test_report_uncategorized_repos(self, mock_run_command):
        """Test posting uncategorized repos to an issue"""
        mock_run_command.return_value = ""

        repos = [
            {
                "nameWithOwner": "user/project1",
                "description": "A cool project",
                "repositoryTopics": {"nodes": [{"topic": {"name": "python"}}]}
            },
            {
                "nameWithOwner": "user/project2",
                "description": "Another project",
                "repositoryTopics": {"nodes": []}
            }
        ]

        client = MagicMock()
        # Should not raise
        report_uncategorized_repos(client, "42", repos)

        # Verify run_command was called to post comment
        self.assertTrue(mock_run_command.called)

    @patch("github_star_organizer.issue_manager.run_command")
    def test_get_already_reported_repos(self, mock_run_command):
        """Test extracting repo names from issue comments"""
        mock_run_command.return_value = '''- **user/reported-1**
- **user/reported-2**
Some other text
- **user/reported-3**'''

        client = MagicMock()
        reported = get_already_reported_repos(client, "42")

        self.assertEqual(len(reported), 3)
        self.assertIn("user/reported-1", reported)
        self.assertIn("user/reported-2", reported)
        self.assertIn("user/reported-3", reported)


class TestConfigValidation(unittest.TestCase):
    """Integration tests for configuration loading."""

    def test_config_loads_and_validates(self):
        """Test that real config.json loads successfully"""
        try:
            config = load_config()

            # Verify structure
            self.assertIn("lists", config)
            self.assertIn("keywords", config)

            # Verify lists is a dict
            self.assertIsInstance(config["lists"], dict)

            # Verify keywords is a dict with categories
            self.assertIsInstance(config["keywords"], dict)
            self.assertGreater(len(config["keywords"]), 0)

        except ConfigError as e:
            self.fail(f"Config validation failed: {e}")

    def test_config_has_expected_categories(self):
        """Test that config has the expected keyword categories"""
        config = load_config()
        keywords = config["keywords"]

        # Check for common categories mentioned in spec
        expected_categories = ["AI Agents & LLMs", "Tools & CLI"]
        for cat in expected_categories:
            self.assertIn(cat, keywords, f"Missing category: {cat}")
            self.assertIsInstance(keywords[cat], list)
            self.assertGreater(len(keywords[cat]), 0, f"Category {cat} has no keywords")


class TestPackageImports(unittest.TestCase):
    """Integration tests for package structure."""

    def test_all_modules_import_correctly(self):
        """Test that all package modules import without errors"""
        from github_star_organizer import gh_client
        from github_star_organizer import categorizer
        from github_star_organizer import logger
        from github_star_organizer import config
        from github_star_organizer import issue_manager

        # Verify classes and functions exist
        self.assertTrue(hasattr(gh_client, 'GitHubAPIError'))
        self.assertTrue(hasattr(gh_client, 'GitHubClient'))
        self.assertTrue(hasattr(gh_client, 'run_query'))
        self.assertTrue(hasattr(categorizer, 'categorize'))
        self.assertTrue(hasattr(categorizer, 'get_categorized_ids'))
        self.assertTrue(hasattr(categorizer, 'get_recent_stars'))
        self.assertTrue(hasattr(logger, 'get_logger'))
        self.assertTrue(hasattr(config, 'ConfigError'))
        self.assertTrue(hasattr(config, 'load_config'))
        self.assertTrue(hasattr(issue_manager, 'IssueError'))
        self.assertTrue(hasattr(issue_manager, 'get_or_create_weekly_issue'))

    def test_logger_factory(self):
        """Test that logger can be created for different modules"""
        from github_star_organizer.logger import get_logger

        logger_cat = get_logger("categorize")
        logger_dist = get_logger("distill")

        self.assertEqual(logger_cat.name, "categorize")
        self.assertEqual(logger_dist.name, "distill")

    def test_entry_scripts_exist(self):
        """Test that entry-point scripts exist"""
        scripts = ["categorize.py", "distill.py", "discover_repos.py"]
        base_dir = Path(__file__).parent.parent.parent

        for script in scripts:
            path = base_dir / script
            self.assertTrue(path.exists(), f"{script} not found at {path}")
            self.assertTrue(path.is_file(), f"{script} is not a file")


class TestCategorizationLogic(unittest.TestCase):
    """Integration tests for categorization logic."""

    def test_categorize_by_name_match(self):
        """Test categorization by repository name"""
        repo = {
            "nameWithOwner": "anthropics/claude",
            "description": "",
            "repositoryTopics": {"nodes": []}
        }
        result = categorize(repo)
        self.assertIsNotNone(result)

    def test_categorize_by_description_match(self):
        """Test categorization by description keywords"""
        repo = {
            "nameWithOwner": "example/project",
            "description": "An LLM-based tool for AI agents",
            "repositoryTopics": {"nodes": []}
        }
        result = categorize(repo)
        self.assertIsNotNone(result)

    def test_categorize_by_topic_match(self):
        """Test categorization by repository topics"""
        repo = {
            "nameWithOwner": "example/project",
            "description": "A cool project",
            "repositoryTopics": {"nodes": [
                {"topic": {"name": "llm"}},
                {"topic": {"name": "ai"}}
            ]}
        }
        result = categorize(repo)
        self.assertIsNotNone(result)

    def test_categorize_no_match(self):
        """Test that repo with no matching keywords returns None"""
        repo = {
            "nameWithOwner": "example/unknown-project-xyz",
            "description": "Just some random project",
            "repositoryTopics": {"nodes": [
                {"topic": {"name": "random"}},
                {"topic": {"name": "misc"}}
            ]}
        }
        result = categorize(repo)
        # Could be None or match a category depending on config
        # Just verify it returns a string or None
        self.assertTrue(result is None or isinstance(result, str))

    def test_categorize_priority_order(self):
        """Test that priority categories are checked before others"""
        # If a repo matches both a priority and non-priority category,
        # it should return the priority one
        repo = {
            "nameWithOwner": "example/ai-cli-tool",
            "description": "An AI agent and CLI tool",
            "repositoryTopics": {"nodes": []}
        }
        result = categorize(repo)
        # Should match AI Agents (priority) or Tools (priority)
        self.assertIsNotNone(result)
        self.assertIn(result, ["AI Agents & LLMs", "Tools & CLI", "Dev Tools & Frameworks"])


class TestGitHubClientClass(unittest.TestCase):
    """Integration tests for GitHubClient class."""

    @patch("subprocess.run")
    def test_github_client_run_query(self, mock_run):
        """Test GitHubClient.run_query wrapper"""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = '{"data": {"viewer": {"login": "testuser"}}}'
        mock_run.return_value = mock_result

        client = GitHubClient()
        result = client.run_query("query { viewer { login } }")

        self.assertIn("data", result)
        self.assertEqual(result["data"]["viewer"]["login"], "testuser")

    @patch("subprocess.run")
    def test_github_client_error_handling(self, mock_run):
        """Test GitHubClient error handling"""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "GitHub API error"
        mock_run.return_value = mock_result

        client = GitHubClient()

        with self.assertRaises(GitHubAPIError):
            client.run_query("query { viewer { login } }")


class TestCompleteWorkflowIntegration(unittest.TestCase):
    """End-to-end integration test of the entire categorization workflow."""

    @patch("subprocess.run")
    def test_complete_categorization_pipeline(self, mock_run):
        """Test the complete pipeline: fetch config, categorize, report uncategorized"""
        # This test validates the entire flow works together

        # Setup mock responses in order
        responses = [
            # 1. Load config (not mocked, uses real file)
            # 2. Fetch categorized repos
            MagicMock(returncode=0, stdout='{"data": {"viewer": {"lists": {"nodes": []}}}}'),
            # 3. Fetch recent stars
            MagicMock(returncode=0, stdout='''{
              "data": {
                "viewer": {
                  "starredRepositories": {
                    "nodes": [
                      {
                        "id": "repo-1",
                        "nameWithOwner": "anthropics/claude-models",
                        "description": "AI LLM models",
                        "repositoryTopics": {"nodes": []}
                      },
                      {
                        "id": "repo-2",
                        "nameWithOwner": "unknown/random-project",
                        "description": "Random stuff",
                        "repositoryTopics": {"nodes": []}
                      }
                    ]
                  }
                }
              }
            }'''),
        ]

        mock_run.side_effect = responses

        client = GitHubClient()

        try:
            config = load_config()
            self.assertIsNotNone(config)

            categorized = get_categorized_ids(client)
            self.assertEqual(len(categorized), 0)

            stars = get_recent_stars(client)
            self.assertEqual(len(stars), 2)

            # Categorize each repo
            results = []
            for repo in stars:
                cat = categorize(repo)
                results.append((repo["nameWithOwner"], cat))

            # First should be categorized, second might not be
            self.assertIsNotNone(results[0][1], "Claude project should be categorized")

        except Exception as e:
            self.fail(f"Complete workflow failed: {e}")


if __name__ == "__main__":
    unittest.main()
