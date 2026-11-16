# categorize.py
"""Place starred repos that are in no Star List into the best-fitting list.

Deterministic (no LLM). Environment:
  MAX_NEW_LIST_PER_WEEK  cap on Star Lists this tool may create per rolling 7 days (default 1)
  MAX_STARS_PER_RUN      newest stars to examine per run (default 500)
  MAX_ASSIGN_PER_RUN     cap on list assignments per run (default 100)
  DRY_RUN                1/true: log intended changes, mutate nothing
"""
import os
import sys
from github_star_organizer.gh_client import GitHubClient, GitHubAPIError
from github_star_organizer import matcher, star_lists
from github_star_organizer.issue_manager import IssueError
from github_star_organizer.logger import get_logger
from github_star_organizer.config import load_config, ConfigError
from github_star_organizer import state_db


logger = get_logger("categorize")


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return max(0, int(raw))
    except ValueError:
        raise ConfigError(f"{name} must be an integer, got {raw!r}")


def run(client, config: dict, extra_lists: dict | None = None) -> dict:
    """Do one organizing pass. Returns counters for logging/tests.

    extra_lists: {name: id} of lists that do not exist yet (bootstrap dry-run preview);
    they join the inventory as empty lists so keyword profiles can match.
    """
    max_new_per_week = _env_int("MAX_NEW_LIST_PER_WEEK", 1)
    max_stars = _env_int("MAX_STARS_PER_RUN", 500)
    max_assign = _env_int("MAX_ASSIGN_PER_RUN", 100)
    dry = os.getenv("DRY_RUN", "").strip().lower() in ("1", "true", "yes")
    if dry:
        logger.info("DRY_RUN: no lists will be created or changed")
    stats = {"assigned": 0, "by_parent": 0, "created_lists": 0, "unplaced": 0}

    inventory = star_lists.fetch_list_inventory(client)
    for name, lid in (extra_lists or {}).items():
        inventory.setdefault(name, {"id": lid, "members": []})
    membership = star_lists.membership_map(inventory)
    logger.info(f"Inventory: {len(inventory)} lists, {len(membership)} repos already listed")

    stars = star_lists.fetch_stars(client, max_stars)
    candidates = [r for r in stars if r["id"] not in membership]
    logger.info(f"{len(candidates)} of {len(stars)} stars are in no list")

    list_ids = {name: info["id"] for name, info in inventory.items()}
    name_to_lists = {
        r["nameWithOwner"].lower(): ids
        for info in inventory.values() for r in info["members"]
        for ids in [membership[r["id"]]]
    }
    profiles = matcher.build_profiles({
        name: {"members": info["members"], "keywords": config["keywords"].get(name, [])}
        for name, info in inventory.items()
    })

    budget = {"left": max_assign}

    def place(repo: dict, list_id: str) -> None:
        if budget["left"] <= 0:
            return
        if dry:
            logger.info(f"[dry-run] would add {repo['nameWithOwner']} to list {list_id}")
        else:
            star_lists.assign(client, repo["id"], membership.get(repo["id"], set()), list_id)
        membership.setdefault(repo["id"], set()).add(list_id)
        budget["left"] -= 1
        stats["assigned"] += 1

    unmatched: list[dict] = []
    for repo in candidates:
        # 1. Forks/mirrors follow the repo they copy, if that one is already listed.
        parent_lists = set()
        for canon in star_lists.canonical_names(repo):
            parent_lists |= name_to_lists.get(canon, set())
        if parent_lists:
            for lid in sorted(parent_lists):
                place(repo, lid)
            stats["by_parent"] += 1
            logger.info(f"{repo['nameWithOwner']}: placed with its original")
            continue
        # 2. Learned-profile match against existing lists.
        name, score = matcher.best_match(repo, profiles)
        if name:
            logger.info(f"{repo['nameWithOwner']} -> {name} (score {score:.2f})")
            place(repo, list_ids[name])
        else:
            unmatched.append(repo)

    # 3. Cautiously create new lists for clusters of unplaced repos.
    quota = max(0, max_new_per_week - state_db.count_lists_created_since(7))
    proposals = matcher.propose_new_lists(
        unmatched, list(inventory), quota, matcher.min_cluster(len(inventory))
    )
    placed_now: set[str] = set()
    for list_name, members in proposals:
        if dry:
            list_id = f"DRY-{list_name}"
            logger.info(f"[dry-run] would create list '{list_name}' for {len(members)} repos")
        else:
            list_id = star_lists.create_list(client, list_name)
            state_db.record_created_list(list_name, list_id)
            logger.info(f"Created list '{list_name}' for {len(members)} repos")
        stats["created_lists"] += 1
        for repo in members:
            place(repo, list_id)
            placed_now.add(repo["nameWithOwner"])
    if quota == 0 and unmatched:
        logger.info(f"New-list quota exhausted (MAX_NEW_LIST_PER_WEEK={max_new_per_week})")

    # 4. Whatever is left is recorded for review.
    leftover = [r for r in unmatched if r["nameWithOwner"] not in placed_now]
    stats["unplaced"] = len(leftover)
    if leftover and not dry:
        known = state_db.get_uncategorized_repos()
        fresh = [r for r in leftover if r["nameWithOwner"] not in known]
        if fresh:
            state_db.insert_uncategorized_repos(fresh)
            logger.info(f"Recorded {len(fresh)} new unplaced repos")
    if budget["left"] <= 0:
        logger.warning(f"Hit MAX_ASSIGN_PER_RUN={max_assign}; remaining repos wait for next run")
    return stats


def main():
    try:
        state_db.init_db()
        config = load_config()
        logger.info("Config loaded successfully")
        stats = run(GitHubClient(), config)
        logger.info(f"Done: {stats}")
    except ConfigError as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)
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
