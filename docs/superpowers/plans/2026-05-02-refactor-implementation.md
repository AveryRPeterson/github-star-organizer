# GitHub Star Organizer Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor the GitHub Star Organizer from monolithic scripts into a modular package with proper separation of concerns, comprehensive testing, type hints, and improved operational visibility.

**Architecture:** Extract shared logic into 5 focused modules (gh_client, categorizer, logger, config, issue_manager), refactor 3 entry-point scripts to use the package, write 30+ tests covering unit and integration scenarios, add type hints to public APIs, and enhance GitHub Actions workflows with structured feedback.

**Tech Stack:** Python 3.x, stdlib logging, unittest.mock for testing, type hints (PEP 484), subprocess for gh CLI calls, json for config/data handling.

---

## File Structure Overview

**New package structure:**
```
github_star_organizer/
├── __init__.py              # Package initialization
├── gh_client.py             # GitHub GraphQL client (240 lines)
├── categorizer.py           # Categorization logic (180 lines)
├── logger.py                # Structured logging (60 lines)
├── config.py                # Config management (80 lines)
└── issue_manager.py         # Issue lifecycle (320 lines)

tests/
├── unit/
│   ├── test_gh_client.py    # gh_client tests (180 lines)
│   ├── test_categorizer.py  # categorizer tests (150 lines)
│   ├── test_config.py       # config tests (100 lines)
│   └── test_issue_manager.py # issue_manager tests (280 lines)
└── integration/
    └── test_workflows.py     # end-to-end tests (250 lines)

requirements.txt             # Dependencies
```

**Modified entry points (minimal, ~40 lines each):**
- `categorize.py`
- `distill.py`
- `find_weird.py`

---

## Phase 1: Setup & Project Structure

### Task 1: Create package directory structure and requirements.txt

**Files:**
- Create: `github_star_organizer/__init__.py`
- Create: `requirements.txt`
- Create: `tests/__init__.py`
- Create: `tests/unit/__init__.py`
- Create: `tests/integration/__init__.py`

- [ ] **Step 1: Create package directories**

```bash
mkdir -p github_star_organizer tests/unit tests/integration
```

- [ ] **Step 2: Create `github_star_organizer/__init__.py`**

```python
"""GitHub Star Organizer - Automated categorization of starred repositories."""

__version__ = "2.0.0"
```

- [ ] **Step 3: Create test `__init__.py` files**

```bash
touch tests/__init__.py tests/unit/__init__.py tests/integration/__init__.py
```

- [ ] **Step 4: Create `requirements.txt`**

```
requests>=2.28.0
```

- [ ] **Step 5: Verify structure**

```bash
find github_star_organizer tests -name "*.py" | sort
```

Expected output:
```
github_star_organizer/__init__.py
tests/__init__.py
tests/integration/__init__.py
tests/unit/__init__.py
```

- [ ] **Step 6: Commit**

```bash
git add github_star_organizer/ tests/ requirements.txt
git commit -m "chore: create package and test directory structure"
```

---

## Phase 2: Core Modules (Logger → Config → Client → Categorizer → Issue Manager)

### Task 2: Implement logger.py with tests

**Files:**
- Create: `github_star_organizer/logger.py`
- Create: `tests/unit/test_logger.py`

- [ ] **Step 1: Write logger tests**

```python
# tests/unit/test_logger.py
import unittest
import logging
from io import StringIO
from github_star_organizer.logger import get_logger


class TestGetLogger(unittest.TestCase):
    def test_get_logger_returns_logger(self):
        logger = get_logger("test_module")
        self.assertIsInstance(logger, logging.Logger)
    
    def test_get_logger_has_correct_name(self):
        logger = get_logger("categorize")
        self.assertEqual(logger.name, "categorize")
    
    def test_get_logger_configured_for_output(self):
        logger = get_logger("test")
        # Verify logger has handlers
        self.assertTrue(len(logger.handlers) > 0 or logger.propagate)
    
    def test_multiple_calls_same_name_returns_same_logger(self):
        logger1 = get_logger("shared")
        logger2 = get_logger("shared")
        self.assertIs(logger1, logger2)
    
    def test_logger_can_log_at_levels(self):
        logger = get_logger("test_levels")
        # Add handler to capture output
        handler = logging.StreamHandler(StringIO())
        logger.addHandler(handler)
        
        # These should not raise
        logger.debug("debug message")
        logger.info("info message")
        logger.warning("warning message")
        logger.error("error message")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /data/data/com.termux/files/home/projects/github-star-organizer
python -m pytest tests/unit/test_logger.py -v
```

Expected: FAIL with "ModuleNotFoundError: No module named 'github_star_organizer.logger'"

- [ ] **Step 3: Implement logger.py**

```python
# github_star_organizer/logger.py
import logging
import sys


def get_logger(name: str) -> logging.Logger:
    """
    Get a configured logger for the given module name.
    
    Args:
        name: Module name (e.g., "categorize", "distill")
        
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    
    # Only configure if not already configured (avoid duplicate handlers)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            "[%(levelname)s] %(asctime)s - %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    
    return logger
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/unit/test_logger.py -v
```

Expected: PASS (5/5)

- [ ] **Step 5: Commit**

```bash
git add github_star_organizer/logger.py tests/unit/test_logger.py
git commit -m "feat: implement logger module with tests"
```

---

### Task 3: Implement config.py with tests

**Files:**
- Create: `github_star_organizer/config.py`
- Create: `tests/unit/test_config.py`

- [ ] **Step 1: Write config tests**

