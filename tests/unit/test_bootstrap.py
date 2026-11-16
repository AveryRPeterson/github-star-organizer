import os
import tempfile
import unittest
from unittest.mock import patch

import bootstrap
from github_star_organizer import state_db
from tests.unit.test_categorize import FakeClient, repo


class TestBootstrap(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        for p in (patch("github_star_organizer.state_db.DB_PATH", self.path),
                  patch("bootstrap.SNAPSHOT_DIR", tempfile.mkdtemp())):
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(lambda: os.path.exists(self.path) and os.remove(self.path))
        state_db.init_db()
        self.config = {"lists": {}, "keywords": {"AI": ["llm", "agent"], "Quantum Computing": ["quantum", "qubit"],
                                                 "Empty": []}}
        self.stars = [repo("R1", "x/qsim", "quantum qubit simulator", ["quantum", "qubit"])]

    def client(self):
        return FakeClient({"AI": ("L_AI", [repo("M1", "a/agentkit", "llm agents", ["llm"])])}, self.stars)

    def test_missing_lists_ignores_case_and_keywordless(self):
        inv = {"ai": {"id": "x", "members": []}}
        self.assertEqual(bootstrap.missing_lists(self.config, inv), ["Quantum Computing"])

    def test_dry_run_changes_nothing_but_previews_new_list(self):
        c = self.client()
        stats = bootstrap.bootstrap(c, self.config, apply=False, limit=50)
        self.assertEqual((c.created, c.assigned), ([], []))
        self.assertEqual(stats["lists_to_create"], 1)
        self.assertEqual(stats["assigned"], 1)  # R1 would land in the new list

    def test_apply_creates_then_seeds_additively(self):
        c = self.client()
        stats = bootstrap.bootstrap(c, self.config, apply=True, limit=50)
        self.assertEqual(c.created, ["Quantum Computing"])
        self.assertEqual(state_db.count_lists_created_since(7), 1)
        self.assertEqual(stats["created_lists"], 0)  # no organic proposals during bootstrap

    def test_snapshot_written(self):
        bootstrap.bootstrap(self.client(), self.config, apply=False, limit=50)
        self.assertEqual(len(os.listdir(bootstrap.SNAPSHOT_DIR)), 1)
