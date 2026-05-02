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
