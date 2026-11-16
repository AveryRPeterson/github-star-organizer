import subprocess
import json
import re
import sys
import time


class GitHubAPIError(Exception):
    """Raised when GitHub API call fails."""
    pass


# Transient server-side failures worth retrying (gateway errors and timeouts).
_TRANSIENT = re.compile(r"HTTP (502|503|504)|timed? ?out|connection reset|EOF", re.I)
MAX_ATTEMPTS = 4
BACKOFF_SECONDS = 2.0


class GitHubAuthError(GitHubAPIError):
    """Raised when GH_TOKEN is missing, expired, or revoked (HTTP 401)."""
    pass


def run_query(query: str, variables: dict[str, str | list[str]] | None = None) -> dict:
    """
    Execute a GraphQL query against GitHub API via gh CLI.

    Args:
        query: GraphQL query string
        variables: Optional dict of query variables (key=value pairs)

    Returns:
        Parsed JSON response dict

    Raises:
        GitHubAPIError: If gh command fails or response is invalid JSON
    """
    cmd = ["gh", "api", "graphql", "-f", f"query={query}"]

    # Add variables to command
    if variables:
        for key, value in variables.items():
            if isinstance(value, (list, tuple)):
                for item in value:  # gh encodes key[]=v as a JSON array
                    cmd.extend(["-f", f"{key}[]={item}"])
            else:
                cmd.extend(["-f", f"{key}={value}"])

    # Execute gh command, retrying transient 5xx/timeouts with exponential backoff
    for attempt in range(1, MAX_ATTEMPTS + 1):
        result = subprocess.run(cmd, capture_output=True, text=True,
                                encoding="utf-8", errors="replace")
        stderr = result.stderr or ""
        if result.returncode == 0 or attempt == MAX_ATTEMPTS or not _TRANSIENT.search(stderr):
            break
        time.sleep(BACKOFF_SECONDS * 2 ** (attempt - 1))

    # Check for command failures
    if result.returncode != 0:
        if "401" in stderr or "Bad credentials" in stderr:
            raise GitHubAuthError(
                "GH_TOKEN is expired, revoked, or invalid (HTTP 401). "
                "Rotate the GH_TOKEN repository secret."
            )
        raise GitHubAPIError(f"GitHub API error: {result.stderr}")

    # Parse JSON response
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise GitHubAPIError(f"Invalid JSON response from GitHub: {e}")


class GitHubClient:
    """Wrapper for GitHub API operations via gh CLI."""

    def run_query(self, query: str, variables: dict[str, str | list[str]] | None = None) -> dict:
        """
        Execute a GraphQL query against GitHub API.

        Args:
            query: GraphQL query string
            variables: Optional dict of query variables

        Returns:
            Parsed JSON response dict

        Raises:
            GitHubAPIError: If gh command fails
        """
        return run_query(query, variables)
