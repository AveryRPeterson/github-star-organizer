import unittest
from github_star_organizer import star_lists as sl


class Client:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def run_query(self, query, variables=None):
        self.calls.append((query, variables))
        return self.responses.pop(0)


def page(nodes, nxt=None):
    return {"nodes": nodes, "pageInfo": {"hasNextPage": nxt is not None, "endCursor": nxt}}


class TestInventory(unittest.TestCase):
    def test_paginates_items_past_100(self):
        first = {"data": {"viewer": {"lists": {
            "nodes": [{"id": "L1", "name": "A", "items": page([{"id": "r1"}], nxt="c1")}],
            "pageInfo": {"hasNextPage": False, "endCursor": None}}}}}
        second = {"data": {"node": {"items": page([{"id": "r2"}, None])}}}
        inv = sl.fetch_list_inventory(Client([first, second]))
        self.assertEqual([r["id"] for r in inv["A"]["members"]], ["r1", "r2"])

    def test_paginates_lists(self):
        p1 = {"data": {"viewer": {"lists": {
            "nodes": [{"id": "L1", "name": "A", "items": page([])}],
            "pageInfo": {"hasNextPage": True, "endCursor": "x"}}}}}
        p2 = {"data": {"viewer": {"lists": {
            "nodes": [{"id": "L2", "name": "B", "items": page([])}],
            "pageInfo": {"hasNextPage": False, "endCursor": None}}}}}
        c = Client([p1, p2])
        self.assertEqual(set(sl.fetch_list_inventory(c)), {"A", "B"})
        self.assertEqual(c.calls[1][1], {"cursor": "x"})

    def test_bad_response_raises(self):
        from github_star_organizer.gh_client import GitHubAPIError
        with self.assertRaises(GitHubAPIError):
            sl.fetch_list_inventory(Client([{"errors": []}]))


class TestStars(unittest.TestCase):
    def resp(self, nodes, nxt=None):
        return {"data": {"viewer": {"starredRepositories": page(nodes, nxt)}}}

    def test_walks_pages_and_respects_limit(self):
        c = Client([self.resp([{"id": "1"}, {"id": "2"}], "n"), self.resp([{"id": "3"}])])
        self.assertEqual([r["id"] for r in sl.fetch_stars(c, 3)], ["1", "2", "3"])
        c = Client([self.resp([{"id": "1"}, {"id": "2"}], "n")])
        self.assertEqual(len(sl.fetch_stars(c, 1)), 1)


class TestHelpers(unittest.TestCase):
    def test_membership_map(self):
        inv = {"A": {"id": "L1", "members": [{"id": "r"}]}, "B": {"id": "L2", "members": [{"id": "r"}]}}
        self.assertEqual(sl.membership_map(inv), {"r": {"L1", "L2"}})

    def test_canonical_fork_and_mirror(self):
        self.assertEqual(sl.canonical_names({"isFork": True, "parent": {"nameWithOwner": "Up/Lib"}}), {"up/lib"})
        self.assertEqual(sl.canonical_names({"isMirror": True, "mirrorUrl": "https://github.com/Up/Lib.git"}), {"up/lib"})
        self.assertEqual(sl.canonical_names({"isMirror": True, "mirrorUrl": "https://gitlab.com/a/b"}), set())
        self.assertEqual(sl.canonical_names({}), set())

    def test_assign_is_additive(self):
        c = Client([{"data": {}}])
        sl.assign(c, "r1", {"L1", "L2"}, "L3")
        self.assertEqual(c.calls[0][1], {"repoId": "r1", "listIds": ["L1", "L2", "L3"]})

    def test_create_list_returns_id(self):
        c = Client([{"data": {"createUserList": {"list": {"id": "NEW", "name": "X"}}}}])
        self.assertEqual(sl.create_list(c, "X"), "NEW")
        self.assertIn("isPrivate: true", c.calls[0][0])


if __name__ == "__main__":
    unittest.main()