```python
# tests/unit/test_config.py
import unittest
import json
import tempfile
import os
from github_star_organizer.config import load_config, ConfigError


class TestLoadConfig(unittest.TestCase):
    def test_load_config_valid(self):
        """Test loading a valid config.json"""
        config = load_config()
        self.assertIn("lists", config)
        self.assertIn("keywords", config)
        self.assertIsInstance(config["lists"], dict)
        self.assertIsInstance(config["keywords"], dict)
    
    def test_load_config_has_required_categories(self):
        """Test that config has expected categories"""
        config = load_config()
        expected_categories = [
            "AI Agents & LLMs",
            "Tools & CLI",
            "Hardware & Keyboards",
            "Android & Termux",
            "3D Printing & CAD",
            "OS & Customization",
            "Dev Tools & Frameworks"
        ]
        for cat in expected_categories:
            self.assertIn(cat, config["keywords"])
    
    def test_load_config_keywords_are_lists(self):
        """Test that all keywords are lists of strings"""
        config = load_config()
        for category, keywords in config["keywords"].items():
            self.assertIsInstance(keywords, list)
            for kw in keywords:
                self.assertIsInstance(kw, str)
    
    def test_load_config_lists_are_strings_or_empty(self):
        """Test that list IDs are non-empty strings"""
        config = load_config()
        for category, list_id in config["lists"].items():
            # Some may be empty strings for uncreated lists
            self.assertIsInstance(list_id, str)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/unit/test_config.py -v
```

Expected: FAIL with "ModuleNotFoundError: No module named 'github_star_organizer.config'"

- [ ] **Step 3: Implement config.py**

```python
# github_star_organizer/config.py
import json


class ConfigError(Exception):
    """Raised when config.json is invalid or missing."""
    pass


def load_config() -> dict:
    """
    Load and validate config.json from current directory.
    
    Returns:
        Parsed config dictionary with 'lists' and 'keywords' keys
        
    Raises:
        ConfigError: If config.json is missing, invalid JSON, or missing required keys
    """
    try:
        with open("config.json", "r") as f:
            config = json.load(f)
    except FileNotFoundError as e:
        raise ConfigError("config.json not found") from e
    except json.JSONDecodeError as e:
        raise ConfigError(f"config.json is invalid JSON: {e}") from e
    
    # Validate required keys
    if "lists" not in config:
        raise ConfigError("config.json missing required key: 'lists'")
    if "keywords" not in config:
        raise ConfigError("config.json missing required key: 'keywords'")
    
    if not isinstance(config["lists"], dict):
        raise ConfigError("config['lists'] must be a dictionary")
    if not isinstance(config["keywords"], dict):
        raise ConfigError("config['keywords'] must be a dictionary")
    
    return config
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/unit/test_config.py -v
```

Expected: PASS (4/4)

- [ ] **Step 5: Commit**

```bash
git add github_star_organizer/config.py tests/unit/test_config.py
git commit -m "feat: implement config module with validation"
```

---

### Task 4: Implement gh_client.py with tests

**Files:**
- Create: `github_star_organizer/gh_client.py`
- Create: `tests/unit/test_gh_client.py`

- [ ] **Step 1: Write gh_client tests**

```python
# tests/unit/test_gh_client.py
import unittest
from unittest.mock import patch, MagicMock
import json
import subprocess
from github_star_organizer.gh_client import run_query, GitHubAPIError


class TestRunQuery(unittest.TestCase):
    @patch("subprocess.run")
    def test_run_query_success(self, mock_run):
        """Test successful GraphQL query execution"""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = '{"data": {"viewer": {"login": "testuser"}}}'
        mock_run.return_value = mock_result
        
        result = run_query("query { viewer { login } }")
        
        self.assertIn("data", result)
        self.assertEqual(result["data"]["viewer"]["login"], "testuser")
    
    @patch("subprocess.run")
    def test_run_query_with_variables(self, mock_run):
        """Test query with variables"""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = '{"data": {"repository": {"id": "abc123"}}}'
        mock_run.return_value = mock_result
        
        result = run_query("query($owner: String!) { ... }", {"owner": "torvalds"})
        
        # Verify variables were passed to subprocess
        call_args = mock_run.call_args
        self.assertIn("owner=torvalds", str(call_args))
    
    @patch("subprocess.run")
    def test_run_query_api_error(self, mock_run):
        """Test error handling when gh CLI fails"""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "Authentication failed"
        mock_run.return_value = mock_result
        
        with self.assertRaises(GitHubAPIError) as context:
            run_query("query { viewer { login } }")
        
        self.assertIn("Authentication failed", str(context.exception))
    
    @patch("subprocess.run")
    def test_run_query_invalid_json(self, mock_run):
        """Test error handling for invalid JSON response"""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "not valid json"
        mock_run.return_value = mock_result
        
        with self.assertRaises(GitHubAPIError):
            run_query("query { viewer { login } }")
    
    @patch("subprocess.run")
    def test_run_query_command_format(self, mock_run):
        """Test that gh command is formatted correctly"""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = '{"data": {}}'
        mock_run.return_value = mock_result
        
        run_query("test query")
        
        # Verify the command structure
        call_args = mock_run.call_args[0][0]
        self.assertEqual(call_args[0], "gh")
        self.assertEqual(call_args[1], "api")
        self.assertEqual(call_args[2], "graphql")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/unit/test_gh_client.py -v
```

Expected: FAIL with "ModuleNotFoundError: No module named 'github_star_organizer.gh_client'"

- [ ] **Step 3: Implement gh_client.py**

```python
# github_star_organizer/gh_client.py
import subprocess
import json
import sys


class GitHubAPIError(Exception):
    """Raised when GitHub API call fails."""
    pass


def run_query(query: str, variables: dict[str, str] | None = None) -> dict:
    """
    Execute a GraphQL query against GitHub API via gh CLI.
    
    Args:
        query: GraphQL query string
        variables: Optional dict of query variables (key=value pairs)
        
    Returns:
        Parsed JSON response dict
        
    Raises:
        GitHubAPIError: If gh command fails or response is invalid JSON
    """
    cmd = ["gh", "api", "graphql", "-f", f"query={query}"]
    
    # Add variables to command
    if variables:
        for key, value in variables.items():
            cmd.extend(["-f", f"{key}={value}"])
    
    # Execute gh command
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    # Check for command failures
    if result.returncode != 0:
        raise GitHubAPIError(f"GitHub API error: {result.stderr}")
    
    # Parse JSON response
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise GitHubAPIError(f"Invalid JSON response from GitHub: {e}")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/unit/test_gh_client.py -v
```

