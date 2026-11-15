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
4. **Classify** (cheapest first): canonical's list -> keyword match (`config.json`) -> LLM pick
   constrained to the existing list names (return a list name or `none`).
5. **Apply** via `updateUserListsForItem`, **additively**: send the repo's current list IDs plus
   the new one. Never overwrite existing membership.
6. **Record** unplaceable repos in `state.db.uncategorized_repos` for `distill.py` keyword growth
   (existing behaviour, kept).

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
| `distill.py` + `uncategorized_repos` table | `probe_ollama_models.py`, workflow, `ollama_model_metrics` table |
| `maintenance.yml` (with the `GH_TOKEN` preflight) | `discovered_repos` table, `issue_manager.py` discovery-issue code |
| `state.db` cache + `state-backup` branch | stray `test_fix.py`, `test_pipeline.py`; tracked `__pycache__` |

Removal happens **after** the new repo exists and has copied what it wants, so nothing is lost
(git history also keeps it).

## Auth

Star Lists live on the user account and are only writable with a user-scoped token
(`GH_TOKEN` PAT). There is no tokenless route (see #194 discussion). Keep the preflight; use a
long-lived token and rotate on a calendar reminder.

## Work breakdown

1. Fix pagination + additive mutation, with tests (highest value, fixes data-loss risk).
2. Resolve list IDs by name; drop empty IDs from `config.json`.
3. Fork/mirror canonical resolution.
4. LLM classification constrained to existing list names (reuse `call_deepseek` pattern in `distill.py`).
5. Process full backlog in batches with a per-run cap.
6. After new repo is bootstrapped: delete discovery code, workflows, tables; update README.
