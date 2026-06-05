import sqlite3
import json
import datetime
import os
from contextlib import contextmanager

DB_PATH = os.getenv("STATE_DB_PATH", "state.db")


@contextmanager
def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with _conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS discovered_repos (
                name_with_owner TEXT PRIMARY KEY,
                description TEXT,
                topics TEXT,
                deepseek_purpose TEXT,
                deepseek_use_case TEXT,
                deepseek_unusual_apps TEXT,
                ollama_purpose TEXT,
                ollama_use_case TEXT,
                ollama_unusual_apps TEXT,
                github_issue_number TEXT,
                discovered_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS uncategorized_repos (
                name_with_owner TEXT PRIMARY KEY,
                description TEXT,
                topics TEXT,
                reported_at TEXT NOT NULL,
                issue_number TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ollama_model_metrics (
                model_name TEXT PRIMARY KEY,
                success_200_count INTEGER DEFAULT 0,
                empty_body_count INTEGER DEFAULT 0,
                empty_json_count INTEGER DEFAULT 0,
                invalid_json_count INTEGER DEFAULT 0,
                client_4xx_count INTEGER DEFAULT 0,
                subscription_403_count INTEGER DEFAULT 0,
                server_5xx_count INTEGER DEFAULT 0,
                timeout_count INTEGER DEFAULT 0,
                hallucination_count INTEGER DEFAULT 0,
                last_updated TEXT NOT NULL
            )
        """)



def get_discovered_repos() -> set[str]:
    with _conn() as conn:
        rows = conn.execute("SELECT name_with_owner FROM discovered_repos").fetchall()
    return {row[0] for row in rows}


def insert_discovered_repo(repo: dict, model_summaries: dict, issue_number: str) -> None:
    name = repo["nameWithOwner"]
    topics = ", ".join(
        [t["topic"]["name"] for t in repo.get("repositoryTopics", {}).get("nodes", [])]
    )
    ds = model_summaries.get("deepseek", {}).get(name, {})
    ol = model_summaries.get("ollama", {}).get(name, {})
    with _conn() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO discovered_repos (
                name_with_owner, description, topics,
                deepseek_purpose, deepseek_use_case, deepseek_unusual_apps,
                ollama_purpose, ollama_use_case, ollama_unusual_apps,
                github_issue_number, discovered_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                name,
                repo.get("description"),
                topics,
                ds.get("purpose"),
                ds.get("use_case"),
                json.dumps(ds.get("unusual_applications", [])),
                ol.get("purpose"),
                ol.get("use_case"),
                json.dumps(ol.get("unusual_applications", [])),
                issue_number,
                datetime.date.today().isoformat(),
            ),
        )



def get_uncategorized_repos() -> set[str]:
    with _conn() as conn:
        rows = conn.execute("SELECT name_with_owner FROM uncategorized_repos").fetchall()
    return {row[0] for row in rows}


def insert_uncategorized_repos(repos: list[dict], issue_number: str) -> None:
    today = datetime.date.today().isoformat()
    with _conn() as conn:
        for repo in repos:
            topics = ", ".join(
                [t["topic"]["name"] for t in repo.get("repositoryTopics", {}).get("nodes", [])]
            )
            conn.execute(
                """
                INSERT OR IGNORE INTO uncategorized_repos
                (name_with_owner, description, topics, reported_at, issue_number)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    repo["nameWithOwner"],
                    repo.get("description"),
                    topics,
                    today,
                    issue_number,
                ),
            )



def get_issue_number_for_discovered(name_with_owner: str) -> str | None:
    with _conn() as conn:
        row = conn.execute(
            "SELECT github_issue_number FROM discovered_repos WHERE name_with_owner = ?",
            (name_with_owner,),
        ).fetchone()
    return row[0] if row else None