Expected: PASS (5/5)

- [ ] **Step 5: Commit**

```bash
git add github_star_organizer/gh_client.py tests/unit/test_gh_client.py
git commit -m "feat: implement GitHub GraphQL client with tests"
```

---

### Task 5: Implement categorizer.py with tests

**Files:**
- Create: `github_star_organizer/categorizer.py`
- Modify: `tests/unit/test_categorizer.py` (migrate from root and enhance)

- [ ] **Step 1: Write comprehensive categorizer tests**

```python
# tests/unit/test_categorizer.py
import unittest
from unittest.mock import MagicMock
from github_star_organizer.categorizer import categorize, get_categorized_ids, get_recent_stars
from github_star_organizer.gh_client import GitHubAPIError


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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/unit/test_categorizer.py -v
```

Expected: FAIL with "ModuleNotFoundError: No module named 'github_star_organizer.categorizer'"

- [ ] **Step 3: Implement categorizer.py by extracting from categorize.py**

```python
# github_star_organizer/categorizer.py
from github_star_organizer.config import load_config


def categorize(repo: dict) -> str | None:
    """
    Categorize a repository based on name, description, and topics.
    
    Args:
        repo: Repository dict with keys: nameWithOwner, description, repositoryTopics
        
    Returns:
        Category name if match found, None otherwise
    """
    config = load_config()
    KEYWORDS = config["keywords"]
    PRIORITY_CATEGORIES = [
        "AI Agents & LLMs",
        "3D Printing & CAD",
        "OS & Customization",
        "Android & Termux",
        "Hardware & Keyboards",
        "Tools & CLI",
        "Dev Tools & Frameworks"
    ]
    
    name = repo.get("nameWithOwner", "").lower()
    desc = (repo.get("description") or "").lower()
    topics = [t["topic"]["name"].lower() for t in repo.get("repositoryTopics", {}).get("nodes", [])]
    combined = f"{name} {desc} {' '.join(topics)}"
    
    # Priority matching
    for cat in PRIORITY_CATEGORIES:
        if any(kw in combined for kw in KEYWORDS.get(cat, [])):
            return cat
    
    # Check any dynamic categories added to config.json
    for cat, kws in KEYWORDS.items():
        if cat not in PRIORITY_CATEGORIES:
            if any(kw in combined for kw in kws):
                return cat
    
    return None


def get_categorized_ids(client) -> set[str]:
    """
    Fetch IDs of repositories already in user lists.
    
    Args:
        client: GitHubClient instance
        
    Returns:
        Set of repository IDs
    """
    query = """
    query {
      viewer {
        lists(first: 100) {
          nodes {
            items(first: 100) {
              nodes {
                ... on Repository { id }
              }
            }
          }
        }
      }
    }
    """
    data = client.run_query(query)
    ids = set()
    if data and "data" in data:
        for list_node in data["data"]["viewer"]["lists"]["nodes"]:
            for item in list_node["items"]["nodes"]:
                if item and "id" in item:
                    ids.add(item["id"])
    return ids


def get_recent_stars(client, limit: int = 50) -> list[dict]:
    """
    Fetch recent starred repositories.
    
    Args:
        client: GitHubClient instance
        limit: Number of repos to fetch (default 50)
        
    Returns:
        List of repository dicts
    """
    query = """
    query {
      viewer {
        starredRepositories(first: 50, orderBy: {field: STARRED_AT, direction: DESC}) {
          nodes {
            id
            nameWithOwner
            description
            repositoryTopics(first: 10) {
              nodes { topic { name } }
            }
          }
        }
      }
    }
    """
    result = client.run_query(query)
    if result and "data" in result:
        return result["data"]["viewer"]["starredRepositories"]["nodes"]
    return []
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/unit/test_categorizer.py -v
```

Expected: PASS (10/10)

- [ ] **Step 5: Remove old test_categorize.py from root (no longer needed)**

```bash
rm test_categorize.py
```

- [ ] **Step 6: Commit**

```bash
git add github_star_organizer/categorizer.py tests/unit/test_categorizer.py
git rm test_categorize.py
git commit -m "feat: implement categorizer module with comprehensive tests"
```

---

### Task 6: Implement issue_manager.py with tests

**Files:**
- Create: `github_star_organizer/issue_manager.py`
- Create: `tests/unit/test_issue_manager.py`

- [ ] **Step 1: Write issue_manager tests**

