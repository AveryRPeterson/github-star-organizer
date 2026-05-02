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
