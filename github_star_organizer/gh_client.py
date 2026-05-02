import subprocess
import json
import sys


class GitHubAPIError(Exception):
    """Raised when GitHub API call fails."""
    pass


def run_query(query: str, variables: dict[str, str] | None = None) -> dict:
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
            cmd.extend(["-f", f"{key}={value}"])

    # Execute gh command
    result = subprocess.run(cmd, capture_output=True, text=True)

    # Check for command failures
    if result.returncode != 0:
        raise GitHubAPIError(f"GitHub API error: {result.stderr}")

    # Parse JSON response
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise GitHubAPIError(f"Invalid JSON response from GitHub: {e}")


class GitHubClient:
    """Wrapper for GitHub API operations via gh CLI."""

    def run_query(self, query: str, variables: dict[str, str] | None = None) -> dict:
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