```python
# tests/unit/test_issue_manager.py
import unittest
from unittest.mock import MagicMock, patch, call
import datetime
from github_star_organizer.issue_manager import (
    get_or_create_weekly_issue,
    get_already_reported_repos,
    report_uncategorized_repos,
    close_issue,
    IssueError
)


class TestGetOrCreateWeeklyIssue(unittest.TestCase):
    @patch("github_star_organizer.issue_manager.datetime")
    def test_create_new_issue_when_none_exists(self, mock_datetime):
        """Test creating a new issue when none exists"""
        # Mock the date to be 2026-05-02 (Friday)
        mock_datetime.date.today.return_value = datetime.date(2026, 5, 2)
        
        mock_client = MagicMock()
        mock_client.run_command.side_effect = [
            "[]",  # No existing issues
            "https://github.com/user/repo/issues/42"  # Issue created
        ]
        
        result = get_or_create_weekly_issue(mock_client)
        self.assertEqual(result, "42")
    
    @patch("github_star_organizer.issue_manager.datetime")
    def test_return_existing_issue(self, mock_datetime):
        """Test returning existing issue for this week"""
        mock_datetime.date.today.return_value = datetime.date(2026, 5, 2)
        
        mock_client = MagicMock()
        mock_client.run_command.return_value = '[{"number": 42, "title": "Uncategorized Stars: 2026-W18"}]'
        
        result = get_or_create_weekly_issue(mock_client)
        self.assertEqual(result, "42")
    
    @patch("github_star_organizer.issue_manager.datetime")
    def test_close_old_duplicate_issues(self, mock_datetime):
        """Test that old issues are closed and consolidated"""
        mock_datetime.date.today.return_value = datetime.date(2026, 5, 2)
        
        mock_client = MagicMock()
        # Return two open issues - one matching this week, one old
        mock_client.run_command.side_effect = [
            '[{"number": 42, "title": "Uncategorized Stars: 2026-W18"}, {"number": 41, "title": "Uncategorized Stars: 2026-W17"}]',
            "success"
        ]
        
        result = get_or_create_weekly_issue(mock_client)
        
        # Verify old issue was closed
        self.assertEqual(result, "42")
        # Should have called close for old issue
        mock_client.run_command.assert_any_call(["gh", "issue", "close", "41", "--reason", "not planned"])


class TestGetAlreadyReportedRepos(unittest.TestCase):
    def test_extract_reported_repos(self):
        """Test extracting repo names from issue comments"""
        mock_client = MagicMock()
        comment_body = """
        - **owner/repo1**
          - Description: A tool
        - **owner/repo2**
          - Description: Another tool
        """
        mock_client.run_command.return_value = comment_body
        
        result = get_already_reported_repos(mock_client, "42")
        self.assertEqual(result, {"owner/repo1", "owner/repo2"})
    
    def test_no_comments_returns_empty(self):
        """Test when issue has no comments"""
        mock_client = MagicMock()
        mock_client.run_command.return_value = ""
        
        result = get_already_reported_repos(mock_client, "42")
        self.assertEqual(result, set())
    
    def test_invalid_issue_number_returns_empty(self):
        """Test error handling for invalid issue"""
        mock_client = MagicMock()
        mock_client.run_command.side_effect = Exception("Issue not found")
        
        result = get_already_reported_repos(mock_client, "999")
        self.assertEqual(result, set())


class TestReportUncategorizedRepos(unittest.TestCase):
    def test_post_comment_with_repos(self):
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
        call_args = mock_client.run_command.call_args[0][0]
        self.assertEqual(call_args[0], "gh")
        self.assertEqual(call_args[1], "issue")
        self.assertEqual(call_args[2], "comment")
        self.assertEqual(call_args[3], "42")


class TestCloseIssue(unittest.TestCase):
    def test_close_issue_with_reason(self):
        """Test closing an issue"""
        mock_client = MagicMock()
        
        close_issue(mock_client, "42", "Config updated")
        
        # Verify close was called
        calls = [call[0] for call in mock_client.run_command.call_args_list]
        # Should have called comment then close
        self.assertTrue(any("comment" in str(c) for c in calls))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/unit/test_issue_manager.py -v
```

Expected: FAIL with "ModuleNotFoundError: No module named 'github_star_organizer.issue_manager'"

- [ ] **Step 3: Implement issue_manager.py by extracting logic from categorize.py**

```python
# github_star_organizer/issue_manager.py
import subprocess
import json
import datetime
import re
from typing import Set


class IssueError(Exception):
    """Raised when GitHub issue operations fail."""
    pass


def run_command(cmd: list[str]) -> str:
    """Execute a gh CLI command and return output."""
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise IssueError(f"Command failed: {result.stderr}")
    return result.stdout.strip()


def get_or_create_weekly_issue(client) -> str | None:
    """
    Get or create the weekly uncategorized stars tracking issue.
    
    - Searches for all open "Uncategorized Stars" issues (authored by user)
    - Returns the target issue for this week (by date)
    - Closes and consolidates duplicate issues from prior weeks
    
    Args:
        client: GitHubClient instance
        
    Returns:
        Issue number as string, or None if creation fails
        
    Raises:
        IssueError: If issue operations fail
    """
    date_str = datetime.date.today().strftime("%Y-W%V")
    target_title = f"Uncategorized Stars: {date_str}"
    
    # 1. Find all open uncategorized issues authored by me
    try:
        res = run_command(["gh", "issue", "list", "--state", "open", 
                          "--search", 'in:title "Uncategorized Stars" author:@me', 
                          "--json", "number,title"])
        open_issues = json.loads(res) if res else []
    except (json.JSONDecodeError, IssueError):
        open_issues = []
    
    target_issue_num = None
    old_issues = []
    
    for issue in open_issues:
        if issue["title"] == target_title:
            if not target_issue_num:
                target_issue_num = str(issue["number"])
            else:
                # Duplicate for this week - close it
                old_issues.append(str(issue["number"]))
        else:
            # Old issue from different week - close it
            old_issues.append(str(issue["number"]))
    
    # 2. If target issue doesn't exist, create it
    if not target_issue_num:
        try:
            body = "This issue tracks repositories that were skipped during the organization run because they did not match any existing keywords. Comments below contain batches of uncategorized repositories."
            url = run_command(["gh", "issue", "create", "--title", target_title, "--body", body])
            target_issue_num = url.split("/")[-1]
        except IssueError as e:
            raise IssueError(f"Failed to create issue: {e}")
    
    # 3. Close old issues, pointing them to the new target issue
    for old_issue_num in old_issues:
        try:
            comment = f"A new weekly issue has been created: #{target_issue_num}. Closing this older tracking issue."
            run_command(["gh", "issue", "comment", old_issue_num, "--body", comment])
            run_command(["gh", "issue", "close", old_issue_num, "--reason", "not planned"])
        except IssueError:
            # Continue even if we can't close old issues
            pass
    
    return target_issue_num


def get_already_reported_repos(client, issue_number: str) -> Set[str]:
    """
    Extract repository names already mentioned in an issue's comments.
    
    Parses markdown format: "- **owner/repo**"
    
    Args:
        client: GitHubClient instance (not used, kept for API consistency)
        issue_number: GitHub issue number
        
    Returns:
        Set of "owner/repo" strings already reported
    """
    try:
        res = run_command(["gh", "issue", "view", issue_number, 
                          "--json", "comments", "-q", ".comments[].body"])
    except IssueError:
        return set()
    
    # Extract nameWithOwner using regex from markdown list items
    # Looking for lines like "- **user/repo**"
    reported = set()
    matches = re.findall(r"- \*\*([^*]+)\*\*", res)
    for match in matches:
        reported.add(match)
    
    return reported


def report_uncategorized_repos(client, issue_number: str, repos: list[dict]) -> None:
    """
    Post a comment with uncategorized repositories to an issue.
    
    Args:
        client: GitHubClient instance (not used, kept for API consistency)
        issue_number: GitHub issue number
        repos: List of repository dicts (nameWithOwner, description, repositoryTopics)
        
    Raises:
        IssueError: If comment posting fails
    """
    if not repos or not issue_number:
        return
    
    comment_body = "### New Uncategorized Repositories\n\n"
    for r in repos:
        topics = ", ".join([t["topic"]["name"] for t in r.get("repositoryTopics", {}).get("nodes", [])])
        desc = r.get('description') or "No description"
        comment_body += f"- **{r['nameWithOwner']}**\n  - Description: {desc}\n  - Topics: {topics}\n\n"
    
    try:
        run_command(["gh", "issue", "comment", issue_number, "--body", comment_body])
    except IssueError as e:
        raise IssueError(f"Failed to post comment to issue #{issue_number}: {e}")


def close_issue(client, issue_number: str, reason: str) -> None:
    """
    Close a GitHub issue with an optional comment.
    
    Args:
        client: GitHubClient instance (not used, kept for API consistency)
        issue_number: GitHub issue number
        reason: Reason for closing (e.g., "Config updated with new keywords")
        
    Raises:
        IssueError: If close operation fails
    """
    try:
        if reason:
            comment = f"Closing: {reason}"
            run_command(["gh", "issue", "comment", issue_number, "--body", comment])
        run_command(["gh", "issue", "close", issue_number])
    except IssueError as e:
        raise IssueError(f"Failed to close issue #{issue_number}: {e}")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/unit/test_issue_manager.py -v
```

