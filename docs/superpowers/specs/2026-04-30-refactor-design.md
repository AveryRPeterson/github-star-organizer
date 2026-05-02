# GitHub Star Organizer Refactor Design

**Date:** 2026-04-30  
**Author:** Claude Code  
**Status:** Approved

## Overview

Refactor the `github-star-organizer` project to improve operational visibility, modularity, and test coverage. The refactor maintains existing functionality while introducing proper package structure, centralized logging, comprehensive testing, and enhanced GitHub Actions feedback.

## Goals (Prioritized)

1. **Operational Friction** — Reduce visibility gaps; users can see exactly what each automation run did
2. **General Modernization** — Type hints on key functions, comprehensive testing (unit + integration), modular structure
3. **Maintainability** — Eliminate code duplication, clear module responsibilities, easier to extend

## Current State

- 3 standalone scripts: `categorize.py`, `distill.py`, `find_weird.py`
- Duplicated code: GraphQL runner appears in both `categorize.py` and `find_weird.py`
- Issue management logic embedded in `categorize.py` (creating, closing, deduplicating comments)
- Basic unit tests for `categorize()` function only
- No integration tests
- No type hints
- Minimal logging (only print statements)
- No structured feedback from `distill.py` about what config changes were made

## Proposed Architecture

### Package Structure

```
github-star-organizer/
├── github_star_organizer/          # New package
│   ├── __init__.py
│   ├── gh_client.py                # Shared GitHub GraphQL client
│   ├── categorizer.py              # Categorization logic
│   ├── logger.py                   # Structured logging
│   ├── config.py                   # Config loading and validation
│   └── issue_manager.py            # Issue lifecycle management
├── tests/                          # New directory
│   ├── unit/
│   │   ├── test_gh_client.py
│   │   ├── test_categorizer.py
│   │   ├── test_config.py
│   │   └── test_issue_manager.py
│   └── integration/
│       └── test_workflows.py
├── categorize.py                   # Entry point (imports from package)
├── distill.py                      # Entry point (imports from package)
├── find_weird.py                   # Entry point (imports from package)
├── config.json                     # Unchanged
├── requirements.txt                # New: list dependencies
└── docs/superpowers/specs/         # This design doc
```

### Module Design

#### `github_star_organizer/gh_client.py`

**Responsibility:** Handle all GitHub GraphQL API interactions.

**Public API:**
```python
class GitHubAPIError(Exception):
    """Raised when GitHub API call fails."""
    pass

def run_query(query: str, variables: dict[str, str] | None = None) -> dict:
    """
    Execute a GraphQL query against GitHub API.
    
    Args:
        query: GraphQL query string
        variables: Optional dict of query variables
        
    Returns:
        Parsed JSON response
        
    Raises:
        GitHubAPIError: If API call fails
    """
```

**Eliminates:** Duplicate GraphQL runner code from `categorize.py` and `find_weird.py`.

#### `github_star_organizer/categorizer.py`

**Responsibility:** Repository categorization logic.

**Public API:**
```python
def categorize(repo: dict) -> str | None:
    """
    Categorize a repository based on name, description, and topics.
    
    Args:
        repo: Repository dict with keys: nameWithOwner, description, repositoryTopics
        
    Returns:
        Category name if match found, None otherwise
    """

def get_categorized_ids(client: GitHubClient) -> set[str]:
    """Fetch IDs of repositories already in user lists."""

def get_recent_stars(client: GitHubClient, limit: int = 50) -> list[dict]:
    """Fetch recent starred repositories."""
```

**Benefits:** Extracted from `categorize.py`, fully typed, testable in isolation.

#### `github_star_organizer/logger.py`

**Responsibility:** Provide consistent logging across all modules.

**Public API:**
```python
def get_logger(name: str) -> logging.Logger:
    """
    Get a configured logger for the given module name.
    
    Returns logger with timestamp, level, and message format suitable for GitHub Actions output.
    """
```

**Format:** `[INFO] 2026-04-30 12:34:56 - categorize.py: Categorizing repo X into AI Agents & LLMs`

#### `github_star_organizer/config.py`

**Responsibility:** Load and validate configuration.

**Public API:**
```python
class ConfigError(Exception):
    """Raised when config.json is invalid."""
    pass

def load_config() -> dict:
    """Load config.json, validate required fields, return parsed dict."""
```

**Validation:** Ensure `lists` and `keywords` dicts exist and have correct structure.

