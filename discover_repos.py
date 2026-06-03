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
    report_uncategorized_repos,
    create_discovery_issue,
    augment_discovery_issue,
    IssueError,
)
from github_star_organizer import state_db


logger = get_logger("find_weird")


def get_current_stars() -> set[str]:
    """
    Fetch user's current starred repositories.
    
    Returns:
        Set of "owner/repo" strings the user has starred
    """
    api_key = os.getenv("GITHUB_TOKEN")
    if not api_key:
        logger.warning("GITHUB_TOKEN not set, cannot fetch current stars")
        return set()
    
    try:
        # Paginate through all starred repos (max 100 per page)
        starred = set()
        page = 1
        while True:
            response = requests.get(
                f"https://api.github.com/users/AveryRPeterson/starred",
                params={"per_page": 100, "page": page},
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Accept": "application/vnd.github.v3+json"
                },
                timeout=10,
            )
            if response.status_code != 200:
                logger.warning(f"Failed to fetch stars: {response.status_code}")
                break
            
            data = response.json()
            if not data:
                break
                
            for repo in data:
                starred.add(repo["full_name"])
            
            if len(data) < 100:
                break
            page += 1
        
        logger.info(f"Found {len(starred)} current stars")
        return starred
        
    except requests.RequestException as e:
        logger.warning(f"Failed to fetch current stars: {e}")
        return set()


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
            primaryLanguage { name }
            languages(first: 5, orderBy: {field: SIZE, direction: DESC}) {
              edges { size node { name } }
              totalSize
            }
            licenseInfo { name }
            updatedAt
            homepageUrl
          }
        }
      }
    }
    """
    return client.run_query(query)


def is_categorized(repo):
    """Check if repo is already categorized"""
    return categorize(repo) is not None


def identify_interesting_repos(repos: list[dict], model: str = "deepseek", current_stars: set[str] | None = None, count: int = 3) -> list[str] | None:
    """
    Ask an LLM to identify unique/strange repos from a list.
    Returns list of nameWithOwner strings for the interesting repos.

    Args:
        repos: List of repository dicts with nameWithOwner, description, repositoryTopics
        model: "deepseek" or "ollama"
        current_stars: Set of repos already starred by user (to exclude from suggestions)
        count: Number of repos to identify

    Returns:
        List of nameWithOwner strings for interesting repos, or None on error
    """
    if not repos:
        return None

    # Build compact repo list
    repo_list_str = ""
    for i, repo in enumerate(repos, 1):
        lang = (repo.get("primaryLanguage") or {}).get("name") or "Unknown"
        desc = repo.get("description") or "No description"
        repo_list_str += f"{i}. {repo['nameWithOwner']} | {desc} | language: {lang}\n"

    # Add info about already starred repos to the prompt
    starred_note = ""
    if current_stars:
        starred_list = sorted(current_stars)
        starred_note = f"""
IMPORTANT: The user has already starred these repos - do NOT suggest them:
{', '.join(starred_list)}

"""

    user_prompt = f"""Analyze these GitHub repositories and identify exactly {count} that are most unique, unusual, or strange.
Look for repos that do unconventional things, have surprising use cases, or solve problems in creative ways.

{starred_note}Return ONLY valid JSON with this structure (no explanation):
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