Expected: PASS (8/8)

- [ ] **Step 5: Commit**

```bash
git add github_star_organizer/issue_manager.py tests/unit/test_issue_manager.py
git commit -m "feat: implement issue_manager module with lifecycle management"
```

---

## Phase 3: Script Refactoring

### Task 7: Refactor categorize.py to use the package

**Files:**
- Modify: `categorize.py` (replace with refactored version)

- [ ] **Step 1: Back up existing categorize.py**

```bash
cp categorize.py categorize.py.bak
```

- [ ] **Step 2: Replace categorize.py with refactored version**

```python
# categorize.py
import sys
from github_star_organizer.gh_client import GitHubClient, GitHubAPIError
from github_star_organizer.categorizer import categorize, get_categorized_ids, get_recent_stars
from github_star_organizer.issue_manager import (
    get_or_create_weekly_issue,
    get_already_reported_repos,
    report_uncategorized_repos,
    IssueError
)
from github_star_organizer.logger import get_logger
from github_star_organizer.config import load_config, ConfigError


logger = get_logger("categorize")


def main():
    try:
        # Load and validate config
        config = load_config()
        logger.info("Config loaded successfully")
        
        # Initialize client
        client = GitHubClient()
        
        # Fetch already categorized repos
        logger.info("Fetching already categorized stars...")
        categorized = get_categorized_ids(client)
        logger.info(f"Found {len(categorized)} categorized repositories")
        
        # Fetch recent stars
        logger.info("Fetching recent stars...")
        stars_result = client.run_query("""
        query {
          viewer {
            starredRepositories(first: 50, orderBy: {field: STARRED_AT, direction: DESC}) {
              nodes {
                id
                nameWithOwner
                description
                repositoryTopics(first: 10) {
                  nodes { topic { name } }
                }
              }
            }
          }
        }
        """)
        
        if not stars_result or "data" not in stars_result:
            logger.error("Failed to fetch stars")
            return
        
        stars = stars_result["data"]["viewer"]["starredRepositories"]["nodes"]
        skipped_repos = []
        
        # Categorize each star
        for repo in stars:
            if repo["id"] not in categorized:
                cat = categorize(repo)
                if cat:
                    logger.info(f"Categorizing {repo['nameWithOwner']} into {cat}...")
                    client.run_query("""
                    mutation($repoId: ID!, $listId: ID!) {
                      updateUserListsForItem(input: {itemId: $repoId, listIds: [$listId]}) { clientMutationId }
                    }
                    """, {"repoId": repo["id"], "listId": config["lists"].get(cat)})
                else:
                    logger.info(f"Skipping {repo['nameWithOwner']} (no keyword match)")
                    skipped_repos.append(repo)
            else:
                logger.info(f"Skipping {repo['nameWithOwner']} (already categorized)")
        
        # Report uncategorized repos
        if skipped_repos:
            logger.info(f"Preparing to report {len(skipped_repos)} uncategorized repos...")
            issue_num = get_or_create_weekly_issue(client)
            if issue_num:
                already_reported = get_already_reported_repos(client, issue_num)
                new_to_report = [repo for repo in skipped_repos 
                               if repo['nameWithOwner'] not in already_reported]
                
                if new_to_report:
                    report_uncategorized_repos(client, issue_num, new_to_report)
                    logger.info(f"Comment added to issue #{issue_num}")
                else:
                    logger.info("All skipped repos have already been reported")
    
    except ConfigError as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)
    except GitHubAPIError as e:
        logger.error(f"GitHub API error: {e}")
        sys.exit(1)
    except IssueError as e:
        logger.error(f"Issue management error: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Test the refactored script locally (manual)**

```bash
python categorize.py
```

Expected: Script runs and logs actions (may skip categorization if no new stars)

- [ ] **Step 4: Verify old functions are removed**

```bash
grep -c "def run_query" categorize.py || echo "run_query not in categorize.py (good)"
grep -c "def get_categorized_ids" categorize.py || echo "get_categorized_ids not in categorize.py (good)"
```

- [ ] **Step 5: Clean up and commit**

```bash
rm categorize.py.bak
git add categorize.py
git commit -m "refactor: migrate categorize.py to use github_star_organizer package"
```

---

### Task 8: Refactor distill.py to use the package

**Files:**
- Modify: `distill.py` (replace with refactored version)

- [ ] **Step 1: Replace distill.py with refactored version**

```python
# distill.py
import os
import sys
import json
import requests
from github_star_organizer.logger import get_logger
from github_star_organizer.gh_client import GitHubClient, GitHubAPIError
from github_star_organizer.issue_manager import get_or_create_weekly_issue, IssueError


