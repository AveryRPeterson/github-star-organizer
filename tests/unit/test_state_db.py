import os
import json
import tempfile
import sqlite3
import pytest
import gc
from unittest.mock import patch
from github_star_organizer import state_db


@pytest.fixture
def temp_db(monkeypatch):
    """Create a temporary database for testing with proper isolation."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setenv("STATE_DB_PATH", path)
    # Patch the module's DB_PATH so it uses our temp path
    monkeypatch.setattr("github_star_organizer.state_db.DB_PATH", path)
    yield path
    # Force garbage collection to close any dangling connections
    gc.collect()
    if os.path.exists(path):
        os.remove(path)


class TestInitDb:
    def test_init_db_creates_tables(self, temp_db):
        """Verify init_db creates all required tables."""
        state_db.init_db()

        conn = sqlite3.connect(temp_db)
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = {row[0] for row in cursor.fetchall()}
        finally:
            conn.close()

        assert "discovered_repos" in tables
        assert "uncategorized_repos" in tables
        assert "ollama_model_metrics" in tables

    def test_init_db_idempotent(self, temp_db):
        """Verify init_db can be called multiple times without error."""
        state_db.init_db()
        state_db.init_db()

        conn = sqlite3.connect(temp_db)
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = {row[0] for row in cursor.fetchall()}
        finally:
            conn.close()

        assert len(tables) == 3


class TestDiscoveredRepos:
    def test_get_discovered_repos_empty(self, temp_db):
        """Verify get_discovered_repos returns empty set when no repos exist."""
        state_db.init_db()
        result = state_db.get_discovered_repos()
        assert result == set()

    def test_insert_and_get_discovered_repo(self, temp_db):
        """Verify insert_discovered_repo and get_discovered_repos work together."""
        state_db.init_db()

        repo = {
            "nameWithOwner": "owner/repo1",
            "description": "Test repo",
            "repositoryTopics": {"nodes": []},
        }
        model_summaries = {
            "owner/repo1": {
                "purpose": "Test purpose",
                "use_case": "Test use case",
                "unusual_applications": ["app1", "app2"],
            }
        }

        state_db.insert_discovered_repo(repo, model_summaries, "42")
        result = state_db.get_discovered_repos()

        assert "owner/repo1" in result
        assert len(result) == 1

    def test_insert_discovered_repo_with_topics(self, temp_db):
        """Verify insert_discovered_repo handles topics correctly."""
        state_db.init_db()

        repo = {
            "nameWithOwner": "owner/repo2",
            "description": "Repo with topics",
            "repositoryTopics": {
                "nodes": [
                    {"topic": {"name": "python"}},
                    {"topic": {"name": "ml"}},
                ]
            },
        }
        model_summaries = {"owner/repo2": {}}

        state_db.insert_discovered_repo(repo, model_summaries, "43")
        result = state_db.get_discovered_repos()

        assert "owner/repo2" in result

    def test_insert_discovered_repo_multiple(self, temp_db):
        """Verify multiple discovered repos are stored."""
        state_db.init_db()

        for i in range(3):
            repo = {
                "nameWithOwner": f"owner/repo{i}",
                "description": f"Repo {i}",
                "repositoryTopics": {"nodes": []},
            }
            state_db.insert_discovered_repo(repo, {}, f"{i}")

        result = state_db.get_discovered_repos()
        assert len(result) == 3
        assert all(f"owner/repo{i}" in result for i in range(3))

    def test_insert_discovered_repo_duplicate_ignored(self, temp_db):
        """Verify INSERT OR IGNORE prevents duplicates."""
        state_db.init_db()

        repo = {
            "nameWithOwner": "owner/repo",
            "description": "Test",
            "repositoryTopics": {"nodes": []},
        }

        state_db.insert_discovered_repo(repo, {}, "1")
        state_db.insert_discovered_repo(repo, {}, "2")

        result = state_db.get_discovered_repos()
        assert len(result) == 1

    def test_get_issue_number_for_discovered_found(self, temp_db):
        """Verify get_issue_number_for_discovered returns correct issue number."""
        state_db.init_db()

        repo = {
            "nameWithOwner": "owner/repo",
            "description": "Test",
            "repositoryTopics": {"nodes": []},
        }
        state_db.insert_discovered_repo(repo, {}, "42")

        result = state_db.get_issue_number_for_discovered("owner/repo")
        assert result == "42"

    def test_get_issue_number_for_discovered_not_found(self, temp_db):
        """Verify get_issue_number_for_discovered returns None for missing repo."""
        state_db.init_db()
        result = state_db.get_issue_number_for_discovered("owner/nonexistent")
        assert result is None

    def test_insert_discovered_repo_with_deepseek_summary(self, temp_db):
        """Verify insert_discovered_repo stores DeepSeek summary data."""
        state_db.init_db()

        repo = {
            "nameWithOwner": "owner/repo",
            "description": "Test",
            "repositoryTopics": {"nodes": []},
        }
        model_summaries = {
            "deepseek": {
                "owner/repo": {
                    "purpose": "Build things",
                    "use_case": "Development",
                    "unusual_applications": ["app1", "app2", "app3"],
                }
            }
        }

        state_db.insert_discovered_repo(repo, model_summaries, "100")

        conn = sqlite3.connect(temp_db)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "SELECT * FROM discovered_repos WHERE name_with_owner = ?",
                ("owner/repo",),
            ).fetchone()
        finally:
            conn.close()

        assert row["deepseek_purpose"] == "Build things"
        assert row["deepseek_use_case"] == "Development"
        assert json.loads(row["deepseek_unusual_apps"]) == ["app1", "app2", "app3"]

    def test_insert_discovered_repo_with_ollama_summary(self, temp_db):
        """Verify insert_discovered_repo stores Ollama summary data."""
        state_db.init_db()

        repo = {
            "nameWithOwner": "owner/repo",
            "description": "Test",
            "repositoryTopics": {"nodes": []},
        }
        model_summaries = {
            "ollama": {
                "owner/repo": {
                    "purpose": "Analyze data",
                    "use_case": "Analysis",
                    "unusual_applications": ["x", "y"],
                }
            }
        }

        state_db.insert_discovered_repo(repo, model_summaries, "101")

        conn = sqlite3.connect(temp_db)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "SELECT * FROM discovered_repos WHERE name_with_owner = ?",
                ("owner/repo",),
            ).fetchone()
        finally:
            conn.close()

        assert row["ollama_purpose"] == "Analyze data"
        assert row["ollama_use_case"] == "Analysis"
        assert json.loads(row["ollama_unusual_apps"]) == ["x", "y"]


class TestUncategorizedRepos:
    def test_get_uncategorized_repos_empty(self, temp_db):
        """Verify get_uncategorized_repos returns empty set initially."""
        state_db.init_db()
        result = state_db.get_uncategorized_repos()
        assert result == set()

    def test_insert_and_get_uncategorized_repos(self, temp_db):
        """Verify insert_uncategorized_repos and get_uncategorized_repos work together."""
        state_db.init_db()

        repos = [
            {
                "nameWithOwner": "owner/uncategorized1",
                "description": "Uncategorized repo 1",
                "repositoryTopics": {"nodes": []},
            },
            {
                "nameWithOwner": "owner/uncategorized2",
                "description": "Uncategorized repo 2",
                "repositoryTopics": {"nodes": []},
            },
        ]

        state_db.insert_uncategorized_repos(repos, "999")
        result = state_db.get_uncategorized_repos()

        assert "owner/uncategorized1" in result
        assert "owner/uncategorized2" in result
        assert len(result) == 2

    def test_insert_uncategorized_repos_with_topics(self, temp_db):
        """Verify insert_uncategorized_repos handles topics."""
        state_db.init_db()

        repos = [
            {
                "nameWithOwner": "owner/repo",
                "description": "Repo with topics",
                "repositoryTopics": {
                    "nodes": [
                        {"topic": {"name": "javascript"}},
                        {"topic": {"name": "web"}},
                    ]
                },
            }
        ]

        state_db.insert_uncategorized_repos(repos, "1000")
        result = state_db.get_uncategorized_repos()

        assert "owner/repo" in result

    def test_insert_uncategorized_repos_empty_list(self, temp_db):
        """Verify insert_uncategorized_repos handles empty list."""
        state_db.init_db()
        state_db.insert_uncategorized_repos([], "1001")
        result = state_db.get_uncategorized_repos()
        assert result == set()

    def test_insert_uncategorized_repos_multiple_calls(self, temp_db):
        """Verify multiple calls to insert_uncategorized_repos accumulate."""
        state_db.init_db()

        repos1 = [
            {
                "nameWithOwner": "owner/repo1",
                "description": "Repo 1",
                "repositoryTopics": {"nodes": []},
            }
        ]
        repos2 = [
            {
                "nameWithOwner": "owner/repo2",
                "description": "Repo 2",
                "repositoryTopics": {"nodes": []},
            }
        ]

        state_db.insert_uncategorized_repos(repos1, "1")
        state_db.insert_uncategorized_repos(repos2, "2")

        result = state_db.get_uncategorized_repos()
        assert len(result) == 2

    def test_insert_uncategorized_repos_duplicate_ignored(self, temp_db):
        """Verify INSERT OR IGNORE prevents duplicate uncategorized repos."""
        state_db.init_db()

        repos = [
            {
                "nameWithOwner": "owner/repo",
                "description": "Test",
                "repositoryTopics": {"nodes": []},
            }
        ]

        state_db.insert_uncategorized_repos(repos, "1")
        state_db.insert_uncategorized_repos(repos, "2")

        result = state_db.get_uncategorized_repos()
        assert len(result) == 1

    def test_insert_uncategorized_repos_stores_issue_number(self, temp_db):
        """Verify insert_uncategorized_repos stores issue number."""
        state_db.init_db()

        repos = [
            {
                "nameWithOwner": "owner/repo",
                "description": "Test",
                "repositoryTopics": {"nodes": []},
            }
        ]

        state_db.insert_uncategorized_repos(repos, "2000")

        conn = sqlite3.connect(temp_db)
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "SELECT issue_number FROM uncategorized_repos WHERE name_with_owner = ?",
                ("owner/repo",),
            ).fetchone()
        finally:
            conn.close()

        assert row["issue_number"] == "2000"


class TestConnectionErrorHandling:
    def test_rollback_on_exception(self, temp_db):
        """Verify the connection is rolled back and closed when an exception occurs."""
        state_db.init_db()

        with pytest.raises(sqlite3.OperationalError):
            with state_db._conn() as conn:
                conn.execute("INSERT INTO discovered_repos (name_with_owner, discovered_at) VALUES (?, ?)", ("owner/r", "2026-01-01"))
                conn.execute("SELECT * FROM nonexistent_table")  # forces error

        # DB is still usable after the error
        result = state_db.get_discovered_repos()
        assert "owner/r" not in result


class TestMixedOperations:
    def test_discovered_and_uncategorized_separate(self, temp_db):
        """Verify discovered and uncategorized repos are stored separately."""
        state_db.init_db()

        discovered = {
            "nameWithOwner": "owner/discovered",
            "description": "Discovered",
            "repositoryTopics": {"nodes": []},
        }
        uncategorized = {
            "nameWithOwner": "owner/uncategorized",
            "description": "Uncategorized",
            "repositoryTopics": {"nodes": []},
        }

        state_db.insert_discovered_repo(discovered, {}, "1")
        state_db.insert_uncategorized_repos([uncategorized], "2")

        discovered_set = state_db.get_discovered_repos()
        uncategorized_set = state_db.get_uncategorized_repos()

        assert "owner/discovered" in discovered_set
        assert "owner/uncategorized" in uncategorized_set
        assert "owner/discovered" not in uncategorized_set
        assert "owner/uncategorized" not in discovered_set

    def test_concurrent_table_operations(self, temp_db):
        """Verify operations on different tables don't interfere."""
        state_db.init_db()

        for i in range(5):
            repo = {
                "nameWithOwner": f"owner/discovered{i}",
                "description": f"Discovered {i}",
                "repositoryTopics": {"nodes": []},
            }
            state_db.insert_discovered_repo(repo, {}, f"{i}")

        for i in range(5):
            repos = [
                {
                    "nameWithOwner": f"owner/uncategorized{i}",
                    "description": f"Uncategorized {i}",
                    "repositoryTopics": {"nodes": []},
                }
            ]
            state_db.insert_uncategorized_repos(repos, f"{i}")

        discovered = state_db.get_discovered_repos()
        uncategorized = state_db.get_uncategorized_repos()

        assert len(discovered) == 5
        assert len(uncategorized) == 5


