"""GitHub Star Lists I/O: paginated inventory, star listing, and additive assignment."""
import re
from github_star_organizer.gh_client import GitHubAPIError

REPO_FIELDS = """
  id
  nameWithOwner
  description
  isFork
  isMirror
  mirrorUrl
  parent { id nameWithOwner }
  repositoryTopics(first: 10) { nodes { topic { name } } }
"""

_LISTS_Q = """
query($cursor: String) {
  viewer {
    lists(first: 50, after: $cursor) {
      nodes {
        id
        name
        items(first: 100) {
          nodes { ... on Repository { %s } }
          pageInfo { hasNextPage endCursor }
        }
      }
      pageInfo { hasNextPage endCursor }
    }
  }
}
""" % REPO_FIELDS

_ITEMS_Q = """
query($listId: ID!, $cursor: String) {
  node(id: $listId) {
    ... on UserList {
      items(first: 100, after: $cursor) {
        nodes { ... on Repository { %s } }
        pageInfo { hasNextPage endCursor }
      }
    }
  }
}
""" % REPO_FIELDS

_STARS_Q = """
query($cursor: String) {
  viewer {
    starredRepositories(first: 100, after: $cursor,
                        orderBy: {field: STARRED_AT, direction: DESC}) {
      nodes { %s }
      pageInfo { hasNextPage endCursor }
    }
  }
}
""" % REPO_FIELDS


def _data(result: dict) -> dict:
    if not result or "data" not in result or result["data"] is None:
        raise GitHubAPIError(f"Unexpected GraphQL response: {str(result)[:200]}")
    return result["data"]


def fetch_list_inventory(client) -> dict[str, dict]:
    """All Star Lists with ALL their repo members (fully paginated).

    Returns {list name: {"id": str, "members": [repo dict]}}.
    """
    inventory: dict[str, dict] = {}
    cursor = None
    while True:
        variables = {"cursor": cursor} if cursor else None
        lists = _data(client.run_query(_LISTS_Q, variables))["viewer"]["lists"]
        for node in lists["nodes"]:
            items = node["items"]
            members = [r for r in items["nodes"] if r]
            more = items["pageInfo"]
            while more["hasNextPage"]:
                page = _data(client.run_query(
                    _ITEMS_Q, {"listId": node["id"], "cursor": more["endCursor"]}
                ))["node"]["items"]
                members.extend(r for r in page["nodes"] if r)
                more = page["pageInfo"]
            inventory[node["name"]] = {"id": node["id"], "members": members}
        if not lists["pageInfo"]["hasNextPage"]:
            return inventory
        cursor = lists["pageInfo"]["endCursor"]


def fetch_stars(client, limit: int) -> list[dict]:
    """Starred repos, newest first, up to `limit`."""
    stars: list[dict] = []
    cursor = None
    while len(stars) < limit:
        variables = {"cursor": cursor} if cursor else None
        page = _data(client.run_query(_STARS_Q, variables))["viewer"]["starredRepositories"]
        stars.extend(r for r in page["nodes"] if r)
        if not page["pageInfo"]["hasNextPage"]:
            break
        cursor = page["pageInfo"]["endCursor"]
    return stars[:limit]


def membership_map(inventory: dict[str, dict]) -> dict[str, set[str]]:
    """repo id -> set of list ids it is already in."""
    out: dict[str, set[str]] = {}
    for info in inventory.values():
        for repo in info["members"]:
            out.setdefault(repo["id"], set()).add(info["id"])
    return out


def canonical_names(repo: dict) -> set[str]:
    """Names of the repo this one is a fork or mirror of (lower-cased)."""
    names: set[str] = set()
    parent = repo.get("parent")
    if repo.get("isFork") and parent and parent.get("nameWithOwner"):
        names.add(parent["nameWithOwner"].lower())
    if repo.get("isMirror") and repo.get("mirrorUrl"):
        m = re.match(r"https?://(?:www\.)?github\.com/([^/]+/[^/#?]+?)(?:\.git)?/?$",
                     repo["mirrorUrl"])
        if m:
            names.add(m.group(1).lower())
    return names


def assign(client, repo_id: str, current_list_ids: set[str], add_list_id: str) -> None:
    """Add a repo to a list WITHOUT dropping its other memberships.

    updateUserListsForItem replaces the full set, so send current + new.
    """
    list_ids = sorted(current_list_ids | {add_list_id})
    client.run_query(
        """
        mutation($repoId: ID!, $listIds: [ID!]!) {
          updateUserListsForItem(input: {itemId: $repoId, listIds: $listIds}) {
            clientMutationId
          }
        }
        """,
        {"repoId": repo_id, "listIds": list_ids},
    )


def create_list(client, name: str) -> str:
    """Create a private Star List and return its id."""
    result = client.run_query(
        """
        mutation($name: String!) {
          createUserList(input: {name: $name, isPrivate: true}) { list { id name } }
        }
        """,
        {"name": name},
    )
    return _data(result)["createUserList"]["list"]["id"]