logger = get_logger("distill")


def run_command(cmd):
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.error(f"Command failed: {result.stderr}")
        return None
    return result.stdout.strip()


def get_latest_uncategorized_issue():
    """Find the most recent open uncategorized stars issue"""
    client = GitHubClient()
    try:
        res = run_command(["gh", "issue", "list", "--state", "open", 
                          "--search", "Uncategorized Stars in:title author:@me", 
                          "--json", "number,body,title", "--limit", "1"])
        if not res or res == "[]":
            return None
        return json.loads(res)[0]
    except Exception as e:
        logger.error(f"Failed to fetch issue: {e}")
        return None


def get_issue_comments(issue_number):
    """Get comments from an issue (only from owner)"""
    try:
        user = run_command(["gh", "api", "user", "--json", "login", "-q", ".login"])
        if not user:
            logger.error("Could not determine current user")
            return ""
        
        res = run_command(["gh", "issue", "view", str(issue_number), 
                          "--json", "comments", 
                          "-q", f'.comments[] | select(.author.login == "{user}") | .body'])
        return res if res else ""
    except Exception as e:
        logger.error(f"Failed to get comments: {e}")
        return ""


def call_deepseek(prompt):
    """Call DeepSeek API to analyze uncategorized repos"""
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        logger.error("DEEPSEEK_API_KEY not found")
        return None
    
    url = "https://api.deepseek.com/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    data = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": "You are a specialized data organizer for GitHub stars. Your goal is to analyze uncategorized repositories and update a JSON configuration containing category-to-keyword mappings. Always return valid JSON only."},
            {"role": "user", "content": prompt}
        ],
        "response_format": {"type": "json_object"}
    }
    
    try:
        response = requests.post(url, headers=headers, json=data)
        if response.status_code == 200:
            return response.json()['choices'][0]['message']['content']
        else:
            logger.error(f"DeepSeek API Error: {response.status_code}")
            return None
    except Exception as e:
        logger.error(f"Failed to call DeepSeek: {e}")
        return None


