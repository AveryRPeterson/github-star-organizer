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
