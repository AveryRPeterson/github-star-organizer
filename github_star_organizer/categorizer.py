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
