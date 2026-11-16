# discover -> ideate -> pathway to viability (working title: gather-volution)

**Date:** 2026-11-15 | **Status:** Design only, no code | **Name:** undecided (private repo). Original working name `gather-volution`; see "Naming" below
**Not created yet:** repo creation is outside the session that wrote this; create it empty and copy this file to `docs/DESIGN.md`.
**Origin:** extracted from `github-star-organizer` (epic #194, issues #195-#201). This file is
written to be copied into the new repo's `docs/DESIGN.md` unchanged.

## Scope boundary

gather-volution **gathers** repos, products and ideas and carries each one as far as a credible
*pathway to viability*. It does **not** evolve code. Rigorous, budgeted, ledger-backed evolution of
a chosen candidate belongs to the sibling project (VerdantRhizome / `strata`, the multi-fidelity
evaluation layer for program-evolution search). The two meet at a small file contract (see
"Handoff to strata").

```
 gather-volution:  trends -> novelty -> mechanism -> lateral ideas -> viability dossier
                                                                          |
                                         evolution brief (JSON, one per promoted idea)
                                                                          v
 VerdantRhizome / strata:      DesignProblem -> AdapterChain -> TieredEvaluator -> evolved artifact
```

Rule of thumb: if the work needs a search loop or an oracle budget, it is strata's. If it is
about *which* thing is worth searching on and *why*, it is ours.

## Purpose

Watch GitHub for **emerging** repos, decide which are genuinely **novel**, abstract what each
one *mechanically* does, theorize **non-obvious uses** of that mechanism, and end with a
**viability assessment** for the best ideas. The output is a short weekly digest a person can act
on, not an inbox.

## Principles (YAGNI)

- One scheduled GitHub Actions run per week; SQLite for state; Python.
- Public GitHub data only, so the built-in `github.token` suffices. No personal PAT.
- Each stage independently useful and measurable; build in order, stop when value stops.
- Deterministic code for anything checkable (velocity, licence, dedupe, competitor counts);
  LLMs only for judgment (abstraction, ideas, critique).
- No vector DB, no agent framework, no web scraping in v1.

## Pipeline

```
 S1 Trend signal -> S2 Novelty -> S3 Mechanism -> S4 Lateral ideas -> S5 Viability -> Digest
        \______________ state.db (snapshots, scores, ideas) ______________/
```

### S1 Trend signal
- Weekly candidate pull from several slices (recently pushed, recently created, by language,
  by topic), not one top-100 query. Store `star_snapshots(repo_id, date, stars, forks)`.
- **Velocity** = stars gained since last snapshot; **acceleration** after 3+ snapshots.
  Rank by velocity. First useful output appears after two weekly runs.
- Key by GitHub repo `id` (survives rename/transfer).

### S2 Novelty
1. Canonicalize: collapse forks, mirrors, renames, same-homepage duplicates (observed:
   OpenMontage, OmniRoute and career-ops each appeared twice).
2. Cheap score: inverse topic frequency across the stored corpus + TF-IDF cosine of the
   description against previously seen repos.
3. LLM re-ranks only the top ~20 and must name which prior repos each is distinct from.

### S3 Mechanism abstraction
Per shortlisted repo (README excerpt + topics + description), one structured extraction, stored
as JSON: `inputs`, `transform`, `outputs`, `key_capability` (the reusable primitive),
`constraints`, `stated_domain` (what to move *away* from). Malformed output: retry once, skip.

### S4 Lateral ideas
- **Transplant:** force the capability into rotating target domains; the idea must name the
  specific pain removed. Maintain a banned-cliche list (smart mirror, art installation, escape
  room, IoT sensor, gamified training...).
- **Combine:** weekly, pair capabilities with low mutual similarity; propose a product that needs
  both.
- Each idea records: domain, who pays, what it replaces, why now (S1 trend). A self-critique pass
  scores specificity and drops weak ideas.

### S5 Viability (top ~3 ideas/week only)
Rubric 1-5 with a one-line evidence note each: pain and willingness to pay, buildability with the
source repo at the core, moat, distribution path, licence fit (AGPL/GPL constrain commercial
use), timing, key risk. Deterministic inputs: licence from the API, competitor count from a
GitHub search for the capability, last-commit recency, velocity. Ungrounded claims are labelled.
Verdict: pursue / watch / drop + the one fact that would change it. No LLM TAM estimates.

### Handoff to strata
Only ideas with verdict `pursue` leave this repo, as one `briefs/<idea_id>.json`:

| Field | Meaning | strata counterpart |
|---|---|---|
| `problem_id` | stable id, e.g. the idea id | `DesignProblem.problem_id` |
| `description` | the goal in one paragraph | `DesignProblem.description` |
| `sense` | `MAXIMIZE` or `MINIMIZE` | `DesignProblem.sense` |
| `constraints{}` | hard limits from the viability rubric (licence, cost ceiling, safety/boundary notes) | `DesignProblem.constraints`, checked at every tier |
| `budget`, `kappa` | spend ceiling and risk appetite, in **one cost unit per problem** (strata's rule; use USD) | `DesignProblem.budget`, `kappa` |
| `metadata{}` | seed repos with pinned commits, source ideas, `uncertainty_notes` (what we could not ground) | `DesignProblem.metadata` |
| `proposed_tiers[]` | cheap-to-expensive checks that could screen a candidate (T0 shape/licence check, T1 quick prototype or simulation, T2 real-world signal) | `Adapter` fidelity `T0/T1/T2` |

Field names above are copied from `strata/types.py` (`DesignProblem`, `EvalResult`, `Fidelity`,
`Sense`) at commit `75cef5a`. strata's `CLAUDE.md` forbids a `domain` field on adapters, so the
brief carries domain context in `metadata`, never as a top-level typing key.

### The seam: "ecotone"
An ecotone is the transition zone where two ecosystems meet. Use it for the contract, not for
either repo: a versioned JSON Schema (`ecotone/brief.schema.json`) plus a `briefs/*.ecotone.json`
convention, copied (not imported) into both repos with a `schema_version` field. Either side may
change independently as long as it honours the version. YAGNI: no shared package until a second
consumer exists.

gather-volution never imports strata; the brief is plain JSON so either side can change
independently. strata's `sketch` "POD niches" domain (cached scores / scoring API / live listing
performance) is the same shape as a product-viability chain and is the natural first consumer.

### Lessons borrowed from strata (apply to S2 and S5)
- **Never emit a bare score.** Every novelty and viability score carries `value`, `uncertainty`,
  `cost` (tokens), `fidelity` (deterministic check vs LLM rubric vs real-world signal), `feasible`
  and `evaluated_ok`. "Model call failed" must not be recorded as "idea is bad".
- **Audit the cheap filter.** The novelty and dedupe filters will reject some good repos; sample a
  few rejections each week and measure the false-rejection rate rather than assuming it is zero.
- **Winner's curse.** The top idea in a noisy ranking is biased upward; re-score finalists once,
  independently, before the digest.
- **Pessimistic when recording, optimistic when spending.** Report verdicts on the lower bound;
  decide what to investigate further using the upper bound so exploration does not die.
- **Consult the ledger before paying.** Never re-score an unchanged repo; cache by repo id and
  content hash.

### Digest and ledger
One issue per week (or one rolling issue) with: top by velocity, top novel, top 3 ideas with
verdicts. History accumulates in `ledger/` (committed JSON or markdown). Never one issue per repo.

### Eval harness (build alongside S2)
~20 hand-labelled repos (novel / duplicate / hype) and ~10 ideas (specific / generic) in
`tests/fixtures/`; one command prints agreement rates and per-stage token cost. Baseline the
current prompts first so each change shows measured improvement.

## Data model (SQLite)

| Table | Key columns |
|---|---|
| `repos` | `repo_id` PK, `name_with_owner`, `canonical_id`, `license`, `homepage`, `first_seen` |
| `star_snapshots` | `repo_id`, `date`, `stars`, `forks` |
| `novelty` | `repo_id`, `date`, `topic_rarity`, `desc_similarity_max`, `score` |
| `mechanisms` | `repo_id`, `json`, `model`, `created_at` |
| `ideas` | `id`, `repo_ids`, `domain`, `json`, `specificity`, `created_at` |
| `assessments` | `idea_id`, `rubric_json`, `verdict`, `created_at` |
| `run_costs` | `run_date`, `stage`, `tokens_in`, `tokens_out` |

Persistence: Actions cache keyed by run id with restore-keys fallback, plus a `state-backup`
branch (proven pattern in the origin repo; the backup step must run `if: always()`).

## Reusable code in `github-star-organizer` (copy, then adapt)

| Need | Source | Notes |
|---|---|---|
| GraphQL via `gh` + typed errors | `github_star_organizer/gh_client.py` (`run_query`, `GitHubAPIError`, `GitHubAuthError`) | Works as-is. Preflight pattern in `.github/workflows/maintenance.yml` ("Verify GH_TOKEN"). |
| Logging | `github_star_organizer/logger.py` | As-is. |
| SQLite helpers, connection pattern, init | `github_star_organizer/state_db.py` (`_conn`, `init_db`) | Reuse the pattern, not the tables. |
| Cache + backup-branch persistence | `.github/workflows/maintenance.yml`, `discover-repos.yml` | Copy the restore / save / backup steps. |
| Repo search query shape and fields | `discover_repos.py:113` `search_popular_repos` | Replace the single query with the S1 slices. |
| Dedupe against stars | `discover_repos.py:20` `get_current_stars` | Optional filter; may not be wanted here. |
| DeepSeek chat call + JSON-only prompting | `discover_repos.py:200` `_identify_via_deepseek`, `:397` `call_deepseek_summaries`, `distill.py` `call_deepseek` | Reuse request/parse/retry shape. |
| Ollama model fallback | `discover_repos.py:246-390`, `probe_ollama_models.py`, `state_db.py:173-316` | **Do not copy by default.** Revisit only if one provider proves unreliable (YAGNI). |
| Structured per-repo summary prompt | `discover_repos.py:420` | Starting point for S3, rewritten to extract mechanism not purpose. |
| Config validation | `github_star_organizer/config.py` | Pattern only. |
| Plan/spec workflow | `docs/superpowers/` | Same convention. |

Do **not** carry over: `issue_manager.py` per-repo issues, `categorize.py`, Star Lists, keyword
config, `distill.py`.

## LLM plan

| Tier | Provider | Used for | Cost model |
|---|---|---|---|
| Free (default) | Ollama Cloud | S2 re-rank, S3 mechanism extraction, S4 first-pass ideas, most evals | Quota, not dollars |
| Paid (explicit) | NanoGPT, pay-as-you-go | S4 critique pass, S5 viability on the top ~3 ideas, finalist re-scoring | USD, hard cap **$1.50 / rolling 7 days** |

**Ollama Cloud free tier.** Public sources agree on the shape and disagree on the numbers: a
session window (resets about every 5 hours), a weekly window, **one concurrent cloud model**, and
usage measured by GPU time rather than tokens, so heavier models burn quota faster. No reliable
published RPM/TPM figures. So the client must discover limits instead of assuming them:
- Concurrency 1. Retry on 429 and 5xx with exponential backoff honouring `Retry-After`.
- A `quota_events` table (timestamp, model, tokens, latency, status). Treat the first 429 in a
  window as the observed ceiling and stop for that window.
- Work is **resumable**: each item's state lives in `state.db`, so quota exhaustion mid-run defers
  the rest to the next run. It is never an error and never silently falls through to paid.
- Prefer small daily batches over one weekly burst, to fit the session window.
- Choose the smallest model that passes the eval harness (S6), since heavier models cost more quota.

**NanoGPT.** OpenAI-compatible chat completions (`/api/v1/chat/completions`; confirm the base URL
against docs.nano-gpt.com before coding). Billed per model list price; the docs describe an
explicit pay-as-you-go override. Rules:
- Paid calls only when the caller sets `paid=True`. Default is free; the router never upgrades
  silently.
- Before every call, compute the **worst-case** cost (input tokens + `max_tokens` x live price from
  the model list) and refuse if it would push the rolling 7-day sum past the cap.
- Split the cap: ~70% S5 viability, ~20% S4 critique, ~10% reserve. Unused budget does not roll over.
- All spend is recorded in `run_costs` in USD, using strata's convention that cost has one unit
  per problem. Free-tier calls record `cost=0` plus quota units in `provenance`.
- Secrets: `OLLAMA_CLOUD_KEY` (already used by the origin repo) and `NANOGPT_API_KEY` (new).

The router is about 100 lines: `complete(task, messages, paid=False)` -> text + a cost record.
If `AveryRPeterson/llm-gateway-router` already does this, reuse it instead of writing a new one.

## Naming

Candidates considered and how they fit what this repo does (one lineage of mechanism spreading
into many new niches, ending in a viability pathway):
- **Adaptive Radiation** (`adaptive-radiation`): one ancestor diversifies into many forms filling
  new niches. That is S4 almost literally, and "niche" is already strata's vocabulary. *Recommended.*
  `ada-rad` reads oddly (Ada, radiation); prefer the full slug.
- **Speciation Pump** (`spec-pump`): good for ideation, weaker on discovery and viability.
- **Refugium**: where species survive a bad period; fits a ledger/archive more than a pipeline.
- **Trophic Cascade** (`trophicade`): top-down effects; no obvious mapping.
- **Evolutionary Cradle / Ecological Crucible / Alchemize / Bloom**: evoke "evolution", which is
  strata's job; risks blurring the boundary.
- **Ecotone**: best used for the seam contract above rather than a repo.

## Open questions for the owner

1. Repo name: private; undecided between `adaptive-radiation` (recommended) and the original `gather-volution`. See "Naming".
2. ~~LLM provider~~ Decided: Ollama Cloud free tier by default, NanoGPT pay-as-you-go for
   explicit heavy tasks, $1.50 weekly cap.
3. Digest destination: GitHub issue, committed markdown, or both?
4. Any domain focus (e.g. developer tools only) to narrow S1 slices, or everything?

## Milestones

- M0 repo bootstrapped (CI, token-free auth, `state.db` persistence, this doc).
- M1 S1 + eval baseline: velocity list after two runs.
- M2 S2 + S3: novelty-ranked shortlist with mechanisms.
- M3 S4: ideas, judged against the cliche baseline.
- M4 S5 + digest: first end-to-end weekly report.
