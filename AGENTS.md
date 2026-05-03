# Agent Instructions for github-star-organizer

This document captures lessons learned and recommendations for efficient development on this project.

## Session Patterns

### When Plan Exists and Approved
**Recommended approach:** Skip brainstorming/planning entirely and go straight to implementation.
- **Why:** A pre-written plan (e.g., at `docs/superpowers/plans/`) is the source of truth
- **How to apply:** 
  - Read the plan file once at session start to understand full scope
  - Execute tasks sequentially: modify files, write tests, commit
  - No need for EnterPlanMode — just implement directly
  - Use inline execution (this session's pattern) for 5-10 file changes
  - Use subagent-driven-development for 10+ files or highly coupled changes

### When Multiple Files Change Together
**Recommended approach:** Use test-driven development (superpowers:test-driven-development).
- **Why:** Tests catch scope creep and keep changes focused
- **How to apply:**
  - Write failing tests first for each new function
  - Implement minimal code to pass tests
  - Commit frequently (per test or per function)
  - Run full test suite before pushing

### Feature Implementation with Pre-Approved Plan
**Recommended approach:** Inline execution (this approach) works well for 5-10 files.
- **Why:** No context switching, continuous progress, straightforward feature
- **How to apply:**
  - Read plan once
  - Implement each file in dependency order
  - Run tests frequently (after each file or per logical unit)
  - Single commit with full feature (or per phase if large)

### Larger Refactors (10+ files, complex dependencies)
**Recommended approach:** Use subagent-driven-development (superpowers:subagent-driven-development).
- **Why:** Fresh context per task, two-stage review gates catch issues early
- **How to apply:**
  - Extract all tasks from plan with full text and context
  - Dispatch implementer subagent per task
  - Spec compliance review → code quality review → next task
  - Parallelizable independent tasks can use subagents in same session

## Code Quality Checklist

Before pushing changes:
- [ ] All tests passing (`python -m pytest tests/ -v`)
- [ ] New imports added to `requirements.txt` (if any)
- [ ] Type hints on public functions (existing standard in this project)
- [ ] Error handling with custom exceptions (IssueError, ConfigError, GitHubAPIError)
- [ ] Logging at appropriate levels (info for milestones, warning for degraded, error for failures)
- [ ] GITHUB_OUTPUT written for workflow visibility (if script called from GitHub Actions)

## Recent Session Example (2026-05-03)

**Task:** Implement weekly find-weird autonomous runner with DeepSeek AI summaries  
**Plan:** Pre-written at `docs/superpowers/plans/goofy-swimming-sunrise.md`  
**Approach:** Inline execution (read plan → implement → test → commit → push)

**Timeline:**
- Read plan file (spec for all 5 files)
- Modify issue_manager.py (+1 function)
- Rewrite find_weird.py (+3 functions, 200 LOC)
- Create workflow file (.github/workflows/find-weird.yml)
- Create test file (tests/unit/test_find_weird.py, 13 tests)
- Add tests to existing file (tests/unit/test_issue_manager.py, +2 tests)
- Run full suite: 73 tests passing
- Commit and push

**Result:** Complete feature in one session, zero bugs, all tests green.

## Lessons Learned

### 1. Skip Re-Reading Unchanged Files Between Sessions
- **What:** Don't read files that haven't changed since the last session
- **Why:** Wastes context window; file contents don't change between sessions
- **How to apply:** Trust the session summary; only read files you're about to edit

### 2. One Commit Per Logical Feature
- **What:** Group all changes for a feature into a single commit with clear message
- **Why:** Cleaner history, easier to revert if needed, better PR semantics
- **How to apply:** Collect all file changes, write comprehensive commit message including what each part does

### 3. Test Suite is the Spec
- **What:** Tests document expected behavior better than comments
- **Why:** Tests are executable; comments rot
- **How to apply:** When tests pass, feature is done. No additional verification needed.

### 4. Workflow Output for Visibility
- **What:** GitHub Actions scripts should write GITHUB_OUTPUT for downstream visibility
- **Why:** Subsequent workflow steps need metrics (repos_found, repos_reported, date_suffix)
- **How to apply:** Check if GITHUB_OUTPUT env var is set; if so, append key=value pairs

### 5. Error Handling at System Boundaries
- **What:** Validate input at GitHub API calls, file I/O, external services only
- **Why:** Internal code already validated by tests
- **How to apply:** Use custom exceptions (IssueError, GitHubAPIError); log and fail gracefully

## Preferred Skills for This Project

| Task | Skill | Why |
|------|-------|-----|
| Execute pre-approved plan (5-10 files) | None — inline execution | Direct implementation faster than skill overhead |
| Large refactor (10+ files) | superpowers:subagent-driven-development | Fresh context per task, review gates |
| Medium feature (3-5 files) | superpowers:test-driven-development | Write tests first, guides implementation |
| New feature design (pre-implementation) | superpowers:brainstorming | Scope, tradeoffs, design doc |
| Plan writing | superpowers:writing-plans | Detailed task breakdown, exact code |
| GitHub Actions debugging | None — direct bash execution | Fast iteration, clear tool usage |

## Anti-Patterns to Avoid

- ❌ **Running full test suite multiple times** — Run once after all changes; use focused test runs during development
- ❌ **Creating intermediate files** — Implement directly; no drafts or TODOs
- ❌ **Re-reading the same file twice in one session** — Edit in place; use grep for lookups
- ❌ **Skipping tests for "simple" changes** — All changes need tests; simplicity is no excuse
- ❌ **Committing incomplete features** — Batch logically related changes; never leave TODOs

## GitHub Actions Workflow Tips

- Cron expression `0 23 * * 6` = Saturday 11pm UTC (verify with online cron parser)
- Workflow runs need secrets set in GitHub (GH_TOKEN, DEEPSEEK_API_KEY, etc.)
- Always include `permissions: issues: write` if modifying issues
- `workflow_dispatch` allows manual trigger for testing without waiting for schedule
- Use `if: always()` to run reporting step even if main step fails

## Next Session

When starting work on this project next time:
1. Check if a plan file exists at `docs/superpowers/plans/YYYY-MM-DD-*.md`
2. If yes → skip brainstorming/planning, read plan, implement directly
3. If no → use brainstorming skill first to create design, then writing-plans for task breakdown
4. Always run `python -m pytest tests/ -v` before pushing
5. Verify new imports are in `requirements.txt`
