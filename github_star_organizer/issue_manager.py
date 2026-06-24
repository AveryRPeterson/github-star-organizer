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


def _get_or_create_weekly_issue(
    client, title_prefix: str, body: str, error_msg_prefix: str, create: bool = True
) -> str | None:
    """
    Common logic for creating and managing weekly tracking issues.

    - Searches for all open issues with the given title prefix (authored by user)
    - Returns the target issue for this week (by date)
    - Closes and consolidates duplicate issues from prior weeks

    Args:
        client: GitHubClient instance
        title_prefix: Prefix for the issue title (e.g., "Uncategorized Stars")
        body: Initial body text for the new issue
        error_msg_prefix: Prefix for the IssueError if creation fails
        create: If False, return None when no issue exists rather than creating one

    Returns:
        Issue number as string, or None if creation fails or create=False and no issue exists

    Raises:
        IssueError: If issue operations fail
    """
    date_str = datetime.date.today().strftime("%Y-W%V")
    target_title = f"{title_prefix}: {date_str}"

    # 1. Find all open issues with the given prefix authored by me
    try:
        res = run_command(["gh", "issue", "list", "--state", "open",
                          "--search", f'in:title "{title_prefix}" author:@me',
                          "--json", "number,title"])
        open_issues = json.loads(res) if res else []
        if not isinstance(open_issues, list):
            open_issues = []
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

    # 2. If target issue doesn't exist, create it (unless caller asked not to)
    if not target_issue_num:
        if not create:
            return None
        try:
            url = run_command(["gh", "issue", "create", "--title", target_title, "--body", body])
            target_issue_num = url.split("/")[-1]
        except IssueError as e:
            raise IssueError(f"{error_msg_prefix}: {e}")

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


def get_or_create_weekly_issue(client, create: bool = True) -> str | None:
    """
    Get or create the weekly uncategorized stars tracking issue.

    - Searches for all open "Uncategorized Stars" issues (authored by user)
    - Returns the target issue for this week (by date)
    - Closes and consolidates duplicate issues from prior weeks

    Args:
        client: GitHubClient instance
        create: If False, return None when no issue exists rather than creating one

    Returns:
        Issue number as string, or None if creation fails or create=False and no issue exists

    Raises:
        IssueError: If issue operations fail
    """
    body = "This issue tracks repositories that were skipped during the organization run because they did not match any existing keywords. Comments below contain batches of uncategorized repositories."
    return _get_or_create_weekly_issue(
        client,
        title_prefix="Uncategorized Stars",
        body=body,
        error_msg_prefix="Failed to create issue",
        create=create,
    )


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


def get_or_create_weekly_discovery_issue(client) -> str | None:
    """
    Get or create the weekly interesting discoveries tracking issue.

    Same lifecycle logic as get_or_create_weekly_issue but with title
    "Interesting Discoveries: YYYY-W##".

    Args:
        client: GitHubClient instance

    Returns:
        Issue number as string, or None if creation fails

    Raises:
        IssueError: If issue operations fail
    """
    body = "This issue tracks AI-generated summaries of popular uncategorized repositories discovered this week. Review the repos below, star any that interest you, then close this issue."
    return _get_or_create_weekly_issue(
        client,
        title_prefix="Interesting Discoveries",
        body=body,
        error_msg_prefix="Failed to create discovery issue",
    )


def create_discovery_issue(repo: dict, model_summaries: dict) -> str:
    """
    Create a GitHub issue for a single discovered repository.

    Issue title: "Discovered: owner/repo"
    Body includes star link, metadata, and all available model analyses.

    Args:
        repo: Repository dict with nameWithOwner, description, repositoryTopics
        model_summaries: Dict with keys 'deepseek' and/or 'ollama', each mapping
                         nameWithOwner -> {purpose, use_case, unusual_applications}

    Returns:
        Created issue number as string

    Raises:
        IssueError: If issue creation fails
    """
    name = repo["nameWithOwner"]
    desc = repo.get("description") or "No description"
    repo_url = f"https://github.com/{name}"
    today = datetime.date.today().isoformat()

    # Language ratio: "Python 78%, JavaScript 14%, Shell 8%"
    primary_lang = (repo.get("primaryLanguage") or {}).get("name")
    lang_edges = repo.get("languages", {}).get("edges", [])
    total_size = repo.get("languages", {}).get("totalSize") or 0
    if lang_edges and total_size:
        lang_ratio = ", ".join(
            f"{e['node']['name']} {round(e['size'] / total_size * 100)}%"
            for e in lang_edges
        )
    elif primary_lang:
        lang_ratio = primary_lang
    else:
        lang_ratio = None

    license_name = (repo.get("licenseInfo") or {}).get("name")
    updated_at = (repo.get("updatedAt") or "")[:10]  # YYYY-MM-DD
    homepage = repo.get("homepageUrl") or None

    body = f"## {name}\n\n"
    body += f"**[⭐ View & Star on GitHub]({repo_url})**\n\n"
    body += f"**Description:** {desc}\n"
    if lang_ratio:
        body += f"**Language:** {lang_ratio}\n"
    if license_name:
        body += f"**License:** {license_name}\n"
    body += f"**Last Updated:** {updated_at}\n"
    if homepage:
        body += f"**Homepage:** {homepage}\n"
    body += "\n"
    body += "---\n\n"

    # Get analysis for this repo (flat dict format: nameWithOwner -> {purpose, use_case, unusual_applications, provider, model})
    if name in model_summaries:
        s = model_summaries[name]
        body += "## Analysis\n\n"
        body += f"**Purpose:** {s.get('purpose', 'N/A')}\n\n"
        body += f"**Suggested Use Case:** {s.get('use_case', 'N/A')}\n\n"
        body += "**Unusual Applications:**\n"
        for app in s.get("unusual_applications", []):
            body += f"- {app}\n"
        body += "\n"
        # Include provider and model at the end
        provider = s.get('provider', 'Unknown')
        model = s.get('model', 'Unknown')
        body += f"*Analysis provided by {provider} ({model})*\n\n"

    body += f"---\n*Discovered on {today}*\n"

    try:
        url = run_command(["gh", "issue", "create",
                           "--title", f"Discovered: {name}",
                           "--body", body])
        return url.split("/")[-1]
    except IssueError as e:
        raise IssueError(f"Failed to create discovery issue for {name}: {e}")


def augment_discovery_issue(issue_number: str, model_name: str, summary: dict) -> None:
    """
    Add a comment to an existing discovery issue with additional model analysis.

    Used when a repo is re-surfaced in a future run and an issue already exists.

    Args:
        issue_number: Existing GitHub issue number
        model_name: Display name for the model (e.g. "DeepSeek", "Ollama")
        summary: Dict with purpose, use_case, unusual_applications keys

    Raises:
        IssueError: If comment posting fails
    """
    comment = f"### Additional Analysis — {model_name}\n\n"
    comment += f"**Purpose:** {summary.get('purpose', 'N/A')}\n\n"
    comment += f"**Suggested Use Case:** {summary.get('use_case', 'N/A')}\n\n"
    comment += "**Unusual Applications:**\n"
    for app in summary.get("unusual_applications", []):
        comment += f"- {app}\n"

    try:
        run_command(["gh", "issue", "comment", issue_number, "--body", comment])
    except IssueError as e:
        raise IssueError(f"Failed to augment issue #{issue_number}: {e}")