def get_available_ollama_models(api_key: str) -> list[str] | None:
    """
    Discover available Ollama Cloud API models dynamically.

    Filters for chat/text models and excludes vision, audio, video, and image models.
    Tries to infer model capabilities from names and sorts by preference.

    Args:
        api_key: Ollama Cloud API key

    Returns:
        List of available chat model names sorted by preference, or None on error
    """
    try:
        response = requests.get(
            "https://ollama.com/api/tags",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10,
        )

        if response.status_code != 200:
            logger.warning(f"Failed to fetch Ollama models: {response.status_code}")
            return None

        data = response.json()
        all_models = [m.get("name") for m in data.get("models", []) if m.get("name")]

        if not all_models:
            logger.warning("No models returned from Ollama /api/tags")
            return None

        # Filter out non-chat models (vision, audio, video, image variants)
        excluded_keywords = {"vision", "audio", "video", "image", "embed"}
        chat_models = [
            m for m in all_models
            if not any(kw in m.lower() for kw in excluded_keywords)
        ]

        if not chat_models:
            logger.warning(f"No chat models found. All models: {all_models}")
            return None

        # Sort by preference: prefer reasoning/code > larger models > general chat
        def model_priority(name: str) -> tuple:
            """Return priority tuple for sorting (lower = better)."""
            name_lower = name.lower()

            # Prefer reasoning models
            if "reasoning" in name_lower or "r1" in name_lower:
                priority = 0
            # Then code/technical models
            elif "code" in name_lower or "coder" in name_lower:
                priority = 1
            # Then larger general models
            elif "70b" in name_lower or "72b" in name_lower:
                priority = 2
            elif "13b" in name_lower or "34b" in name_lower:
                priority = 3
            # Default for unknown size
            else:
                priority = 4

            # Secondary sort by name (alphabetical) for same priority
            return (priority, name)

        sorted_models = sorted(chat_models, key=model_priority)
        logger.info(f"Discovered {len(sorted_models)} chat models: {sorted_models}")
        return sorted_models

    except requests.RequestException as e:
        logger.warning(f"Failed to discover Ollama models: {e}")
        return None


