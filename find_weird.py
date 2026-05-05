import os
import json
import sys
import datetime
import requests
import threading
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


def get_model_specs(model_name: str) -> dict:
    """
    Fetch model specifications from DeepSeek API at runtime.

    Args:
        model_name: Model identifier (e.g., "deepseek-chat")

    Returns:
        Dict with model specs, or empty dict if unavailable
    """
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        return {}

    try:
        response = requests.get(
            "https://api.deepseek.com/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10,
        )

        if response.status_code != 200:
            logger.warning(f"Failed to fetch model specs: {response.status_code}")
            return {}

        data = response.json()
        # Find the model in the list
        for model in data.get("data", []):
            if model.get("id") == model_name:
                return {
                    "name": model.get("id"),
                    "created": model.get("created"),
                    "owned_by": model.get("owned_by"),
                    "permission": model.get("permission", [{}])[0].get("allow_create_engine", "N/A"),
                }

        logger.warning(f"Model {model_name} not found in API response")
        return {}

    except requests.RequestException as e:
        logger.warning(f"Failed to fetch model specs from API: {e}")
        return {}


def search_popular_repos(client):
    """Search for uncategorized repositories created after 2023 with lower star threshold"""
    query = """
    query {
      search(query: "created:>2023-01-01 stars:>1000", type: REPOSITORY, first: 100) {
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


def identify_interesting_repos(repos: list[dict], model: str = "deepseek") -> list[str] | None:
    """
    Ask an LLM to identify 3 unique/strange repos from a list.
    Returns list of nameWithOwner strings for the interesting repos.

    Args:
        repos: List of repository dicts with nameWithOwner, description, repositoryTopics
        model: "deepseek" or "ollama"

    Returns:
        List of nameWithOwner strings for 3 interesting repos, or None on error
    """
    if not repos:
        return None

    # Build compact repo list
    repo_list_str = ""
    for i, repo in enumerate(repos, 1):
        topics = ", ".join([t["topic"]["name"] for t in repo.get("repositoryTopics", {}).get("nodes", [])])
        desc = repo.get("description") or "No description"
        repo_list_str += f"{i}. {repo['nameWithOwner']} | {desc} | topics: {topics}\n"

    user_prompt = f"""Analyze these GitHub repositories and identify exactly 3 that are most unique, unusual, or strange.
Look for repos that do unconventional things, have surprising use cases, or solve problems in creative ways.

Return ONLY valid JSON with this structure (no explanation):
{{
  "interesting_repos": [
    "owner/repo1",
    "owner/repo2",
    "owner/repo3"
  ]
}}