def record_ollama_model_metric(
    model_name: str,
    success: bool = False,
    empty_body: bool = False,
    empty_json: bool = False,
    invalid_json: bool = False,
    status_code: int | None = None,
    timeout: bool = False,
    hallucination: bool = False,
) -> None:
    """Record a metric for an Ollama model attempt."""
    with _conn() as conn:
        # Initialize row if not exists
        conn.execute(
            """
            INSERT OR IGNORE INTO ollama_model_metrics
            (model_name, last_updated) VALUES (?, ?)
            """,
            (model_name, datetime.date.today().isoformat()),
        )

        # Update metrics
        updates = []
        if success:
            updates.append("success_200_count = success_200_count + 1")
        if empty_body:
            updates.append("empty_body_count = empty_body_count + 1")
        if empty_json:
            updates.append("empty_json_count = empty_json_count + 1")
        if invalid_json:
            updates.append("invalid_json_count = invalid_json_count + 1")
        if status_code == 403:
            updates.append("subscription_403_count = subscription_403_count + 1")
            updates.append("client_4xx_count = client_4xx_count + 1")
        elif status_code and 400 <= status_code < 500:
            updates.append("client_4xx_count = client_4xx_count + 1")
        elif status_code and status_code >= 500:
            updates.append("server_5xx_count = server_5xx_count + 1")
        if timeout:
            updates.append("timeout_count = timeout_count + 1")
        if hallucination:
            updates.append("hallucination_count = hallucination_count + 1")

        if updates:
            updates.append("last_updated = ?")
            sql = f"UPDATE ollama_model_metrics SET {', '.join(updates)} WHERE model_name = ?"
            conn.execute(sql, (datetime.date.today().isoformat(), model_name))


def get_all_known_ollama_models() -> list[str]:
    """Return all model names tracked in the metrics table."""
    with _conn() as conn:
        rows = conn.execute("SELECT model_name FROM ollama_model_metrics").fetchall()
    return [row[0] for row in rows]


def reset_subscription_metrics(model_name: str) -> None:
    """
    Reset 403/subscription counts for a model that has transitioned from paid to free.
    Subtracts subscription_403_count from client_4xx_count then zeroes subscription_403_count.
    Non-subscription quality signals (success, empty, timeout, hallucination) are preserved.
    """
    with _conn() as conn:
        conn.execute(
            """
            UPDATE ollama_model_metrics
            SET client_4xx_count = MAX(0, client_4xx_count - subscription_403_count),
                subscription_403_count = 0,
                last_updated = ?
            WHERE model_name = ?
            """,
            (datetime.date.today().isoformat(), model_name),
        )


SUBSCRIPTION_SKIP_THRESHOLD = 3


def get_sorted_ollama_models(base_models: list[str], skip_gated: bool = True) -> list[str]:
    """
    Sort curated Ollama models by reliability metrics.

    Scoring: success_200 * 100 - empty_body * 10 - empty_json * 5
             - client_4xx * 15 - server_5xx * 20 - timeout * 25
             - hallucination * 30 - subscription_403 * 12

    Models with no metrics (newly added) appear at the end to try them.
    Returns the reordered list with highest-scoring (most reliable) first.

    When skip_gated=True (default), models with subscription_403_count >=
    SUBSCRIPTION_SKIP_THRESHOLD and no successes are excluded entirely.
    The weekly probe workflow re-evaluates them and resets metrics if they
    become free.
    """
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM ollama_model_metrics WHERE model_name IN ({})".format(
                ",".join("?" * len(base_models))
            ),
            base_models,
        ).fetchall()

    metrics_dict = {row["model_name"]: dict(row) for row in rows}

    def is_subscription_gated(model_name: str) -> bool:
        if model_name not in metrics_dict:
            return False
        m = metrics_dict[model_name]
        return (
            (m["subscription_403_count"] or 0) >= SUBSCRIPTION_SKIP_THRESHOLD
            and (m["success_200_count"] or 0) == 0
        )

    def score_model(model_name: str) -> tuple:
        """Return (has_metrics, score) for sorting."""
        if model_name not in metrics_dict:
            return (False, 0)

        m = metrics_dict[model_name]
        score = (
            (m["success_200_count"] or 0) * 100
            - (m["empty_body_count"] or 0) * 10
            - (m["empty_json_count"] or 0) * 5
            - (m["client_4xx_count"] or 0) * 15
            - (m["server_5xx_count"] or 0) * 20
            - (m["timeout_count"] or 0) * 25
            - (m["hallucination_count"] or 0) * 30
            - (m["subscription_403_count"] or 0) * 12
        )
        return (True, score)

    candidates = (
        [m for m in base_models if not is_subscription_gated(m)]
        if skip_gated
        else base_models
    )
    return sorted(candidates, key=score_model, reverse=True)