def _identify_via_ollama(prompt: str) -> list[str] | None:
    """Call Ollama to identify interesting repos with dynamic model discovery and fallback to DeepSeek"""
    api_key = os.getenv("OLLAMA_API_KEY")
    if not api_key:
        logger.warning("OLLAMA_API_KEY not set, falling back to DeepSeek")
        return _identify_via_deepseek(prompt)

    # Dynamically discover available models
    available_models = get_available_ollama_models(api_key)
    if not available_models:
        logger.warning("No available Ollama models, falling back to DeepSeek")
        return _identify_via_deepseek(prompt)

    for model in available_models:
        try:
            logger.info(f"Trying Ollama with model: {model}")
            response = requests.post(
                "https://ollama.com/api/chat",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
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

            if response.status_code == 200:
                result = response.json()
                content = result.get("message", {}).get("content", "")
                if content:
                    try:
                        parsed = json.loads(content)
                        repos = parsed.get("interesting_repos", [])
                        if repos:
                            logger.info(f"Ollama {model} successful")
                            return repos
                    except json.JSONDecodeError:
                        logger.warning(f"Ollama {model} returned invalid JSON")
                        continue
            elif response.status_code == 403:
                logger.warning(f"Ollama {model} not accessible (subscription required or no access)")
                continue
            else:
                logger.warning(f"Ollama {model} API error: {response.status_code}")
        except requests.RequestException as e:
            logger.warning(f"Ollama {model} request failed: {e}")
            continue

    # All Ollama models exhausted, fall back to DeepSeek
    logger.warning("All Ollama models exhausted, falling back to DeepSeek")
    return _identify_via_deepseek(prompt)


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
        lang = (repo.get("primaryLanguage") or {}).get("name") or "Unknown"
        desc = repo.get("description") or "No description"
        repo_list_str += f"{i}. {repo['nameWithOwner']} | {desc} | language: {lang}\n"

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
    Call Ollama Cloud API to generate summaries with 3-tier fallback to DeepSeek.

    Args:
        repos: List of repository dicts

    Returns:
        Dict keyed by nameWithOwner with {purpose, use_case, unusual_applications}, or None on error
    """
    api_key = os.getenv("OLLAMA_API_KEY")
    if not api_key:
        logger.warning("OLLAMA_API_KEY not set, falling back to DeepSeek")
        return call_deepseek_summaries(repos)

    repo_list_str = ""
    for i, repo in enumerate(repos, 1):
        lang = (repo.get("primaryLanguage") or {}).get("name") or "Unknown"
        desc = repo.get("description") or "No description"
        repo_list_str += f"{i}. {repo['nameWithOwner']} | {desc} | language: {lang}\n"

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

    # Dynamically discover available models
    available_models = get_available_ollama_models(api_key)
    if not available_models:
        logger.warning("No available Ollama models, falling back to DeepSeek")
        return call_deepseek_summaries(repos)

    for model in available_models:
        try:
            logger.info(f"Trying Ollama with model: {model}")
            response = requests.post(
                "https://ollama.com/api/chat",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
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

            if response.status_code == 200:
                result = response.json()
                content = result.get("message", {}).get("content", "")
                if content:
                    try:
                        parsed = json.loads(content)
                        summaries = {}
                        for repo_data in parsed.get("repos", []):
                            summaries[repo_data["nameWithOwner"]] = {
                                "purpose": repo_data.get("purpose", ""),
                                "use_case": repo_data.get("use_case", ""),
                                "unusual_applications": repo_data.get("unusual_applications", []),
                            }
                        if summaries:
                            logger.info(f"Ollama {model} successful")
                            return summaries
                    except json.JSONDecodeError:
                        logger.warning(f"Ollama {model} returned invalid JSON")
                        continue
            elif response.status_code == 403:
                logger.warning(f"Ollama {model} not accessible (subscription required or no access)")
                continue
            else:
                logger.warning(f"Ollama {model} API error: {response.status_code}")
        except requests.RequestException as e:
            logger.warning(f"Ollama {model} request failed: {e}")
            continue

    # All Ollama tiers failed, fall back to DeepSeek
    logger.warning("All Ollama models exhausted, falling back to DeepSeek")
    return call_deepseek_summaries(repos)


def identify_and_summarize_interesting(repos: list[dict], current_stars: set[str] | None = None, total: int = 13) -> tuple[list[dict], dict[str, dict]] | None:
    """
    Two-stage discovery: identify interesting repos, then generate single summaries (Ollama primary, DeepSeek fallback).

    1. Identify top N unique repos using one model (Ollama with fallback)
    2. Generate detailed summaries for selected repos with the same provider
    3. Include provider/model metadata in each summary

    Args:
        repos: List of uncategorized repository dicts
        current_stars: Set of repos already starred by user (to include in prompt)
        total: Total number of repos to discover

    Returns:
        Tuple of (selected_repos_list, summaries_dict) where summaries_dict is
        {nameWithOwner: {purpose, use_case, unusual_applications, provider, model}} or None on error
    """
    if not repos:
        return None

    logger.info(f"Identifying {total} interesting repos from {len(repos)} candidates")

    # Identify interesting repos using single provider (Ollama primary, DeepSeek fallback)
    interesting_names = identify_interesting_repos(repos, model="ollama", current_stars=current_stars, count=total)
    if not interesting_names:
        logger.warning("Ollama identification failed, trying DeepSeek")
        interesting_names = identify_interesting_repos(repos, model="deepseek", current_stars=current_stars, count=total)

    if not interesting_names:
        logger.warning("No interesting repos identified")
        return None

    logger.info(f"Identified {len(interesting_names)} interesting repos: {interesting_names}")

    # Filter to selected repos (in original order)
    selected_set = set(interesting_names)
    selected_repos = [r for r in repos if r["nameWithOwner"] in selected_set]
    logger.info(f"Selected {len(selected_repos)} repos for detailed analysis")

    # Generate summaries using single provider (Ollama primary, DeepSeek fallback)
    summaries = get_single_model_summaries(selected_repos)

    return (selected_repos, summaries)


def get_single_model_summaries(repos: list[dict]) -> dict[str, dict]:
    """
    Generate summaries using single provider (Ollama primary, DeepSeek fallback).
    Includes provider and model metadata in each summary.

    Args:
        repos: List of repository dicts

    Returns:
        Dict with nameWithOwner -> {purpose, use_case, unusual_applications, provider, model}
    """
    # Try Ollama first
    summaries = call_ollama_summaries(repos)
    if summaries:
        # Add provider/model metadata to each summary
        for repo_name, summary in summaries.items():
            summary["provider"] = "Ollama"
            summary["model"] = "auto-selected"  # User will see actual model in logs
        logger.info("Using Ollama for summaries")
        return summaries

    # Fallback to DeepSeek
    logger.warning("Ollama summaries failed, falling back to DeepSeek")
    summaries = call_deepseek_summaries(repos)
    if summaries:
        for repo_name, summary in summaries.items():
            summary["provider"] = "DeepSeek"
            summary["model"] = "deepseek-chat"
        logger.info("Using DeepSeek for summaries")
        return summaries

    logger.error("Both Ollama and DeepSeek summaries failed")
    return {}



def main():
    try:
        state_db.init_db()
        client = GitHubClient()
        logger.info("Searching for popular repositories...")
        data = search_popular_repos(client)

        if not data or "data" not in data:
            logger.error("Failed to fetch repositories")
            return

        # Get all repos from search (both categorized and uncategorized)
        all_repos = data["data"]["search"]["nodes"]
        logger.info(f"Found {len(all_repos)} total repos in search")

        # Stage 1: Identify uncategorized repos for keyword growth
        uncategorized = [r for r in all_repos if not is_categorized(r)]
        logger.info(f"Found {len(uncategorized)} uncategorized repos (Stage 1: keyword growth)")

        # Get current stars for deduplication (fetch once, reused throughout)
        current_stars = get_current_stars()

        # Stage 1 dedup: use DB instead of parsing issue comments
        already_uncategorized = state_db.get_uncategorized_repos()
        new_uncategorized = [
            r for r in uncategorized
            if r["nameWithOwner"] not in already_uncategorized
        ]

        # Stage 2 dedup: use DB instead of searching discovery issue titles
        already_discovered = state_db.get_discovered_repos()
        new_all_repos = [
            r for r in all_repos
            if r["nameWithOwner"] not in already_discovered
            and r["nameWithOwner"] not in current_stars
        ]

        logger.info(f"Stage 1: {len(new_uncategorized)} new uncategorized repos for keywords")
        logger.info(f"Stage 2: {len(new_all_repos)} new repos available for interesting selection")

        # Report uncategorized repos (Stage 1) — only create issue when there's something new
        if new_uncategorized:
            issue_num = get_or_create_weekly_issue(client, create=False)
            if not issue_num:
                issue_num = get_or_create_weekly_issue(client, create=True)
            if issue_num:
                report_uncategorized_repos(client, issue_num, new_uncategorized)
                state_db.insert_uncategorized_repos(new_uncategorized, issue_num)
                logger.info(f"Reported {len(new_uncategorized)} repos to uncategorized issue #{issue_num}")

        # Two-stage discovery: identify interesting repos, then summarize (Stage 2 + 3)
        discovery_count = int(os.environ.get("DISCOVERY_COUNT", "13"))
        result = identify_and_summarize_interesting(new_all_repos, current_stars=current_stars, total=discovery_count)
        discovered_count = 0

        if result:
            selected_repos, model_summaries = result
            logger.info(f"Stage 2+3: Selected {len(selected_repos)} interesting repos for detailed analysis")

            if model_summaries:
                for repo in selected_repos:
                    name = repo["nameWithOwner"]
                    existing_issue_num = state_db.get_issue_number_for_discovered(name)
                    if existing_issue_num:
                        # Repo seen before — augment existing issue with any new model analyses
                        for model_key, display in [("deepseek", "DeepSeek"), ("ollama", "Ollama")]:
                            summary = model_summaries.get(model_key, {}).get(name)
                            if summary:
                                try:
                                    augment_discovery_issue(existing_issue_num, display, summary)
                                    logger.info(f"Augmented issue #{existing_issue_num} for {name}")
                                except IssueError as e:
                                    logger.warning(f"Failed to augment issue for {name}: {e}")
                    else:
                        try:
                            new_issue_num = create_discovery_issue(repo, model_summaries)
                            state_db.insert_discovered_repo(repo, model_summaries, new_issue_num)
                            discovered_count += 1
                            logger.info(f"Created discovery issue #{new_issue_num} for {name}")
                        except IssueError as e:
                            logger.error(f"Failed to create discovery issue for {name}: {e}")
            else:
                logger.warning("Summary generation failed; no discovery issues created")
        else:
            logger.warning("Repo identification failed; no discovery issues created")

        # Write GITHUB_OUTPUT
        if "GITHUB_OUTPUT" in os.environ:
            with open(os.environ["GITHUB_OUTPUT"], "a") as f:
                date_suffix = datetime.date.today().strftime("%Y-W%V")
                f.write(f"repos_found={len(uncategorized)}\n")
                f.write(f"repos_reported={len(new_uncategorized)}\n")
                f.write(f"repos_discovered={discovered_count}\n")
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
