# github-star-organizer: tightened scope

**Date:** 2026-11-15 | **Status:** Proposed | **Related:** #194, #202

## One job

> Put each starred repo that is **not in any Star List yet** into the most fitting list.

Everything else (trend discovery, lateral-use theorizing, viability) moves to a separate repo
(see `trend-lab-new-repo.md`). This repo keeps only what serves the one job.

## Behaviour

1. **Inventory** every Star List and every repo already in one (fully paginated).
2. **Candidates** = starred repos not in the inventory (walk all stars, not just the newest 50).
3. **Resolve identity** for each candidate:
   - `isFork` / `parent { nameWithOwner }`, `isMirror` / `mirrorUrl` via GraphQL.
   - If the canonical (parent/source) repo is already in a list, reuse that list. Forks and
     mirrors should land next to the thing they copy.
4. **Classify deterministically, no LLM:** canonical's list -> learned-profile match
   (`matcher.py`). Each list's profile is built from the repos already in it (topics weighted
   highest), plus the list name and seed keywords from `config.json`. A repo's score is the
   IDF-weighted share of its tokens that the list profile covers.
   - The acceptance threshold **falls as the number of lists grows** (`0.45 / (1 + n/6)`, floor
     0.12): the more lists exist, the harder the matcher tries to reuse one.
   - Below threshold, the repo is "unplaced".
5. **New lists, cautiously.** Unplaced repos are grouped by shared topic. A list is created only if
   (a) at least `3 + n_lists // 10` unplaced repos share the topic, (b) the topic is not already
   expressed by an existing list name or so common that it carries no signal, and (c) fewer than
   `MAX_NEW_LIST_PER_WEEK` (default 1) lists were created in the last 7 days (tracked in
   `state.db.created_lists`). New lists are private. Anything still unplaced goes to
   `uncategorized_repos`.
6. **Apply** via `updateUserListsForItem`, **additively**: send the repo's current list IDs plus
   the new one. Never overwrite existing membership.
7. **Record** unplaceable repos in `state.db.uncategorized_repos` for manual review.

## Bugs to fix on the way (found in review)

| Where | Problem |
|---|---|
| `categorizer.get_categorized_ids` | `lists(first:100)` / `items(first:100)` with no pagination. A repo past item 100 of a list looks uncategorized. |
| `categorize.py` mutation | `listIds: [$listId]` **replaces** the repo's memberships, so a mis-detected repo is removed from its other lists. |
| `categorize.py` / `get_recent_stars` | Only the 50 newest stars are considered; backlog never gets organized. |
| `config.json` | Four lists have empty IDs (Education, Quantum, Document Management, Decentralized, Ecosystems): matched repos are silently skipped. Resolve IDs by list *name* at runtime instead of hard-coding. |

## Keep / remove

| Keep | Remove (moves to new repo or is deleted) |
|---|---|
| `categorize.py`, `categorizer.py`, `config.py`, `gh_client.py`, `logger.py` | `discover_repos.py`, `.github/workflows/discover-repos.yml` |
| `uncategorized_repos` table (review list) | `probe_ollama_models.py`, workflow, `ollama_model_metrics` table |
| `maintenance.yml` (with the `GH_TOKEN` preflight) | `discovered_repos` table, `issue_manager.py` discovery-issue code |
| `state.db` cache + `state-backup` branch | stray `test_fix.py`, `test_pipeline.py`; tracked `__pycache__` |

Removal happens **after** the new repo exists and has copied what it wants, so nothing is lost
(git history also keeps it).

## Auth

Star Lists live on the user account and are only writable with a user-scoped token
(`GH_TOKEN` PAT). There is no tokenless route (see #194 discussion). Keep the preflight; use a
long-lived token and rotate on a calendar reminder.

## Work breakdown

1. [x] Fix pagination + additive mutation, with tests.
2. [x] Resolve list IDs by name at runtime.
3. [x] Fork/mirror canonical resolution.
4. [x] Deterministic matcher replaces keyword/LLM classification; `distill.py` removed.
5. [x] Full backlog per run with caps (`MAX_STARS_PER_RUN`, `MAX_ASSIGN_PER_RUN`).
6. [ ] First dry run on the real account; tune thresholds from the log.
7. [ ] After the new repo has what it needs: delete discovery code, workflows, tables (#202).

## Status (2026-11-16)

Done: pagination, additive assignment, fork/mirror resolution, deterministic matcher, capped
list creation, `DRY_RUN`, `distill.py` removed (LLM no longer used anywhere in the organizer),
stray `test_fix.py`/`test_pipeline.py` removed, `__pycache__` untracked. Remaining: first
dry run against the real account to tune `accept_threshold` / `min_cluster`, then delete the
discovery code once the new repo has what it needs.
