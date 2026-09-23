# Junior Syndicate — working rules

These are the working rules for this repository.

**Repo:** HackAlem AI team repository for **Junior Syndicate** (up to 3 people). Remote: GitHub **`BAITC-Hacks/hack-29b2f249-junior-syndicate`**. Branch base: **`main`**.

**Case:** Money Graph — reconstruct the financial structure of an organized group from a transaction network. Track: Analytics and Decision-Making / Cybersecurity and Compliance. Primary user: an AML analyst at a second-tier bank. The tool must answer: which of the 2,248 customers to look at first, and why.

**Bar:** the rules below are mandatory. If a diff introduces a pattern that does not exist in neighboring files in the same area, stop — align with neighbors or get explicit approval before coding. «It works» or «it builds» without a neighbor pass is not done.

This file is a working draft adapted from the team workflow. Project-specific cheat sheets are appended at the end as the codebase appears. Do not import rules from other products unless this team explicitly asks.

## Case constraints (mandatory)

These come from the case brief. A solution that breaks them is not submittable, even if the pipeline runs.

### Product

- Input is a one-off batch: `edges.parquet` (3,119), `nodes.parquet` (2,248), `transactions.parquet` (4,840). July 2026, intra-bank, outgoing transfers only, 4 hops from 81 seed customers, amounts under 5,000 KZT excluded. Total turnover in the graph: 365,890,012 KZT. Field schema lives in the dataset README.
- Graph construction is already done by the organizers. Do not rebuild the sample, do not pull outside transfers, do not invent customer attributes.
- Output is three CSV files plus a viewing screen (web page, notebook, or desktop app):
  - `nodes_roles.csv` — exactly 2,248 rows: `gid`, `role`, `role_score` (0–1), `cluster_id`, `priority_score` (0–1), `evidence` (non-empty, ≤ 200 characters, human-readable).
  - `clusters.csv` — one row per cluster: `cluster_id`, `n_nodes`, `n_seed`, `sum_kzt_internal`, `top_gids`, `hypothesis`.
  - `top_nodes.csv` — ranked list of at least 20 nodes: `rank`, `gid`, `role`, `priority_score`, `why`.
- Role dictionary (minimum; extensions only if documented): `consolidator`, `transit`, `distributor`, `terminal`, `coordinator`, `peripheral`.
- One reproducible command from raw `.parquet` to all three exports. No manual steps. Full recalculation ≤ 5 minutes on this volume, on an ordinary laptop, locally.
- The screen shows a network map with flow direction, highlighted roles and clusters, and search by `gid`. During the demo a named `gid` must be findable with its links.
- README must include: the one run command, role criteria and thresholds, what the output is, limitations, and what would change at ~1 million nodes (text only, no implementation).
- Also required: one diagram `data → metrics → roles → interface`, and a 5-minute demo of a live run plus 2–3 nodes.
- Use the organizers' `starter/` folder. Do not spend the build on boilerplate the starter already covers.
- Optional extras do not block submission: hop-4 artifact handling, temporal patterns, recurring routes and cycles, anomaly detection, resilience if top-N nodes are removed, an analyst Q&A assistant grounded in the graph, an auto node card, a completeness note on missing data. Do not start an optional item until the five must-haves are done.

### Forbidden

- Hardcoding the answer: no lists of `gid`s baked in as the «right» roles or the top list. Roles, scores, clusters, and rank come from calculation on the files.
- A black box: a role without an explainable rule or interpretable features does not count. For each role, document a formal rule or a metric with a threshold. The team must be able to explain any three `gid`s from those metrics within a minute.
- Enriching the data. No external sources. No fields that are not in the export (name, gender, age, income, organization, IIN, balance). Any such field is treated as fabricated.
- Requiring a cloud cluster, GPU training, or a paid service to reproduce the result. Internet is allowed only for an external LLM API, if the team chooses to use one. The pipeline itself must run offline from the parquet files.
- Stating guilt. Wording is a hypothesis for review («signs of consolidation»), not a claim that a customer committed a crime.

### Data traps (accounting for them is scored)

- 444 nodes have `depth=4` and zero outgoing transfers. That is a traversal cut-off, not money that settled. The rule «out-degree = 0 ⇒ terminal» creates 444 false sinks. Separate true terminals from hop-4 artifacts, or do not call those nodes terminals.
- Only outgoing transfers were traced. Incoming flows from outside the sample are invisible. A node's full balance cannot be computed. Do not present in-graph sums as a real balance.
- Seed inflows are understated: the graph was grown from the seeds, so money they received from outside is missing. The sent/received ratio for seeds is wrong. 354 nodes appear to send more than they received. Do not treat that ratio as ground truth for seeds.
- The 5,000 KZT threshold hides structuring below it. Do not claim the graph is complete.
- 19 of 81 seeds are absent from edges; 12 appear only as recipients; 31 seeds have no outgoing transfers. Traversal and seed counts must tolerate that.
- 16 weakly connected components. The largest has 1,877 nodes (46 seeds); 352 nodes sit outside it. Do not assume one monolith. Cluster stats must count seeds per component, not only inside the giant component.
- There is no labeled ground truth. Quality is how well-founded the criteria are, not accuracy against a hidden answer.