#### `github_star_organizer/issue_manager.py`

**Responsibility:** GitHub issue lifecycle management — creation, closure, comment handling, deduplication.

**Public API:**
```python
class IssueError(Exception):
    """Raised when issue operations fail."""
    pass

def get_or_create_weekly_issue(client: GitHubClient) -> str | None:
    """
    Get or create the weekly uncategorized stars tracking issue.
    
    - Searches for all open "Uncategorized Stars" issues (authored by user)
    - Returns the target issue for this week (by date)
    - Closes and consolidates duplicate issues from prior weeks
    
    Returns:
        Issue number as string, or None if creation fails
        
    Raises:
        IssueError: If issue operations fail
    """

def get_already_reported_repos(client: GitHubClient, issue_number: str) -> set[str]:
    """
    Extract repository names already mentioned in an issue's comments.
    
    Parses markdown format: "- **owner/repo**"
    
    Args:
        issue_number: GitHub issue number
        
    Returns:
        Set of "owner/repo" strings already reported
    """

def report_uncategorized_repos(client: GitHubClient, issue_number: str, repos: list[dict]) -> None:
    """
    Post a comment with uncategorized repositories to an issue.
    
    Args:
        issue_number: GitHub issue number
        repos: List of repository dicts (nameWithOwner, description, repositoryTopics)
        
    Raises:
        IssueError: If comment posting fails
    """

def close_issue(client: GitHubClient, issue_number: str, reason: str) -> None:
    """
    Close a GitHub issue with an optional comment.
    
    Args:
        issue_number: GitHub issue number
        reason: Reason for closing (e.g., "Config updated with new keywords")
        
    Raises:
        IssueError: If close operation fails
    """
```

**Benefits:** 
- Consolidates all issue-related logic (creation, closing, commenting, deduplication)
- Reusable from both `categorize.py` and `distill.py`
- Enables auto-close flow when PRs merge (distill.py calls `close_issue()` after success)
- Testable in isolation with mocked `GitHubClient`

### Error Handling Strategy

**Custom Exceptions:**
- `GitHubAPIError(message: str)` — GitHub API call failed (includes stderr for debugging)
- `ConfigError(message: str)` — config.json invalid or missing
- `CategorizationError(message: str)` — unexpected error during categorization
- `IssueError(message: str)` — GitHub issue operations failed (create, close, comment)

**Error Flow in Scripts:**

| Script | Catches | Behavior |
|--------|---------|----------|
| `categorize.py` | `GitHubAPIError`, `IssueError` | Log error, exit gracefully (no crashes) |
| `distill.py` | `DeepSeekError`, `json.JSONDecodeError`, `IssueError` | Log error, include in PR comment what failed; attempt issue close if possible |
| `find_weird.py` | `GitHubAPIError` | Log warning, continue searching |

### Testing Strategy

#### Unit Tests (`tests/unit/`)

**`test_categorizer.py`** — Expand existing tests:
- All existing tests preserved
- Add edge cases: missing description, empty topics, multiple matches (priority ordering)
- Add case-insensitivity tests
- Add dynamic category tests (categories not in hardcoded priority list)
- ~15 total tests

**`test_gh_client.py`** — New:
- Mock `subprocess.run` to simulate API responses
- Test successful query execution
- Test API error handling (non-zero return code)
- Test malformed JSON response handling
- ~8 tests

**`test_config.py`** — New:
- Test valid config loads correctly
- Test missing `lists` key raises `ConfigError`
- Test missing `keywords` key raises `ConfigError`
- Test invalid JSON raises `ConfigError`
- ~5 tests

**`test_issue_manager.py`** — New:
- Mock `GitHubClient` to simulate issue operations
- Test `get_or_create_weekly_issue()` creates issue when none exists
- Test `get_or_create_weekly_issue()` returns existing issue for this week
- Test `get_or_create_weekly_issue()` closes and consolidates old duplicate issues
- Test `get_already_reported_repos()` correctly parses markdown comments
- Test `report_uncategorized_repos()` posts formatted comments
- Test `close_issue()` closes issue with reason
- Test error handling when API calls fail
- ~12 tests

#### Integration Tests (`tests/integration/`)

**`test_workflows.py`** — New:
- Mock `gh` CLI and `requests` library
- Simulate full categorize workflow: fetch stars → categorize → update lists
- Simulate full distill workflow: fetch uncategorized → call DeepSeek → generate summary
- Test error scenarios (API down mid-workflow, DeepSeek timeout, bad response)
- Test logging output contains expected messages
- ~10 tests