class TestOllamaModelMetrics:
    def test_record_success(self, temp_db):
        state_db.init_db()
        state_db.record_ollama_model_metric("model-a", success=True)

        result = state_db.get_sorted_ollama_models(["model-a"])
        assert result == ["model-a"]

    def test_sorted_by_score_descending(self, temp_db):
        """Model with more successes should rank higher."""
        state_db.init_db()
        state_db.record_ollama_model_metric("low", success=True)
        state_db.record_ollama_model_metric("high", success=True)
        state_db.record_ollama_model_metric("high", success=True)

        result = state_db.get_sorted_ollama_models(["low", "high"])
        assert result[0] == "high"

    def test_unknown_models_appear_last(self, temp_db):
        """Models with no history go after ranked models."""
        state_db.init_db()
        state_db.record_ollama_model_metric("known", success=True)

        result = state_db.get_sorted_ollama_models(["unknown", "known"])
        assert result[0] == "known"
        assert result[1] == "unknown"

    def test_subscription_gated_excluded_by_default(self, temp_db):
        """Models with >= threshold 403s and no successes are skipped."""
        state_db.init_db()
        for _ in range(state_db.SUBSCRIPTION_SKIP_THRESHOLD):
            state_db.record_ollama_model_metric("gated", status_code=403)
        state_db.record_ollama_model_metric("free", success=True)

        result = state_db.get_sorted_ollama_models(["gated", "free"])
        assert "gated" not in result
        assert "free" in result

    def test_subscription_gated_included_when_skip_false(self, temp_db):
        """skip_gated=False includes all models regardless of 403 history."""
        state_db.init_db()
        for _ in range(state_db.SUBSCRIPTION_SKIP_THRESHOLD):
            state_db.record_ollama_model_metric("gated", status_code=403)

        result = state_db.get_sorted_ollama_models(["gated"], skip_gated=False)
        assert "gated" in result

    def test_model_with_403s_but_also_successes_not_skipped(self, temp_db):
        """A model that had 403s but also succeeds is not treated as gated."""
        state_db.init_db()
        for _ in range(state_db.SUBSCRIPTION_SKIP_THRESHOLD):
            state_db.record_ollama_model_metric("mixed", status_code=403)
        state_db.record_ollama_model_metric("mixed", success=True)

        result = state_db.get_sorted_ollama_models(["mixed"])
        assert "mixed" in result

    def test_reset_subscription_metrics(self, temp_db):
        """reset_subscription_metrics zeroes 403 counts and adjusts client_4xx."""
        state_db.init_db()
        for _ in range(4):
            state_db.record_ollama_model_metric("model", status_code=403)

        state_db.reset_subscription_metrics("model")

        # After reset the model should no longer be gated
        result = state_db.get_sorted_ollama_models(["model"])
        assert "model" in result

    def test_get_all_known_ollama_models(self, temp_db):
        state_db.init_db()
        state_db.record_ollama_model_metric("alpha", success=True)
        state_db.record_ollama_model_metric("beta", timeout=True)

        known = state_db.get_all_known_ollama_models()
        assert "alpha" in known
        assert "beta" in known
        assert len(known) == 2