### Done means all five

1. One command, three exports, under 5 minutes.
2. Every one of the 2,248 nodes has a dictionary role, `role_score`, and non-empty `evidence`.
3. Criteria and thresholds are written down and match the code.
4. Every node has a `cluster_id`; `clusters.csv` has size, seed count, internal turnover, and a hypothesis.
5. `top_nodes.csv` has ≥ 20 ranked nodes with a rationale, and the map can find a `gid` and show its links.

## 0) Neighbor-first gate (before any code)

Do this before the first edit in a task or review-fix cycle.

1. Name **2–3 neighbor files** in the same flow (screen, endpoint, agent tool, prompt, data model).
2. Open them and note the style already used: naming, layers, error handling, how the UI loads and shows empty/error states.
3. Search the repo for the pattern you plan to add. If this feature would be the **only** hit, the default answer is **do not add it**.
4. If several apps or packages are touched, run the neighbor pass on **every** touched area before saying «готово».
5. Self-review every changed file. «The API is fine, the UI is roughly fine» without a line-by-line neighbor check is a process failure.

If steps 1–3 were skipped and the same rule has to be repeated, that is an agent defect, not a new requirement.

## 1) Approval before changes

- For each new task: look at the repo first, then give a short plan.
- Do not edit code, configs, styles, or structure until explicit approval (`yes` / `да` / `делай` / `можно`).
- A detailed or imperative request («убери X», «почини Y») is **not** approval to execute. Stop after the plan and wait.
- After approval, implement only the agreed plan.
- If scope changes, pause and ask for new approval.

### Plan before the first line of code

Checklist before coding:

1. The problem in one sentence.
2. The minimum data needed end to end.
3. Screens and endpoints as a list.
4. What is consciously **out of scope**.
5. An explicit «делай» after the plan.

Without this, stop. Do not write code.

## 2) Git intent before action

Before any Git action, state what will be done and why: branch, merge, rebase, cherry-pick, commit, push, force-push, history rewrite. Run those commands only after explicit approval.

Three separate approvals:

| User words | Allowed | Not allowed |
|------------|---------|-------------|
| «делай» / «делай по ревью» | file edits, local checks | `git commit`, `git push` |
| «коммит» / «закоммить» | `git add` + `git commit` | `git push` |
| «пуш» / «запушь» / «можно пушить» | `git push` | — |

- Fixing code after review is not permission to commit.
- Do not push right after «делай по ревью» unless push was also approved.
- One task = one branch = one focused story. Do not mix unrelated work.
- Start a new task branch from latest `main` (or the agreed base).
- Do not push work directly to `main`. Use a branch; merge to `main` only after review.
- Before commit or push, `git branch --show-current` must match the agreed task branch. Do not commit task A onto a leftover branch from task B.
- When asked for a targeted commit or push, name the branch first and abort if it disagrees with the task.
- Stage only task-scope files with explicit paths. Do not commit secrets, tokens, `.env`, or local-only config drift.
- Commit messages: short, focused on why. If the team agrees a task code, start the message with it.

### Local files vs remote

- «Откати на remote» / «убери с GitHub» changes **only** `origin/<branch>`. Do not `git reset --hard` the working copy while someone is testing locally.
- Force-push only on a feature branch, and only when the user explicitly asks. Never force-push `main`.
- Typical order after review: edit locally → user checks → commit on request → push on request.

## 3) Root cause first

For bugs, find the cause before fixing. Prefer a small fix of the confirmed cause. Do not patch symptoms in a loop.

- Do not announce one confident cause («сеть», «база», «окружение») from a local failure alone.
- Trace the real path first (UI → client → handler → data). Rank at least two hypotheses when both code and environment are plausible.
- A local timeout or connection error is local evidence only.
- Do not claim the symptom is fixed until it is shown on the scope of the task.

## 4) No code comments by default

Do not add source comments unless the user asks. Prefer clear names and structure.

Keep user-facing text in the place this repo already uses for copy (one module, one locale file). Do not hardcode a second label map beside an existing pattern.

## 5) Match existing style

New code must read like the rest of this repo: names, folders, layers, errors, formatting. Open a nearby file and mirror it.

- Extend the owner of a feature. Do not add a parallel service, util, or wrapper for a sub-feature of an existing area.
- Do not add a new file type (`*.utils`, extra helper module, one-off type declaration) if neighbors do not have it.
- Rules copied from another product are not applied here unless this team asks.

## 6) Simplicity and scope

Good code solves the real problem and stays easy to maintain. More code, cache, TTL, or «that's how another project does it» is not better work.