### Logging & Visibility

**Logging Coverage:**
- `categorize.py`: "Fetching stars...", "Categorizing X into Y", "Skipping X (already categorized)", "Failed to categorize X: reason"
- `distill.py`: "Analyzing uncategorized repos...", "Updating config.json", "Generated summary: X keywords added, Y categories created"
- `find_weird.py`: "Searching popular repos...", "Found X uncategorized repos", warnings for API issues

**GitHub Actions Visibility:**

In `distill.yml` PR body:
```
## Distillation Summary

**Config Changes:**
- Added keywords to "AI Agents & LLMs": [autonomous-agents, foundation-models]
- Modified "Tools & CLI": removed [obsolete-tool], added [new-tool]
- Created new category "Game Development" with keywords: [unreal, godot, unity]

**Analysis Results:**
- Uncategorized repos analyzed: 12
- New keywords suggested: 18
- New categories created: 1
- Categories modified: 2

**Status:** ✅ Success
```

If `distill.py` fails:
```
## Distillation Failed

**Error:** DeepSeek API returned status 429 (rate limited)

**What we tried:** Analyzing 12 uncategorized repos with DeepSeek API

**Next steps:** Retry manually or check API quota
```

### Changes to Scripts

#### `categorize.py` (Entry Point)

```python
from github_star_organizer.gh_client import GitHubClient, GitHubAPIError
from github_star_organizer.categorizer import categorize, get_categorized_ids, get_recent_stars
from github_star_organizer.issue_manager import get_or_create_weekly_issue, get_already_reported_repos, report_uncategorized_repos, IssueError
from github_star_organizer.logger import get_logger
from github_star_organizer.config import load_config

logger = get_logger("categorize")

def main():
    load_config()  # Validates config
    client = GitHubClient()
    
    try:
        categorized = get_categorized_ids(client)
        stars = get_recent_stars(client)
        # ... rest of categorization logic
        
        # Handle uncategorized repos
        if skipped_repos:
            logger.info(f"Preparing to report {len(skipped_repos)} uncategorized repos...")
            issue_num = get_or_create_weekly_issue(client)
            if issue_num:
                already_reported = get_already_reported_repos(client, issue_num)
                new_to_report = [repo for repo in skipped_repos 
                                if repo['nameWithOwner'] not in already_reported]
                if new_to_report:
                    report_uncategorized_repos(client, issue_num, new_to_report)
                    logger.info(f"Comment added to issue #{issue_num}.")
    except (GitHubAPIError, IssueError) as e:
        logger.error(f"Error: {e}")
        sys.exit(1)
```

**Changes:**
- Import from `github_star_organizer` package
- Use `issue_manager` module for all issue operations (no inline logic)
- Use `logger` instead of `print`
- Proper error handling with `try/except`

#### `distill.py` (Entry Point)

```python
from github_star_organizer.gh_client import GitHubClient
from github_star_organizer.issue_manager import get_or_create_weekly_issue, close_issue, IssueError
from github_star_organizer.logger import get_logger

logger = get_logger("distill")

def main():
    client = GitHubClient()
    
    try:
        # ... existing distillation logic
        
        summary = {
            "repos_analyzed": len(comments),
            "new_keywords_added": count_new_keywords(old_config, new_config),
            "new_categories": count_new_categories(old_config, new_config),
            "status": "success"
        }
        
        # Write summary for GitHub Actions
        if "GITHUB_OUTPUT" in os.environ:
            with open(os.environ["GITHUB_OUTPUT"], "a") as f:
                f.write(f"summary={json.dumps(summary)}\n")
        
        # After PR merge, close the issue (future enhancement)
        # This would be triggered by a separate workflow on merge
        # issue_num = get_or_create_weekly_issue(client)
        # close_issue(client, issue_num, reason="Config updated with new keywords")
        
    except Exception as e:
        logger.error(f"Error: {e}")
        summary["status"] = "failed"
        summary["error"] = str(e)
        # Write error summary for GitHub Actions
        if "GITHUB_OUTPUT" in os.environ:
            with open(os.environ["GITHUB_OUTPUT"], "a") as f:
                f.write(f"summary={json.dumps(summary)}\n")
```

**Changes:**
- Import `issue_manager` for future auto-close flow
- Generate structured summary dict with status
- Pass summary to GitHub Actions via `GITHUB_OUTPUT`
- Use logger for visibility
- Include error details in summary output

