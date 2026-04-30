import pytest
from categorize import categorize

def test_categorize_ai_agents():
    repo = {
        "nameWithOwner": "user/my-llm-project",
        "description": "An awesome project",
        "repositoryTopics": {"nodes": []}
    }
    assert categorize(repo) == "AI Agents & LLMs"

def test_categorize_3d_printing():
    repo = {
        "nameWithOwner": "user/repo",
        "description": "A 3d printer mesh tool",
        "repositoryTopics": {"nodes": []}
    }
    assert categorize(repo) == "3D Printing & CAD"

def test_categorize_priority():
    # Matches both AI (gpt) and Tools (cli)
    # AI Agents & LLMs should be returned as it is checked first
    repo = {
        "nameWithOwner": "user/gpt-cli",
        "description": "A tool",
        "repositoryTopics": {"nodes": []}
    }
    assert categorize(repo) == "AI Agents & LLMs"

def test_categorize_dynamic():
    # Quantum Computing is not in the hardcoded priority list but in config.json
    repo = {
        "nameWithOwner": "user/q-sim",
        "description": "A quantum simulator",
        "repositoryTopics": {"nodes": []}
    }
    assert categorize(repo) == "Quantum Computing"

def test_categorize_topics():
    repo = {
        "nameWithOwner": "user/repo",
        "description": "none",
        "repositoryTopics": {"nodes": [
            {"topic": {"name": "mechanical-keyboard"}},
            {"topic": {"name": "zmk"}}
        ]}
    }
    assert categorize(repo) == "Hardware & Keyboards"

def test_categorize_case_insensitive():
    repo = {
        "nameWithOwner": "USER/ANDROID-TOOL",
        "description": "DESC",
        "repositoryTopics": {"nodes": []}
    }
    assert categorize(repo) == "Android & Termux"

def test_categorize_none():
    repo = {
        "nameWithOwner": "user/unknown",
        "description": "just some random text",
        "repositoryTopics": {"nodes": []}
    }
    assert categorize(repo) is None

def test_categorize_empty():
    repo = {}
    assert categorize(repo) is None
