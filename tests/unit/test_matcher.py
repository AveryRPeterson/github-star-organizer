import unittest
from github_star_organizer import matcher as m


def repo(name, desc="", topics=()):
    return {"nameWithOwner": name, "description": desc,
            "repositoryTopics": {"nodes": [{"topic": {"name": t}} for t in topics]}}


LISTS = {
    "AI Agents": {"members": [repo("a/agentkit", "autonomous llm agents", ["ai", "llm", "agents"]),
                              repo("a/mcp-tools", "mcp servers for claude", ["mcp", "claude"])],
                  "keywords": ["gpt", "anthropic"]},
    "3D Printing": {"members": [repo("b/slicer", "gcode slicer", ["3d-printing", "cad"])],
                    "keywords": ["stl", "filament"]},
}


class TestTokenize(unittest.TestCase):
    def test_drops_stopwords_and_stems(self):
        self.assertEqual(m.tokenize("The Agents of the tool"), ["agent"])

    def test_none_safe(self):
        self.assertEqual(m.tokenize(None), [])


class TestMatching(unittest.TestCase):
    def setUp(self):
        self.profiles = m.build_profiles(LISTS)

    def test_matches_obvious_list(self):
        name, score = m.best_match(repo("x/swarm", "multi agent llm framework", ["llm", "agents"]), self.profiles)
        self.assertEqual(name, "AI Agents")
        self.assertGreater(score, 0.3)

    def test_keyword_seed_matches(self):
        name, _ = m.best_match(repo("x/benchy", "filament stl printer calibration", ["stl"]), self.profiles)
        self.assertEqual(name, "3D Printing")

    def test_unrelated_repo_unmatched(self):
        name, score = m.best_match(repo("x/recipes", "grandma cooking recipes", ["cooking"]), self.profiles)
        self.assertIsNone(name)
        self.assertLess(score, 0.12)

    def test_empty_repo_unmatched(self):
        self.assertEqual(m.best_match(repo("", None, []), self.profiles)[0], None)

    def test_deterministic(self):
        r = repo("x/swarm", "llm agents", ["llm"])
        self.assertEqual(m.best_match(r, self.profiles), m.best_match(r, self.profiles))

    def test_threshold_falls_as_lists_grow(self):
        self.assertGreater(m.accept_threshold(2), m.accept_threshold(10))
        self.assertGreater(m.accept_threshold(10), m.accept_threshold(40) - 1e-9)
        self.assertEqual(m.accept_threshold(10_000), 0.12)  # floor

    def test_weak_match_accepted_only_with_many_lists(self):
        # A borderline repo is rejected with few lists but accepted when many exist.
        r = repo("x/odd", "llm", [])
        few = m.build_profiles(LISTS)
        many = dict(LISTS)
        for i in range(25):
            many[f"Filler {i}"] = {"members": [], "keywords": [f"zz{i}"]}
        s_few = m.score_repo(r, few)["AI Agents"]
        s_many = m.score_repo(r, m.build_profiles(many))["AI Agents"]
        self.assertTrue(m.accept_threshold(25) < m.accept_threshold(2))
        self.assertGreater(s_few, 0)
        self.assertGreater(s_many, 0)


class TestNewLists(unittest.TestCase):
    def pool(self, n, topic, extra=()):
        return [repo(f"o/r{i}", "x", [topic, *extra]) for i in range(n)]

    def test_proposes_cluster_topic(self):
        un = self.pool(3, "quantum-computing") + [repo("o/z", "", ["misc"])]
        out = m.propose_new_lists(un, ["AI Agents"], max_new=1, min_size=3)
        self.assertEqual(out[0][0], "Quantum Computing")
        self.assertEqual(len(out[0][1]), 3)

    def test_cluster_too_small(self):
        self.assertEqual(m.propose_new_lists(self.pool(2, "quantum"), [], 1, 3), [])

    def test_zero_quota(self):
        self.assertEqual(m.propose_new_lists(self.pool(5, "quantum"), [], 0, 3), [])

    def test_respects_max_new(self):
        un = self.pool(3, "alpha") + self.pool(3, "beta")
        self.assertEqual(len(m.propose_new_lists(un, [], max_new=1, min_size=3)), 1)

    def test_skips_topic_already_a_list(self):
        self.assertEqual(m.propose_new_lists(self.pool(4, "3d-printing"), ["3D Printing"], 1, 3), [])

    def test_skips_overly_generic_topic(self):
        un = self.pool(8, "ai") + [repo(f"p/{i}", "", ["niche"]) for i in range(3)]
        out = m.propose_new_lists(un, [], max_new=2, min_size=3)
        self.assertEqual([n for n, _ in out], ["Niche"])

    def test_repo_used_once(self):
        un = [repo(f"o/{i}", "", ["alpha", "beta"]) for i in range(3)]
        out = m.propose_new_lists(un, [], max_new=2, min_size=3)
        self.assertEqual(len(out), 1)

    def test_min_cluster_grows_with_lists(self):
        self.assertEqual(m.min_cluster(0), 3)
        self.assertEqual(m.min_cluster(25), 5)


if __name__ == "__main__":
    unittest.main()