#### `find_weird.py` (Entry Point)

```python
from github_star_organizer.gh_client import GitHubClient, GitHubAPIError
from github_star_organizer.categorizer import is_categorized
from github_star_organizer.logger import get_logger

logger = get_logger("find_weird")

def main():
    client = GitHubClient()
    
    try:
        # ... search and display logic, using logger instead of print
    except GitHubAPIError as e:
        logger.warning(f"API error (continuing): {e}")
```

**Changes:**
- Import `GitHubClient` from package instead of defining locally
- Use `logger` instead of `print`
- Graceful error handling (warning logged, search continues)

### GitHub Actions Updates

#### `organize.yml`

```yaml
- name: Set up Python
  uses: actions/setup-python@v5
  with:
    python-version: '3.x'

- name: Install dependencies
  run: pip install -r requirements.txt

- name: Organize Stars
  env:
    GH_TOKEN: ${{ secrets.GH_TOKEN }}
  run: python3 categorize.py
```

**Changes:** Add Python setup and dependency installation.

#### `distill.yml`

```yaml
- name: Run Distillation
  id: distillation
  env:
    GH_TOKEN: ${{ secrets.GH_TOKEN }}
    DEEPSEEK_API_KEY: ${{ secrets.DEEPSEEK_API_KEY }}
  run: python distill.py

- name: Create Pull Request
  uses: peter-evans/create-pull-request@v6
  with:
    token: ${{ secrets.GH_TOKEN }}
    commit-message: "Automated: Update config.json keywords from uncategorized stars (${{ steps.distillation.outputs.date_suffix }})"
    title: "Distillation: Update Star Categories (${{ steps.distillation.outputs.date_suffix }})"
    body: |
      This PR was automatically generated by the Distill Keywords runner.
      
      ${{ steps.distillation.outputs.summary }}
      
      See issue #${{ steps.distillation.outputs.issue_num }} for uncategorized repos.
    branch: "distill-keywords"
    delete-branch: true
```

**Changes:** Include distill summary in PR body.

### New Files

#### `requirements.txt`

```
requests>=2.28.0
```

Only external dependency is `requests` for `distill.py` (DeepSeek API calls).

### Migration Path

1. Create `github_star_organizer/` package with 5 modules (gh_client, categorizer, logger, config, issue_manager)
2. Extract issue lifecycle logic from `categorize.py` into `issue_manager.py`
3. Update 3 entry-point scripts to import from package
4. Migrate existing tests to `tests/unit/` and update imports
5. Add new tests for all modules (unit + integration)
6. Update GitHub Actions workflows (python setup, dependency install)
7. Commit all changes in a single PR

**Future Enhancement (not in this refactor):**
- Add a new workflow (`on-distill-merge.yml`) that triggers when distill PRs merge
- This workflow would call `close_issue()` to auto-close the weekly issue after config updates
- Currently, we just set up the infrastructure for this flow

## Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| Tests fail to mock `subprocess.run` correctly | Use `unittest.mock.patch`; verify mocks match actual API format and gh CLI output |
| Issue deduplication regex fails on edge cases | Test with varied markdown formats; handle missing fields gracefully |
| New logging adds verbosity in GitHub Actions | Use `logger.debug()` for detail, keep `logger.info()` for summary messages |
| `distill.py` summary generation is complex | Start with simple dict, test generation separately in unit tests |
| Package import issues on GitHub Actions | Test locally first; ensure `__init__.py` is present; run tests in CI before merging |
| Issue close fails when PR merges | Wrap in try/except; log failure but don't block the merge (not critical path) |

## Success Criteria

- ✅ All existing functionality preserved (categorize, distill, find_weird work identically)
- ✅ Issue lifecycle logic consolidated in `issue_manager.py` (no duplication with categorize.py)
- ✅ Distill PR comments show config changes automatically
- ✅ 30+ tests (unit + integration) with >80% code coverage on package modules
- ✅ Type hints on all public functions in package modules
- ✅ Logging visible in GitHub Actions without adding noise
- ✅ No breaking changes to entry-point scripts or config.json format
- ✅ Code duplication eliminated (single gh_client, single categorizer, single issue_manager)
- ✅ Infrastructure in place for future auto-close-on-merge flow (distill.py imports close_issue)

## Open Questions / Decisions

None. Design is complete and approved.
