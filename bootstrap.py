# bootstrap.py
"""One-time taxonomy bootstrap: create the lists named in config.json, then seed them.

Dry-run by default. Nothing is deleted or removed from any list; placement is additive.

  python bootstrap.py            preview: lists that would be created + placements
  python bootstrap.py --apply    snapshot, create missing lists (private), seed placements
  --limit N                      max stars examined and max placements (default 500)

A JSON snapshot of every list and member is written to snapshots/ first (kept local, not in git),
so the previous taxonomy can be rebuilt by hand if you ever want it back.
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

import categorize
from github_star_organizer import star_lists, state_db
from github_star_organizer.config import ConfigError, load_config
from github_star_organizer.gh_client import GitHubAPIError, GitHubClient
from github_star_organizer.logger import get_logger

logger = get_logger("bootstrap")
SNAPSHOT_DIR = "snapshots"


def taxonomy_names(config: dict) -> list[str]:
    """List names to ensure exist: those with keywords, config order, no case duplicates."""
    seen, out = set(), []
    for name in config["keywords"]:
        if name.lower() not in seen and config["keywords"][name]:
            seen.add(name.lower())
            out.append(name)
    return out


def missing_lists(config: dict, inventory: dict) -> list[str]:
    existing = {n.lower() for n in inventory}
    return [n for n in taxonomy_names(config) if n.lower() not in existing]


def write_snapshot(inventory: dict, directory: str | None = None) -> str:
    directory = directory or SNAPSHOT_DIR
    os.makedirs(directory, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = os.path.join(directory, f"lists-{stamp}.json")
    data = {name: {"id": info["id"], "members": sorted(r["nameWithOwner"] for r in info["members"])}
            for name, info in inventory.items()}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
    return path


def bootstrap(client, config: dict, apply: bool, limit: int) -> dict:
    inventory = star_lists.fetch_list_inventory(client)
    snap = write_snapshot(inventory)
    logger.info(f"Snapshot of {len(inventory)} lists written to {snap}")
    to_create = missing_lists(config, inventory)
    logger.info(f"{len(to_create)} lists to create: {to_create}")

    env = {"MAX_NEW_LIST_PER_WEEK": "0", "MAX_STARS_PER_RUN": str(limit),
           "MAX_ASSIGN_PER_RUN": str(limit), "DRY_RUN": "" if apply else "1"}
    saved = {k: os.environ.get(k) for k in env}
    os.environ.update(env)
    try:
        extra = None
        if apply:
            for name in to_create:
                list_id = star_lists.create_list(client, name)
                state_db.record_created_list(name, list_id)
                logger.info(f"Created list '{name}'")
        else:
            extra = {name: f"DRY-{name}" for name in to_create}
        stats = categorize.run(client, config, extra_lists=extra)
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    stats["lists_to_create"] = len(to_create)
    return stats


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="make changes (default: dry-run)")
    ap.add_argument("--limit", type=int, default=500)
    args = ap.parse_args(argv)
    try:
        state_db.init_db()
        stats = bootstrap(GitHubClient(), load_config(), args.apply, args.limit)
        logger.info(f"Done ({'applied' if args.apply else 'dry-run'}): {stats}")
    except (ConfigError, GitHubAPIError) as e:
        logger.error(str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