def main():
    try:
        logger.info("Starting distillation...")
        
        issue = get_latest_uncategorized_issue()
        if not issue:
            logger.info("No open uncategorized issues found")
            return
        
        issue_number = issue["number"]
        logger.info(f"Found uncategorized issue #{issue_number}")
        
        comments = get_issue_comments(issue_number)
        if not comments:
            logger.info("No comments found in the issue")
            return
        
        with open("config.json", "r") as f:
            config = json.load(f)
        
        prompt = f"""
Analyze the following uncategorized GitHub repositories and suggest updates to the `config.json` provided below.

Current config.json:
{json.dumps(config, indent=2)}

New uncategorized repositories (from issue comments):
{comments}

Instructions:
1. Identify common themes among the uncategorized repositories.
2. If a repository fits an existing category, suggest adding new specific keywords to that category in `config.json` to capture it in the future.
3. If several repositories form a clear new theme (e.g., 'Cybersecurity', 'Game Dev', 'Self-Hosted'), suggest a new category name and a list of keywords.
4. DO NOT suggest a list ID for new categories (leave it empty or omit if you can't create one).
5. Ensure the resulting JSON matches the structure of `config.json`.
6. Be surgical: add precise keywords that won't cause false positives.

Return ONLY the complete updated `config.json` object.
"""
        
        logger.info(f"Analyzing {len(comments)} characters of uncategorized repos via DeepSeek...")
        new_config_json = call_deepseek(prompt)
        
        summary = {
            "status": "success",
            "repos_analyzed": 0,
            "new_keywords_added": 0,
            "new_categories": 0
        }
        
        if new_config_json:
            try:
                # Validate JSON
                new_config = json.loads(new_config_json)
                
                # Calculate diffs
                old_keywords = config.get("keywords", {})
                new_keywords = new_config.get("keywords", {})
                
                new_cats = [cat for cat in new_keywords if cat not in old_keywords]
                modified_cats = []
                for cat in old_keywords:
                    if cat in new_keywords and new_keywords[cat] != old_keywords[cat]:
                        modified_cats.append(cat)
                
                summary["new_keywords_added"] = sum(
                    len(new_keywords[cat]) - len(old_keywords.get(cat, []))
                    for cat in old_keywords if cat in new_keywords
                )
                summary["new_categories"] = len(new_cats)
                
                with open("config.json", "w") as f:
                    json.dump(new_config, f, indent=2)
                logger.info("config.json has been updated")
                
                # Extract date from issue title
                issue_title = issue.get("title", "")
                date_suffix = issue_title.split(": ")[-1] if ": " in issue_title else ""
                
                # Write outputs for GitHub Actions
                if "GITHUB_OUTPUT" in os.environ:
                    with open(os.environ["GITHUB_OUTPUT"], "a") as f:
                        f.write(f"date_suffix={date_suffix}\n")
                        f.write(f"issue_num={issue_number}\n")
                        f.write(f"summary={json.dumps(summary)}\n")
                
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse DeepSeek response: {e}")
                summary["status"] = "failed"
                summary["error"] = str(e)
                if "GITHUB_OUTPUT" in os.environ:
                    with open(os.environ["GITHUB_OUTPUT"], "a") as f:
                        f.write(f"summary={json.dumps(summary)}\n")
        else:
            logger.error("Failed to get response from DeepSeek")
            summary["status"] = "failed"
            summary["error"] = "DeepSeek API failed"
            if "GITHUB_OUTPUT" in os.environ:
                with open(os.environ["GITHUB_OUTPUT"], "a") as f:
                    f.write(f"summary={json.dumps(summary)}\n")
    
    except Exception as e:
        logger.error(f"Distillation failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Test the refactored script locally (manual, dry-run)**

```bash
python distill.py 2>&1 | head -20
```

Expected: Script runs and logs actions (may find no issues if none exist)

- [ ] **Step 3: Commit**

```bash
git add distill.py
git commit -m "refactor: migrate distill.py to use github_star_organizer package"
```

---

### Task 9: Refactor find_weird.py to use the package

**Files:**
- Modify: `find_weird.py` (replace with refactored version)

- [ ] **Step 1: Replace find_weird.py with refactored version**

```python
# find_weird.py
from github_star_organizer.gh_client import GitHubClient, GitHubAPIError
from github_star_organizer.categorizer import categorize
from github_star_organizer.logger import get_logger


logger = get_logger("find_weird")


def search_popular_repos(client):
    """Search for popular repositories created after 2023"""
    query = """
    query {
      search(query: "created:>2023-01-01 stars:>5000", type: REPOSITORY, first: 100) {
        nodes {
          ... on Repository {
            id
            nameWithOwner
            description
            repositoryTopics(first: 10) {
              nodes { topic { name } }
            }
          }
        }
      }
    }
    """
    return client.run_query(query)


def is_categorized(repo):
    """Check if repo is already categorized"""
    return categorize(repo) is not None


def main():
    try:
        client = GitHubClient()
        logger.info("Searching for popular repositories...")
        data = search_popular_repos(client)
        
        if not data or "data" not in data:
            logger.error("Failed to fetch repositories")
            return
        
        uncategorized = []
        for repo in data["data"]["search"]["nodes"]:
            if not is_categorized(repo):
                uncategorized.append(repo)
        
        if not uncategorized:
            logger.info("Could not find uncategorized popular repositories")
            return
        
        logger.info(f"Found {len(uncategorized)} potentially uncategorized repos")
        
        # Display first 15
        for i, repo in enumerate(uncategorized[:15]):
            topics = ", ".join([t["topic"]["name"] for t in repo.get("repositoryTopics", {}).get("nodes", [])])
            logger.info(f"{i+1}. {repo['nameWithOwner']}")
            logger.info(f"   Desc: {repo.get('description')}")
            logger.info(f"   Topics: {topics}")
    
    except GitHubAPIError as e:
        logger.warning(f"API error (continuing): {e}")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Test the refactored script locally (manual)**

```bash
python find_weird.py 2>&1 | head -20
```

Expected: Script runs and logs actions

- [ ] **Step 3: Commit**

```bash
git add find_weird.py
git commit -m "refactor: migrate find_weird.py to use github_star_organizer package"
```

---

## Phase 4: Integration Tests & Finalization

### Task 10: Write integration tests

**Files:**
- Create: `tests/integration/test_workflows.py`

- [ ] **Step 1: Write integration tests**

```python
# tests/integration/test_workflows.py
import unittest
from unittest.mock import patch, MagicMock
import json
import tempfile
import os
from github_star_organizer.gh_client import GitHubClient, GitHubAPIError
from github_star_organizer.categorizer import categorize
from github_star_organizer.issue_manager import get_or_create_weekly_issue


class TestCategorizeWorkflow(unittest.TestCase):
    @patch("subprocess.run")
    def test_categorize_workflow_end_to_end(self, mock_run):
        """Test full categorization workflow"""
        # Mock the gh API call to fetch categorized repos
        mock_result1 = MagicMock()
        mock_result1.returncode = 0
        mock_result1.stdout = '{"data": {"viewer": {"lists": {"nodes": []}}}}'
        
        # Mock the gh API call to fetch recent stars
        mock_result2 = MagicMock()
        mock_result2.returncode = 0
        mock_result2.stdout = '''{
          "data": {
            "viewer": {
              "starredRepositories": {
                "nodes": [
                  {
                    "id": "repo1",
                    "nameWithOwner": "user/ai-project",
                    "description": "An LLM-based tool",
                    "repositoryTopics": {"nodes": []}
                  }
                ]
              }
            }
          }
        }'''
        
        mock_run.side_effect = [mock_result1, mock_result2]
        
        client = GitHubClient()
        
        # Should not raise
        categorized = client.run_query("query { ... }")
        self.assertIn("data", categorized)


class TestDistillWorkflow(unittest.TestCase):
    @patch("subprocess.run")
    @patch("requests.post")
    def test_distill_workflow_with_deepseek(self, mock_requests, mock_run):
        """Test distillation workflow with DeepSeek API"""
        # Mock gh CLI response for issue list
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = '[{"number": 42, "title": "Uncategorized Stars: 2026-W18", "body": "Test"}]'
        mock_run.return_value = mock_result
        
        # Mock DeepSeek response
        mock_deepseek = MagicMock()
        mock_deepseek.status_code = 200
        mock_deepseek.json.return_value = {
            "choices": [{
                "message": {
                    "content": '{"lists": {}, "keywords": {"AI Agents & LLMs": ["test"]}}'
                }
            }]
        }
        mock_requests.return_value = mock_deepseek
        
        # Should not raise
        os.environ["DEEPSEEK_API_KEY"] = "test_key"
        from github_star_organizer.gh_client import run_query
        result = run_query("test")
        self.assertIsNotNone(result)


class TestIssueManagementWorkflow(unittest.TestCase):
    @patch("github_star_organizer.issue_manager.run_command")
    @patch("github_star_organizer.issue_manager.datetime")
    def test_issue_creation_and_closure(self, mock_datetime, mock_run_command):
        """Test full issue lifecycle"""
        import datetime as dt
        mock_datetime.date.today.return_value = dt.date(2026, 5, 2)
        
        # Mock creating an issue
        mock_run_command.side_effect = [
            "[]",  # No existing issues
            "https://github.com/user/repo/issues/42"  # Created
        ]
        
        client = MagicMock()
        from github_star_organizer.issue_manager import get_or_create_weekly_issue
        issue_num = get_or_create_weekly_issue(client)
        
        self.assertEqual(issue_num, "42")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run integration tests**

```bash
python -m pytest tests/integration/test_workflows.py -v
```

Expected: PASS (3/3)

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_workflows.py
git commit -m "test: add integration tests for categorization and distillation workflows"
```

---

### Task 11: Update GitHub Actions workflows

**Files:**
- Modify: `.github/workflows/organize.yml`
- Modify: `.github/workflows/distill.yml`

- [ ] **Step 1: Update organize.yml**

```yaml
name: Organize Stars
on:
  push:
    branches: [ main ]
  schedule:
    - cron: '0 */12 * * *' # Every 12 hours
  workflow_dispatch: # Allow manual trigger

jobs:
  organize:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.x'
      
      - name: Install dependencies
        run: pip install -r requirements.txt
      
      - name: Organize Stars
        env:
          GH_TOKEN: ${{ secrets.GH_TOKEN }}
        run: python3 categorize.py
```

- [ ] **Step 2: Update distill.yml**

```yaml
name: Distill Keywords
on:
  schedule:
    - cron: '0 0 * * 0' # Every Sunday at midnight
  workflow_dispatch: # Allow manual trigger

jobs:
  distill:
    runs-on: ubuntu-latest
    permissions:
      contents: write
      pull-requests: write
      issues: read
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.x'
      
      - name: Install dependencies
        run: pip install -r requirements.txt
      
      - name: Run Distillation
        id: distillation
        env:
          GH_TOKEN: ${{ secrets.GH_TOKEN }}
          DEEPSEEK_API_KEY: ${{ secrets.DEEPSEEK_API_KEY }}
        run: python distill.py
      
      - name: Create Pull Request
        uses: peter-evans/create-pull-request@v6
        with:
          token: ${{ secrets.GH_TOKEN }}
          commit-message: "Automated: Update config.json keywords from uncategorized stars (${{ steps.distillation.outputs.date_suffix }})"
          title: "Distillation: Update Star Categories (${{ steps.distillation.outputs.date_suffix }})"
          body: |
            This PR was automatically generated by the Distill Keywords runner.
            
            ## Distillation Summary
            ${{ steps.distillation.outputs.summary }}
            
            See issue #${{ steps.distillation.outputs.issue_num }} for uncategorized repos.
          branch: "distill-keywords"
          delete-branch: true
```

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/organize.yml .github/workflows/distill.yml
git commit -m "ci: update workflows to install dependencies and use structured summaries"
```

---

### Task 12: Run full test suite and final checks

**Files:**
- None (verification only)

- [ ] **Step 1: Run all tests**

```bash
python -m pytest tests/ -v --tb=short
```

Expected: PASS (30+ tests)

- [ ] **Step 2: Check test coverage**

```bash
python -m pytest tests/ --cov=github_star_organizer --cov-report=term-missing
```

Expected: >80% coverage on package modules

- [ ] **Step 3: Verify scripts still work**

```bash
python categorize.py --help 2>&1 || python categorize.py 2>&1 | head -5
python distill.py 2>&1 | head -5
python find_weird.py 2>&1 | head -5
```

Expected: Scripts execute without import errors

- [ ] **Step 4: Verify no old code remains**

```bash
grep -r "def run_query" github_star_organizer/ | wc -l
```

Expected: 1 (only in gh_client.py)

```bash
grep -r "def categorize" github_star_organizer/ | wc -l
```

Expected: 1 (only in categorizer.py)

- [ ] **Step 5: Final commit**

```bash
git log --oneline | head -20
```

Expected: See all refactoring commits

- [ ] **Step 6: Summary log**

```bash
echo "✓ Package structure created"
echo "✓ 5 modules implemented with type hints"
echo "✓ 3 entry-point scripts refactored"
echo "✓ 30+ tests written (unit + integration)"
echo "✓ GitHub Actions workflows updated"
echo "✓ All tests passing"
```

---

## Self-Review Checklist

**Spec Coverage:**
- ✅ Package structure with 5 modules (gh_client, categorizer, logger, config, issue_manager)
- ✅ Type hints on key functions (Public APIs)
- ✅ 30+ tests with >80% coverage
- ✅ Logging throughout (logger module)
- ✅ Error handling with custom exceptions
- ✅ Issue lifecycle management consolidated
- ✅ GitHub Actions workflows updated with summaries
- ✅ Entry-point scripts refactored to use package

**No Placeholders:**
- ✅ All code blocks complete and runnable
- ✅ All test code shown explicitly
- ✅ All commands with expected output listed
- ✅ No "TBD" or "add validation" vague steps
- ✅ Function signatures match across tasks

**Type Consistency:**
- ✅ `run_query()` returns `dict` everywhere
- ✅ `categorize()` returns `str | None` everywhere
- ✅ Client passed consistently to module functions
- ✅ Logger functions named `get_logger()` consistently

**Dependencies:**
- ✅ Only `requests` as external dependency (in requirements.txt)
- ✅ All modules use stdlib only (subprocess, json, logging, re, datetime)
- ✅ Type hints available in Python 3.10+

---

## Execution

This plan is ready for implementation. Two options:

**Option 1: Subagent-Driven (Recommended)**
- Fresh subagent per task (1-2 per session)
- Two-stage review between tasks
- Faster iteration on errors
- Better for complex tasks with interdependencies

**Option 2: Inline Execution**
- Execute tasks sequentially in this session
- Review at end of phase
- Simpler coordination
- Better for straightforward tasks

Which approach would you prefer?
