import json
import subprocess
import random

def load_config():
    with open("config.json", "r") as f:
        return json.load(f)

config = load_config()
KEYWORDS = config["keywords"]

def run_query(query, variables=None):
    cmd = ["gh", "api", "graphql", "-f", f"query={query}"]
    if variables:
        for k, v in variables.items():
            cmd.extend(["-f", f"{k}={v}"])
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error: {result.stderr}")
        return None
    return json.loads(result.stdout)

def search_popular_repos():
    # Search for recent highly starred repositories that are not AI, not standard web dev
    # We want mind-bending ones (e.g., biological, quantum, esoteric languages, weird concepts)
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
    return run_query(query)

def is_categorized(repo):
    name = repo.get("nameWithOwner", "").lower()
    desc = (repo.get("description") or "").lower()
    topics = [t["topic"]["name"].lower() for t in repo.get("repositoryTopics", {}).get("nodes", [])]
    combined = f"{name} {desc} {' '.join(topics)}"
    
    for cat, kws in KEYWORDS.items():
        if any(kw in combined for kw in kws):
            return True
    return False

def main():
    print("Searching for popular repositories...")
    data = search_popular_repos()
    if not data or "data" not in data:
        print("Failed to fetch repositories.")
        return

    uncategorized = []
    for repo in data["data"]["search"]["nodes"]:
        if not is_categorized(repo):
            uncategorized.append(repo)

    if not uncategorized:
        print("Could not find uncategorized popular repositories.")
        return

    print(f"Found {len(uncategorized)} potentially uncategorized repos.")
    
    # We want to pick 5 mind-bending ones. Let's just output them so we can pick.
    for i, repo in enumerate(uncategorized[:15]):
        topics = ", ".join([t["topic"]["name"] for t in repo.get("repositoryTopics", {}).get("nodes", [])])
        print(f"{i+1}. {repo['nameWithOwner']}")
        print(f"   Desc: {repo.get('description')}")
        print(f"   Topics: {topics}\n")

if __name__ == "__main__":
    main()