- One change should read as one story: minimal diff, no drive-by refactors, no extra layers.
- Do not add cache-busting, smart URL helpers, or «for later» infrastructure unless the task asks for it.
- Prefer one clear path for one logical update.
- If you cannot explain in 2–3 sentences why a layer, validation, or cache exists, do not add it.
- Do not spread unrelated work through one change when it can stay narrow.
- Infrastructure and feature work stay separate unless the task is both.

## 7) Contracts and the full path

When adding or changing something the UI or another agent calls:

1. Explicit request and response shapes. No ad-hoc JSON walking or stringly-typed bodies for normal flows.
2. Mapping in the same place neighbors already map.
3. Business rules where this feature already puts them, not piled into the entry point.
4. A thin entry point: check, call, return. Match sibling actions.
5. The caller in the same change: method, path, body, and response type match the contract.

Do not ship a contract change and leave the client on a dead call.

Before inventing a pattern, read history on similar files and align with what is already in the repo.

## 8) Lists, filters, and display

- Product rules for which rows exist, how they are ordered, and how a name is displayed belong on the server (or the single owner of that data), not only in the browser.
- Do not fetch everything and then filter or sort on the client when that narrowing is a product rule.
- Role-scoped lists are enforced where the data is read, not only after a generic «all rows» response.
- One business field uses one name across the stack. Do not mix two words for the same meaning.
- Do not encode display heuristics on the client («if the name looks like an email, hide it»). Normalize once and bind to that field.

## 9) Bulk actions

A mass operation (save all, approve all, and similar) is **one** call with an explicit contract. Do not loop single-item requests from the client, and do not mirror that loop on the server. The server runs one business operation for the batch.

## 10) Thin UI, obvious code

- The screen requests and renders. Filtering, sorting, and filter options stay with the data owner.
- Do not nest subscriptions or callbacks when neighbors use a plain load method.
- Reset loading flags on both success and error, the same way neighbors do.
- Prefer constructor or the injection style already used in that folder. Do not mix styles in one file.
- Names are the shortest that a reviewer understands in one read: `loadList`, `isSaving`, not opaque or overlong technical names.
- Boolean UI state names say what the user is waiting on.
- Shared request and response types live where neighboring features already put them.
- Do not keep a second client array only to re-filter or re-sort.
- Do not add a private helper with one call site. Keep straightforward inline code unless siblings already share that helper.
- Prefer a few clear branches over a dense one-liner.

## 11) UI sells the work

A clear screen can carry a simple model. A bad screen wastes a correct model.

- Before «готово», open the screen as a user: flow, copy, spacing, loading, empty, and error states should match neighboring screens.
- User-visible text describes only what the screen actually does.
- A control exists only when the path behind it works end to end.

## 12) Helpers and wrappers

Do not add a new response wrapper, private validator, or formatter when the same logic can stay inline and nearby files do not use that helper — especially with a single call site.

For a review fix, the smallest diff that answers the comment. Do not introduce a new abstraction.

## 13) Review direction

- A reviewer’s requested approach replaces the previous one, even if the old one works locally.
- A review comment that asks a question («зачем убрал?») needs a short reply, not an automatic revert, and not an unrequested commit or push.
- Map every active comment to a concrete change before coding.
- A rename or architecture comment applies to the whole feature path, not only the highlighted line, unless the reviewer limited the scope.
- Do not reintroduce a close variant of a pattern the reviewer just rejected.
- Do not say the change is ready until each comment maps to file and lines, and the neighbor pass has been run on every touched area.

## 14) Pre-commit checklist

- Neighbor-first gate done for every changed file.
- Current branch matches the agreed task.
- Active review comments are mapped to exact changes.
- Diff is task-scope only.
- Names are clear in one read.
- No one-off helpers, no client-side product filters, no secrets.
- Case constraints still hold: no hardcoded `gid` lists, no invented customer attributes, no guilt wording, hop-4 nodes are not naive terminals, roles stay explainable, exports match the fixed schemas.
- Local check for what was touched (build, tests, or the app flow) shows no new errors.
- Commit and push only after the matching explicit request in §2.

## 15) Choosing work

Do not pick a task blind. Look at the product and `main`, then propose the task with a reason: what is missing, why it helps the user, what already exists to mirror.

- One clarifying question on the product model, then wait, then the plan, then «делай».
- Do not build a control «for show» without the real integration.
- Do not start a feature while a teammate owns that area in an open change — agree first.
- Better to spend time agreeing than to merge work that contradicts the product.

Self-check before calling it done:

1. Is the screen understandable, like neighboring screens?
2. Does the whole chain work, not only compile?
3. Is there any request loop?
4. Can the code be read once, with no method that exists for a single call?
5. Are we duplicating a neighbor endpoint or service?

## 16) Cheat sheets

When the same feedback repeats, add a short section at the end of this file: topic, wrong, right. Do not rewrite the whole file after every review. If the feedback repeats an existing rule, still add a row — it marks a repeated failure, not a new optional hint.
