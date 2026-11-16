"""Deterministic, LLM-free matching of starred repos to Star Lists.

Pure functions only: no network, no env, no clock. The orchestration (fetching,
mutating, quotas) lives in categorize.py / star_lists.py.

Score = fraction of the repo's (IDF-weighted) token mass that a list's profile
already covers. A list profile is learned from the repo members already in the
list, plus the list name and any seed keywords from config.json.
"""
import math
import re
from collections import Counter

STOPWORDS = frozenset("""
a an and are as at be by for from has have in into is it its of on or that the this to
with your you our their using use used based simple fast new best awesome tool tools
library lib app apps project projects repo repository github open source free
""".split())

# Weights by where a token came from: topics are curated, descriptions are noisy.
W_TOPIC, W_NAME, W_DESC = 3.0, 2.0, 1.0
W_SEED = 2.0  # list name / config keywords


def _stem(tok: str) -> str:
    if len(tok) > 3 and tok.endswith("s") and not tok.endswith("ss"):
        return tok[:-1]
    return tok


def tokenize(text: str | None) -> list[str]:
    toks = re.findall(r"[a-z0-9]+", (text or "").lower())
    return [_stem(t) for t in toks if len(t) > 1 and t not in STOPWORDS]


def topic_names(repo: dict) -> list[str]:
    nodes = (repo.get("repositoryTopics") or {}).get("nodes") or []
    return [n["topic"]["name"].lower() for n in nodes if n and n.get("topic")]


def repo_tokens(repo: dict) -> Counter:
    c: Counter = Counter()
    for topic in topic_names(repo):
        for t in tokenize(topic):
            c[t] += W_TOPIC
    name = (repo.get("nameWithOwner") or "").split("/")[-1]
    for t in tokenize(name):
        c[t] += W_NAME
    for t in tokenize(repo.get("description")):
        c[t] += W_DESC
    return c


def build_profiles(lists: dict[str, dict]) -> dict[str, Counter]:
    """lists: {name: {"members": [repo dict], "keywords": [str]}} -> {name: token Counter}."""
    profiles: dict[str, Counter] = {}
    for name, info in lists.items():
        p: Counter = Counter()
        for member in info.get("members", []):
            # Normalize each member to a unit mass so one verbose repo can't dominate.
            toks = repo_tokens(member)
            total = sum(toks.values()) or 1.0
            for t, w in toks.items():
                p[t] += w / total * 3.0
        for t in tokenize(name):
            p[t] += W_SEED
        for kw in info.get("keywords", []):
            for t in tokenize(kw):
                p[t] += W_SEED
        profiles[name] = p
    return profiles


def _idf(profiles: dict[str, Counter]) -> dict[str, float]:
    n = len(profiles)
    df: Counter = Counter()
    for p in profiles.values():
        df.update(p.keys())
    return {t: math.log((1 + n) / (1 + d)) + 1.0 for t, d in df.items()}


def score_repo(repo: dict, profiles: dict[str, Counter]) -> dict[str, float]:
    """Coverage score in [0, 1] of the repo against every list profile."""
    toks = repo_tokens(repo)
    if not toks or not profiles:
        return {name: 0.0 for name in profiles}
    idf = _idf(profiles)
    default_idf = math.log(1 + len(profiles)) + 1.0  # tokens no list knows
    mass = {t: w * idf.get(t, default_idf) for t, w in toks.items()}
    total = sum(mass.values())
    scores = {}
    for name, p in profiles.items():
        covered = sum(m * (1 - math.exp(-p.get(t, 0.0))) for t, m in mass.items())
        scores[name] = covered / total
    return scores


# Absolute minimum score for placing into an existing list, however many lists exist.
# Below this the fit is too weak to trust; the repo stays unplaced instead.
MIN_ACCEPT = 0.30


def accept_threshold(n_lists: int, base: float = 0.45, floor: float = 0.12,
                     scale: float = 6.0) -> float:
    """Minimum score to accept an existing list. Falls as lists accumulate, so the
    matcher works harder to reuse a list the more lists already exist."""
    return max(floor, base / (1.0 + n_lists / scale))


def best_match(repo: dict, profiles: dict[str, Counter]) -> tuple[str | None, float]:
    """(list name, score) of the best list if it clears the threshold, else (None, best score)."""
    scores = score_repo(repo, profiles)
    if not scores:
        return None, 0.0
    name = max(sorted(scores), key=lambda n: scores[n])
    if scores[name] >= max(MIN_ACCEPT, accept_threshold(len(profiles))):
        return name, scores[name]
    return None, scores[name]


def min_cluster(n_lists: int, base: int = 3, per: int = 10) -> int:
    """Unplaced repos that must share a topic before a new list is justified.
    Grows with the number of lists, making creation harder as the set grows."""
    return base + n_lists // per


def propose_new_lists(unmatched: list[dict], existing_names: list[str],
                      max_new: int, min_size: int) -> list[tuple[str, list[dict]]]:
    """Group unplaced repos by a shared topic; propose at most max_new lists.

    A topic qualifies if >= min_size unplaced repos carry it, it is not already
    expressed by an existing list name, and it is not so common among the unplaced
    that it carries no signal (>60% of them, when there are enough repos to judge).
    """
    if max_new <= 0 or len(unmatched) < min_size:
        return []
    covered = {t for n in existing_names for t in tokenize(n)}
    by_topic: dict[str, list[dict]] = {}
    for repo in unmatched:
        for topic in set(topic_names(repo)):
            by_topic.setdefault(topic, []).append(repo)
    generic_cap = 0.6 * len(unmatched) if len(unmatched) >= min_size * 2 else len(unmatched) + 1
    candidates = [
        (topic, repos) for topic, repos in by_topic.items()
        if len(repos) >= min_size
        and len(repos) <= generic_cap
        and not (set(tokenize(topic)) and set(tokenize(topic)) <= covered)
    ]
    candidates.sort(key=lambda tr: (-len(tr[1]), tr[0]))
    out: list[tuple[str, list[dict]]] = []
    used: set[str] = set()
    for topic, repos in candidates:
        if len(out) >= max_new:
            break
        members = [r for r in repos if r["nameWithOwner"] not in used]
        if len(members) < min_size:
            continue
        used.update(r["nameWithOwner"] for r in members)
        out.append((topic.replace("-", " ").title(), members))
    return out
