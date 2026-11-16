import os
import tempfile
import unittest
from unittest.mock import patch

import categorize
from github_star_organizer import state_db


def repo(rid, name, desc="", topics=(), parent=None, mirror=None):
    return {
        "id": rid, "nameWithOwner": name, "description": desc,
        "isFork": parent is not None, "parent": {"id": "P", "nameWithOwner": parent} if parent else None,
        "isMirror": mirror is not None, "mirrorUrl": mirror,
        "repositoryTopics": {"nodes": [{"topic": {"name": t}} for t in topics]},
    }


class FakeClient:
    """Serves list inventory and stars from memory; records mutations."""

    def __init__(self, lists, stars):
        self.lists = lists  # {name: (id, [repo])}
        self.stars = stars
        self.assigned = []   # (repo_id, [list ids])
        self.created = []    # names

    def run_query(self, query, variables=None):
        variables = variables or {}
        if "createUserList" in query:
            self.created.append(variables["name"])
            return {"data": {"createUserList": {"list": {"id": f"NEW{len(self.created)}", "name": variables["name"]}}}}
        if "updateUserListsForItem" in query:
            self.assigned.append((variables["repoId"], variables["listIds"]))
            return {"data": {}}
        if "viewer" in query and "lists(" in query:
            nodes = [{"id": lid, "name": n,
                      "items": {"nodes": members, "pageInfo": {"hasNextPage": False, "endCursor": None}}}
                     for n, (lid, members) in self.lists.items()]
            return {"data": {"viewer": {"lists": {"nodes": nodes, "pageInfo": {"hasNextPage": False, "endCursor": None}}}}}
        if "starredRepositories" in query:
            return {"data": {"viewer": {"starredRepositories": {
                "nodes": self.stars, "pageInfo": {"hasNextPage": False, "endCursor": None}}}}}
        raise AssertionError(f"unexpected query: {query[:60]}")


class TestRun(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        patcher = patch("github_star_organizer.state_db.DB_PATH", self.path)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(lambda: os.path.exists(self.path) and os.remove(self.path))
        state_db.init_db()
        self.config = {"lists": {}, "keywords": {"AI": ["llm", "agent"]}}
        self.ai_members = [repo("M1", "a/agentkit", "llm agents", ["llm", "agents"])]

    def run_with(self, client, **env):
        with patch.dict(os.environ, env, clear=False):
            return categorize.run(client, self.config)

    def test_places_matching_repo_additively(self):
        client = FakeClient({"AI": ("L_AI", self.ai_members)},
                            [repo("R1", "x/swarm", "multi agent llm", ["llm", "agents"])])
        stats = self.run_with(client)
        self.assertEqual(stats["assigned"], 1)
        self.assertEqual(client.assigned, [("R1", ["L_AI"])])

    def test_keeps_existing_memberships(self):
        # R1 is already in list OTHER; it is not a candidate and must not be touched.
        client = FakeClient({"AI": ("L_AI", self.ai_members), "Other": ("L_O", [repo("R1", "x/a", "", [])])},
                            [repo("R1", "x/a", "", [])])
        self.run_with(client)
        self.assertEqual(client.assigned, [])

    def test_fork_follows_original(self):
        orig = repo("O1", "up/lib", "", [])
        client = FakeClient({"Misc": ("L_M", [orig])},
                            [repo("F1", "me/lib", "", [], parent="Up/Lib")])
        stats = self.run_with(client)
        self.assertEqual(stats["by_parent"], 1)
        self.assertEqual(client.assigned, [("F1", ["L_M"])])

    def test_mirror_follows_original(self):
        orig = repo("O1", "up/lib", "", [])
        client = FakeClient({"Misc": ("L_M", [orig])},
                            [repo("F1", "mir/lib", "", [], mirror="https://github.com/up/lib.git")])
        self.run_with(client)
        self.assertEqual(client.assigned, [("F1", ["L_M"])])

    def cluster(self, topic, n):
        return [repo(f"Q{i}", f"q/r{i}", "x", [topic]) for i in range(n)]

    def test_creates_one_list_for_cluster_within_quota(self):
        client = FakeClient({"AI": ("L_AI", self.ai_members)}, self.cluster("quantum-computing", 3))
        stats = self.run_with(client, MAX_NEW_LIST_PER_WEEK="1")
        self.assertEqual(client.created, ["Quantum Computing"])
        self.assertEqual(stats["assigned"], 3)
        self.assertEqual(state_db.count_lists_created_since(7), 1)

    def test_weekly_cap_blocks_second_creation(self):
        state_db.record_created_list("Earlier", "L_E")
        client = FakeClient({"AI": ("L_AI", self.ai_members)}, self.cluster("quantum-computing", 3))
        stats = self.run_with(client, MAX_NEW_LIST_PER_WEEK="1")
        self.assertEqual(client.created, [])
        self.assertEqual(stats["unplaced"], 3)
        self.assertEqual(len(state_db.get_uncategorized_repos()), 3)

    def test_zero_cap_never_creates(self):
        client = FakeClient({"AI": ("L_AI", self.ai_members)}, self.cluster("quantum-computing", 5))
        self.run_with(client, MAX_NEW_LIST_PER_WEEK="0")
        self.assertEqual(client.created, [])

    def test_small_cluster_does_not_create(self):
        client = FakeClient({"AI": ("L_AI", self.ai_members)}, self.cluster("quantum-computing", 2))
        self.run_with(client)
        self.assertEqual(client.created, [])

    def test_assign_cap_per_run(self):
        stars = [repo(f"R{i}", f"x/agent{i}", "llm agents", ["llm", "agents"]) for i in range(5)]
        client = FakeClient({"AI": ("L_AI", self.ai_members)}, stars)
        stats = self.run_with(client, MAX_ASSIGN_PER_RUN="2")
        self.assertEqual(stats["assigned"], 2)

    def test_dry_run_mutates_nothing(self):
        stars = [repo("R1", "x/swarm", "multi agent llm", ["llm", "agents"])] + self.cluster("quantum-computing", 3)
        client = FakeClient({"AI": ("L_AI", self.ai_members)}, stars)
        stats = self.run_with(client, DRY_RUN="1", MAX_NEW_LIST_PER_WEEK="1")
        self.assertEqual(client.assigned, [])
        self.assertEqual(client.created, [])
        self.assertEqual(state_db.count_lists_created_since(7), 0)
        self.assertEqual(stats["assigned"], 4)          # what it WOULD have done
        self.assertEqual(stats["created_lists"], 1)

    def test_bad_env_value_is_config_error(self):
        client = FakeClient({"AI": ("L_AI", self.ai_members)}, [])
        from github_star_organizer.config import ConfigError
        with self.assertRaises(ConfigError):
            self.run_with(client, MAX_NEW_LIST_PER_WEEK="lots")

    def test_unplaced_not_reinserted(self):
        client = FakeClient({"AI": ("L_AI", self.ai_members)},
                            [repo("R9", "x/recipes", "cooking", ["cooking"])])
        self.run_with(client)
        self.run_with(client)
        self.assertEqual(len(state_db.get_uncategorized_repos()), 1)


if __name__ == "__main__":
    unittest.main()