Repositories to analyze:
{repo_list_str}"""

    if model == "deepseek":
        return _identify_via_deepseek(user_prompt)
    else:
        return _identify_via_ollama(user_prompt)


def _identify_via_deepseek(prompt: str) -> list[str] | None:
    """Call DeepSeek to identify interesting repos"""
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        logger.warning("DEEPSEEK_API_KEY not set")
        return None

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
                        "content": "You are a technical analyst. Return only valid JSON with no explanation.",
                    },
                    {"role": "user", "content": prompt},
                ],
                "response_format": {"type": "json_object"},
            },
            timeout=30,
        )

        if response.status_code != 200:
            logger.warning(f"DeepSeek API error: {response.status_code}")
            return None

        result = response.json()
        content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
        if not content:
            logger.warning("No content in DeepSeek response")
            return None

        parsed = json.loads(content)
        return parsed.get("interesting_repos", [])

    except (json.JSONDecodeError, requests.RequestException) as e:
        logger.warning(f"DeepSeek identification failed: {e}")
        return None


def _identify_via_ollama(prompt: str) -> list[str] | None:
    """Call Ollama to identify interesting repos"""
    api_key = os.getenv("OLLAMA_API_KEY")
    if not api_key:
        logger.warning("OLLAMA_API_KEY not set")
        return None

    try:
        response = requests.post(
            "https://ollama.com/api/chat",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "qwen3.5",
                "messages": [
                    {
                        "role": "system",
                        "content": "You are a technical analyst. Return only valid JSON with no explanation.",
                    },
                    {"role": "user", "content": prompt},
                ],
                "stream": False,
            },
            timeout=30,
        )

        if response.status_code != 200:
            logger.warning(f"Ollama API error: {response.status_code}")
            return None

        result = response.json()
        content = result.get("message", {}).get("content", "")
        if not content:
            logger.warning("No content in Ollama response")
            return None

        parsed = json.loads(content)
        return parsed.get("interesting_repos", [])

    except (json.JSONDecodeError, requests.RequestException) as e:
        logger.warning(f"Ollama identification failed: {e}")
        return None


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


def call_ollama_summaries(repos: list[dict]) -> dict[str, dict] | None:
    """
    Call Ollama Cloud API to generate summaries for uncategorized repos.

    Args:
        repos: List of repository dicts

    Returns:
        Dict keyed by nameWithOwner with {purpose, use_case, unusual_applications}, or None on error
    """
    api_key = os.getenv("OLLAMA_API_KEY")
    if not api_key:
        logger.warning("OLLAMA_API_KEY not set, skipping Ollama analysis")
        return None

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
            "https://ollama.com/api/chat",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "qwen3.5",
                "messages": [
                    {
                        "role": "system",
                        "content": "You are a technical analyst for a GitHub repository discovery tool. Return only valid JSON with no explanation.",
                    },
                    {"role": "user", "content": user_prompt},
                ],
                "stream": False,
            },
            timeout=30,
        )

        if response.status_code != 200:
            logger.warning(f"Ollama API error: {response.status_code}")
            return None

        result = response.json()
        # Ollama API response format: {"message": {"role": "assistant", "content": "..."}}
        content = result.get("message", {}).get("content", "")
        if not content:
            logger.warning("No content in Ollama response")
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
        logger.warning(f"Failed to parse Ollama response: {e}")
        return None
    except requests.RequestException as e:
        logger.warning(f"Ollama request failed: {e}")
        return None


def identify_and_summarize_interesting(repos: list[dict]) -> tuple[list[dict], dict[str, dict[str, dict]]] | None:
    """
    Two-stage discovery: identify interesting repos, then generate summaries.

    1. Split top 20 repos: even indices to DeepSeek, odd to Ollama
    2. Each model identifies 3 unique/strange repos from their subset
    3. Consolidate and deduplicate (aim for ~6 total unique)
    4. Generate detailed summaries for selected repos

    Args:
        repos: List of uncategorized repository dicts

    Returns:
        Tuple of (selected_repos_list, model_summaries_dict) or None on error
    """
    if not repos:
        return None

    # Limit to top 20 for analysis
    top_20 = repos[:20]
    logger.info(f"Analyzing top 20 repos with dual-model approach")

    # Split by even/odd indices
    even_repos = [repo for i, repo in enumerate(top_20) if i % 2 == 0]  # indices 0,2,4,6...
    odd_repos = [repo for i, repo in enumerate(top_20) if i % 2 == 1]   # indices 1,3,5,7...

    logger.info(f"DeepSeek analyzing {len(even_repos)} repos (even indices)")
    logger.info(f"Ollama analyzing {len(odd_repos)} repos (odd indices)")

    # Identify interesting repos from each subset
    deepseek_interesting = identify_interesting_repos(even_repos, model="deepseek")
    ollama_interesting = identify_interesting_repos(odd_repos, model="ollama")

    # Consolidate results
    interesting_names = set()
    if deepseek_interesting:
        interesting_names.update(deepseek_interesting)
        logger.info(f"DeepSeek identified: {deepseek_interesting}")
    if ollama_interesting:
        interesting_names.update(ollama_interesting)
        logger.info(f"Ollama identified: {ollama_interesting}")

    if not interesting_names:
        logger.warning("No interesting repos identified by either model")
        return None

    logger.info(f"Consolidated {len(interesting_names)} unique interesting repos")

    # Filter original repos to only selected ones
    selected_repos = [r for r in repos if r["nameWithOwner"] in interesting_names]
    logger.info(f"Selected {len(selected_repos)} repos for detailed analysis")

    # Generate summaries for selected repos
    summaries = run_parallel_summaries(selected_repos)

    return (selected_repos, summaries)


def run_parallel_summaries(repos: list[dict]) -> dict[str, dict[str, dict]]:
    """
    Run DeepSeek and Ollama summaries in parallel.

    Args:
        repos: List of repository dicts

    Returns:
        Dict with keys 'deepseek' and 'ollama', each containing nameWithOwner -> {purpose, use_case, unusual_applications}
    """
    results = {}
    errors = []

    def call_deepseek():
        try:
            summaries = call_deepseek_summaries(repos)
            if summaries:
                results['deepseek'] = summaries
            else:
                errors.append("DeepSeek")
        except Exception as e:
            logger.warning(f"DeepSeek thread error: {e}")
            errors.append("DeepSeek")

    def call_ollama():
        try:
            summaries = call_ollama_summaries(repos)
            if summaries:
                results['ollama'] = summaries
            else:
                logger.warning("Ollama returned no summaries")
        except Exception as e:
            logger.warning(f"Ollama thread error: {e}")

    # Run both in parallel
    deepseek_thread = threading.Thread(target=call_deepseek)
    ollama_thread = threading.Thread(target=call_ollama)

    deepseek_thread.start()
    ollama_thread.start()

    deepseek_thread.join()
    ollama_thread.join()

    if errors:
        logger.warning(f"Failed models: {', '.join(errors)}")

    return results


def format_discovery_comment(repos: list[dict], model_summaries: dict[str, dict[str, dict]]) -> str:
    """
    Format repositories as markdown comment with AI summaries from multiple models.

    Args:
        repos: List of repository dicts
        model_summaries: Dict with keys 'deepseek' and/or 'ollama', each containing nameWithOwner -> {purpose, use_case, unusual_applications}

    Returns:
        Markdown string for GitHub issue comment
    """
    comment = f"### New Discovery Batch\n\n"

    # Process DeepSeek results
    if 'deepseek' in model_summaries and model_summaries['deepseek']:
        deepseek_specs = get_model_specs("deepseek-chat")
        comment += f"#### DeepSeek Analysis\n\n"
        comment += f"**Model:** `deepseek-chat`\n"
        if deepseek_specs:
            if deepseek_specs.get('owned_by'):
                comment += f"**Provider:** {deepseek_specs.get('owned_by')}\n"
            if deepseek_specs.get('created'):
                comment += f"**Created:** {deepseek_specs.get('created')}\n"
        comment += "\n"

        summaries = model_summaries['deepseek']
        for repo in repos:
            name = repo["nameWithOwner"]
            if name in summaries:
                desc = repo.get("description") or "No description"
                topics = ", ".join([t["topic"]["name"] for t in repo.get("repositoryTopics", {}).get("nodes", [])])
                repo_url = f"https://github.com/{name}"

                comment += f"- **[{name}]({repo_url})**\n"
                comment += f"  - **Description:** {desc}\n"
                comment += f"  - **Topics:** {topics}\n"

                summary = summaries[name]
                comment += f"  - **Purpose:** {summary.get('purpose', 'N/A')}\n"
                comment += f"  - **Suggested Use Case:** {summary.get('use_case', 'N/A')}\n"
                comment += "  - **Unusual Applications:**\n"
                for app in summary.get("unusual_applications", []):
                    comment += f"    - {app}\n"
                comment += "\n"

    # Process Ollama results
    if 'ollama' in model_summaries and model_summaries['ollama']:
        comment += f"#### Ollama Cloud Analysis (Qwen3.5)\n\n"
        comment += f"**Model:** `qwen3.5`\n"
        comment += f"**Provider:** Ollama Cloud\n\n"

        summaries = model_summaries['ollama']
        for repo in repos:
            name = repo["nameWithOwner"]
            if name in summaries:
                desc = repo.get("description") or "No description"
                topics = ", ".join([t["topic"]["name"] for t in repo.get("repositoryTopics", {}).get("nodes", [])])
                repo_url = f"https://github.com/{name}"

                comment += f"- **[{name}]({repo_url})**\n"
                comment += f"  - **Description:** {desc}\n"
                comment += f"  - **Topics:** {topics}\n"

                summary = summaries[name]
                comment += f"  - **Purpose:** {summary.get('purpose', 'N/A')}\n"
                comment += f"  - **Suggested Use Case:** {summary.get('use_case', 'N/A')}\n"
                comment += "  - **Unusual Applications:**\n"
                for app in summary.get("unusual_applications", []):
                    comment += f"    - {app}\n"
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

        logger.info(f"Preparing to analyze {len(new_repos)} new repos")

        # Two-stage discovery: identify interesting repos, then summarize them
        result = identify_and_summarize_interesting(new_repos)

        if result:
            selected_repos, model_summaries = result
            logger.info(f"Selected {len(selected_repos)} interesting repos for discovery")

            # Post to discovery issue
            if model_summaries:
                comment = format_discovery_comment(selected_repos, model_summaries)
                try:
                    from github_star_organizer.issue_manager import run_command
                    run_command(["gh", "issue", "comment", discovery_issue_num, "--body", comment])
                    logger.info(f"Posted discovery summary to issue #{discovery_issue_num}")
                except IssueError as e:
                    logger.error(f"Failed to post discovery comment: {e}")
            else:
                logger.warning("Summary generation failed; discovery issue not updated")
        else:
            logger.warning("Repo identification failed; discovery issue not updated")

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
