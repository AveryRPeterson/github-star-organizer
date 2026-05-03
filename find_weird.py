import os
import json
import sys
import datetime
import requests
from github_star_organizer.gh_client import GitHubClient, GitHubAPIError
from github_star_organizer.categorizer import categorize
from github_star_organizer.logger import get_logger
from github_star_organizer.issue_manager import (
    get_or_create_weekly_issue,
    get_or_create_weekly_discovery_issue,
    get_already_reported_repos,
    report_uncategorized_repos,
    IssueError,
)


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


def call_deepseek_summaries(repos: list[dict]) -> dict[str, dict] | None:
    """
    Call DeepSeek API to generate summaries for uncategorized repos.

    Args:
        repos: List of repository dicts with nameWithOwner, description, repositoryTopics

    Returns:
        Dict keyed by nameWithOwner with {purpose, use_case, unusual_applications}, or None on error
    """
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        logger.error("DEEPSEEK_API_KEY not set")
        return None

    # Build compact repo list
    repo_list_str = ""
    for i, repo in enumerate(repos, 1):
        topics = ", ".join([t["topic"]["name"] for t in repo.get("repositoryTopics", {}).get("nodes", [])])
        desc = repo.get("description") or "No description"
        repo_list_str += f"{i}. {repo['nameWithOwner']} | {desc} | topics: {topics}\n"

    user_prompt = f"""Analyze these uncategorized GitHub repositories and generate structured summaries.
For each repo, provide:
- purpose: What is the primary purpose of this project?
- use_case: What is a suggested use case for this project?
- unusual_applications: An array of 3 possible unusual or creative applications

Return ONLY valid JSON with this structure:
{{
  "repos": [
    {{
      "nameWithOwner": "owner/repo",
      "purpose": "...",
      "use_case": "...",
      "unusual_applications": ["...", "...", "..."]
    }}
  ]
}}

Repositories to analyze:
{repo_list_str}"""

    try:
        response = requests.post(
            "https://api.deepseek.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "deepseek-chat",
                "messages": [
                    {
                        "role": "system",
                        "content": "You are a technical analyst for a GitHub repository discovery tool. Return only valid JSON with no explanation.",
                    },
                    {"role": "user", "content": user_prompt},
                ],
                "response_format": {"type": "json_object"},
            },
            timeout=30,
        )

        if response.status_code != 200:
            logger.error(f"DeepSeek API error: {response.status_code} - {response.text}")
            return None

        result = response.json()
        content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
        if not content:
            logger.error("No content in DeepSeek response")
            return None

        parsed = json.loads(content)
        summaries = {}
        for repo_data in parsed.get("repos", []):
            summaries[repo_data["nameWithOwner"]] = {
                "purpose": repo_data.get("purpose", ""),
                "use_case": repo_data.get("use_case", ""),
                "unusual_applications": repo_data.get("unusual_applications", []),
            }
        return summaries

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse DeepSeek response: {e}")
        return None
    except requests.RequestException as e:
        logger.error(f"DeepSeek request failed: {e}")
        return None


def format_discovery_comment(repos: list[dict], summaries: dict[str, dict]) -> str:
    """
    Format repositories as markdown comment with AI summaries.

    Args:
        repos: List of repository dicts
        summaries: Dict of nameWithOwner -> {purpose, use_case, unusual_applications}

    Returns:
        Markdown string for GitHub issue comment
    """
    comment = "### New Discovery Batch\n\n"

    for repo in repos:
        name = repo["nameWithOwner"]
        desc = repo.get("description") or "No description"
        topics = ", ".join([t["topic"]["name"] for t in repo.get("repositoryTopics", {}).get("nodes", [])])

        comment += f"- **{name}**\n"
        comment += f"  - **Description:** {desc}\n"
        comment += f"  - **Topics:** {topics}\n"

        if name in summaries:
            summary = summaries[name]
            comment += f"  - **Purpose:** {summary.get('purpose', 'N/A')}\n"
            comment += f"  - **Suggested Use Case:** {summary.get('use_case', 'N/A')}\n"
            comment += "  - **Unusual Applications:**\n"
            for app in summary.get("unusual_applications", []):
                comment += f"    1. {app}\n"
        comment += "\n"

    return comment


def main():
    try:
        client = GitHubClient()
        logger.info("Searching for popular repositories...")
        data = search_popular_repos(client)

        if not data or "data" not in data:
            logger.error("Failed to fetch repositories")
            return

        uncategorized = [r for r in data["data"]["search"]["nodes"] if not is_categorized(r)]

        if not uncategorized:
            logger.info("No uncategorized popular repositories found")
            # Write GITHUB_OUTPUT
            if "GITHUB_OUTPUT" in os.environ:
                with open(os.environ["GITHUB_OUTPUT"], "a") as f:
                    date_suffix = datetime.date.today().strftime("%Y-W%V")
                    f.write(f"repos_found=0\n")
                    f.write(f"repos_reported=0\n")
                    f.write(f"date_suffix={date_suffix}\n")
            return

        logger.info(f"Found {len(uncategorized)} uncategorized repos")

        # Create or get weekly issues
        uncategorized_issue_num = get_or_create_weekly_issue(client)
        discovery_issue_num = get_or_create_weekly_discovery_issue(client)

        if not uncategorized_issue_num or not discovery_issue_num:
            logger.error("Failed to create/get weekly issues")
            return

        # Get already reported repos
        already_uncategorized = get_already_reported_repos(client, uncategorized_issue_num)
        already_discovered = get_already_reported_repos(client, discovery_issue_num)

        # Filter to new repos only
        new_repos = [
            r
            for r in uncategorized
            if r["nameWithOwner"] not in already_discovered
            and r["nameWithOwner"] not in already_uncategorized
        ]

        if not new_repos:
            logger.info("All uncategorized repos have already been reported")
            # Write GITHUB_OUTPUT
            if "GITHUB_OUTPUT" in os.environ:
                with open(os.environ["GITHUB_OUTPUT"], "a") as f:
                    date_suffix = datetime.date.today().strftime("%Y-W%V")
                    f.write(f"repos_found={len(uncategorized)}\n")
                    f.write(f"repos_reported=0\n")
                    f.write(f"date_suffix={date_suffix}\n")
            return

        logger.info(f"Preparing to report {len(new_repos)} new repos")

        # Get AI summaries
        summaries = call_deepseek_summaries(new_repos)

        # Post to discovery issue
        if summaries:
            comment = format_discovery_comment(new_repos, summaries)
            try:
                from github_star_organizer.issue_manager import run_command
                run_command(["gh", "issue", "comment", discovery_issue_num, "--body", comment])
                logger.info(f"Posted discovery summary to issue #{discovery_issue_num}")
            except IssueError as e:
                logger.error(f"Failed to post discovery comment: {e}")
        else:
            logger.warning("DeepSeek failed; discovery issue not updated")

        # Post to uncategorized issue
        report_uncategorized_repos(client, uncategorized_issue_num, new_repos)
        logger.info(f"Reported {len(new_repos)} repos to uncategorized issue #{uncategorized_issue_num}")

        # Write GITHUB_OUTPUT
        if "GITHUB_OUTPUT" in os.environ:
            with open(os.environ["GITHUB_OUTPUT"], "a") as f:
                date_suffix = datetime.date.today().strftime("%Y-W%V")
                f.write(f"repos_found={len(uncategorized)}\n")
                f.write(f"repos_reported={len(new_repos)}\n")
                f.write(f"date_suffix={date_suffix}\n")

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
