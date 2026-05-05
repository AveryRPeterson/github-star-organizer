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
                    list_id = config["lists"].get(cat)
                    if list_id:
                        logger.info(f"Categorizing {repo['nameWithOwner']} into {cat}...")
                        client.run_query("""
                        mutation($repoId: ID!, $listId: ID!) {
                          updateUserListsForItem(input: {itemId: $repoId, listIds: [$listId]}) { clientMutationId }
                        }
                        """, {"repoId": repo["id"], "listId": list_id})
                    else:
                        logger.info(f"Skipping {repo['nameWithOwner']} (category '{cat}' has no list ID configured)")
                        skipped_repos.append(repo)
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
