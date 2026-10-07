---
name: icml2026-agent-repro-logbook-submission
description: |
  Publish a compliant reproduction logbook to the ICML 2026 Agent Reproducibility Challenge
  (HF org ICML-2026-agent-repro). Use when: (1) you need a paper's challenge paper-id, (2) you
  are about to `trackio logbook publish` for the challenge, (3) the "Start here" quick-guide's
  `<username>/<paper-id>` publish target looks wrong, (4) `trackio logbook publish` fails to
  promote dashboards with `402 Payment Required`, (5) the leaderboard is not discovering a
  published logbook, (6) a submission scored 0/N pts (or lower than expected) on the
  leaderboard and you need to know how points are computed or how to get re-judged. Covers
  finding the paper-id from the challenge Hub dataset, the REAL slug/tag/structure requirements
  (which differ from the quick-guide), the official scaffold + validator, the
  PRO-for-dashboards gotcha, and the Logbook Judge scoring mechanics (registry claims, not
  your own; 2/1/0 per claim; re-judge on republish).
author: Claude Code
version: 1.1.0
date: 2026-07-22
---

# Publishing to the ICML 2026 Agent Reproducibility Challenge

## Problem
The Space "Start here" quick-guide says `trackio logbook publish <your-username>/<paper-id>`,
which is **misleading**. The real requirements are in the challenge's Hub dataset + README, and
publishing the quick-guide way creates a stray, non-discoverable public Space with the wrong name.

## Where the authoritative info lives (fetch these first)
- **Papers registry** (has every paper-id): the Hub dataset `ICML-2026-agent-repro/challenge`,
  file `papers.json` (~11 MB). HF LFS/xet-redirects, so `curl -L`.
- **The real rules**: `README.md` and `challenge.json` in that same dataset.
- **Official scripts** (the canonical path): the challenge Space raw URL
  `https://huggingface.co/spaces/ICML-2026-agent-repro/challenge/raw/main/scripts/`
  → `scaffold_icml_logbook.py` and `validate_icml_logbook.py`.

## 1. Find the paper-id (it's the OpenReview id `orid`)
```bash
curl -L "https://huggingface.co/datasets/ICML-2026-agent-repro/challenge/resolve/main/papers.json" -o papers.json
python3 -c "
import json; root=json.load(open('papers.json'))
# root = {'papers':[{...}], 'abstracts':{orid:text}, 'areas':..., 'areaTree':...}
for p in root['papers']:
    if '<arxiv-id-or-title-substring>'.lower() in json.dumps(p).lower():
        print(p['orid'], '|', p['title'])"
```
Each entry in `root['papers']` has `orid` (OpenReview base62 id, e.g. `v2rdJBVVEt`), `title`,
`arxiv`, `pid`, virtual-poster url. **The `orid` is the challenge paper-id.** `root['abstracts']`
is keyed by orid (useful for matching by abstract text).

## 2. The REAL publish target and tags (not the quick-guide's)
- **Space slug = `repro-<slugified-paper-title>`** (lowercase, non-alnum→`-`, max 96 chars),
  **NEVER the OpenReview id**. The validator rejects an orid-looking slug.
- **Required metadata tags** in `./.trackio/metadata.json`: `["icml2026-repro", "paper-<orid>"]`.
  *Without them the leaderboard cannot discover your logbook.*
- The published Space is a **static** SDK Space (free); tags land in its README on publish/sync.

## 3. Use the official scaffold (don't hand-roll the structure)
```bash
curl -L ".../scripts/scaffold_icml_logbook.py" -o scaffold.py
python3 scaffold.py --title "<exact paper title>" --orid <orid> --arxiv <arxiv-id> \
  --openreview-url "https://openreview.net/forum?id=<orid>" --username <hf-user> \
  --claims-json '["claim 1 text","claim 2 text"]'
```
This creates `./.trackio/logbook/` with: index (title + Pages table only), `executive-summary`
(a **pinned** markdown cell titled "Executive summary" + a **pinned** figure titled
"Reproduction poster"), one `claim-N-...` page per claim, and `conclusion`. Then fill each page
with `trackio logbook cell markdown/dashboard/...`. Keep the pinned exec-summary cell and pinned
poster cell — the validator requires them.

**CRITICAL — `--claims-json` must be the challenge's OWN claims for your orid, not claims you
chose yourself.** The Logbook Judge scores against the challenge's per-paper claim registry
(`claims_anchored.json`, falling back to `claims.json`, both in the challenge Space repo).
A logbook organised around self-chosen claims scores 0 on every registry claim it never
addresses, however good the runs are. Fetch them first:
```bash
curl -sL "https://huggingface.co/spaces/ICML-2026-agent-repro/challenge/raw/main/claims_anchored.json" | \
  python3 -c "import json,sys; [print(f'{i}. {c[\"text\"]}') for i,c in enumerate(json.load(sys.stdin).get('<orid>',[]),1)]"
```

**Scaffold bug to fix before validating:** the scaffold writes a paper link into `index.md`, but
the validator requires the index to contain **only** the title + Pages table. Delete the
`[OpenReview paper](...)` line from `pages/index.md`.

## 4. Validate LOCALLY before publishing (it's irreversible)
```bash
curl -L ".../scripts/validate_icml_logbook.py" -o validate.py
python3 validate.py         # runs on the local ./.trackio/logbook, no --space needed
```
Checks: both tags present; slug starts `repro-` and isn't an orid; index = title+TOC only; first
page `executive-summary`, last `conclusion`, middle `claim-*`; pinned exec-summary markdown +
pinned poster figure; a Hub or GitHub URL somewhere. Fix every `error:` until "validation passed".

## 5. Publish, and the 402 gotcha
```bash
trackio logbook publish <hf-user>/repro-<slug>
```
- The **static logbook publishes free** and is the actual submission (judgeable from markdown).
- **Promoting live Trackio dashboards to Gradio Spaces fails with `402 Payment Required`** unless
  the account has **HF PRO** ("hosting Gradio/Docker Spaces on free cpu-basic requires PRO"). The
  metric data still uploads to a bucket; the dashboard *cells* just won't render live charts. This
  is a billing limit, NOT a token-scope problem — a plain write token/OAuth still publishes the
  logbook fine. To get live dashboards: subscribe to PRO, then `trackio logbook sync`.

## The 96-char slug trap (publish hard-fails, Space silently NOT updated)
Verified 22/07/2026. If the slugified paper title hits the 96-char Hub repo-name cap (long
titles do), trackio's auto-derived companion repos `<base>-traces` and `<base>-artifacts`
exceed the cap and cannot be created — and that failure **aborts publish BEFORE the static
Space is pushed**. Symptom: publish prints errors mentioning "max length is 96", and the
Space's `sha` (check `https://huggingface.co/api/spaces/<id>`) is UNCHANGED — the judge
never sees your update. **Always verify the sha advanced after every publish.** Fixes:
- **Artifacts bucket IS overridable**: set `"artifacts_bucket": "<user>/<short>-artifacts"`
  in `.trackio/metadata.json` (honoured at `trackio/logbook.py` `metadata.get("artifacts_bucket")
  or f"{owner}/{name}-artifacts"`). Publish then succeeds.
- **Trace dataset is NOT overridable** (unconditional `f"{owner}/{name}-traces"`): remove the
  attached trace (`trackio logbook remove trace <session-id>`), preserve it manually
  (`hf upload <user>/<short-name> .trackio/logbook/traces/<session-id> --repo-type dataset
  --private`), and link it from the Conclusion with a note explaining why the Traces tab is
  empty.
- The 402 dashboard-promotion error remains non-fatal (PRO gotcha above); do not confuse the
  two — the length errors are the ones that abort.
Also: rerunning any SELFRec-clone config for evidence needs a fresh `--seed` (an `Exists!`
guard on the log filename silently skips; a `| grep` pipe hides both the skip and exit code).

## How scoring actually works (the Logbook Judge)
Verified 22/07/2026 by reading `leaderboard.js` in the challenge Space, the
`ICML-2026-agent-repro/logbook-judge` Space (README + `app.py`), and the live verdicts dataset.

- **Discovery**: the judge service scans every minute for Spaces tagged `icml2026-repro` +
  `paper-<orid>`; every 5 minutes an LLM judge (`zai-org/GLM-5.2` via HF Inference Providers,
  env-overridable) drains the queue.
- **What it judges**: the logbook text against the **registry claims for the orid**
  (`claims_anchored.json` > `claims.json`). Your own claim framing is treated as an untrusted
  assertion; the judge independently assesses setup, runs, artifacts, and numbers.
- **Points per claim**: `verified` = 2, `falsified` = 2, `toy` = 1, `inconclusive` = 0.
  Leaderboard max = (number of registry claims) × 2 (e.g. 6 claims → "/12 pts").
- **Verdicts are public**: `https://huggingface.co/datasets/ICML-2026-agent-repro/verdicts/`
  `resolve/main/verdicts.json`, keyed by space id — each entry has per-claim verdict + evidence
  text, the judged revision `sha`, model, and an `overall` note. Read it to see exactly why
  points were lost.
- **Re-judging**: the judge skips a Space only while its revision sha matches the last judged
  sha (`app.py`: `if prev and prev.get("sha") == lb["sha"]: skip`). **Republishing the updated
  logbook (new sha) triggers a fresh judgment automatically** — no manual step.
- **Do NOT create a second Space for the same paper**: the leaderboard keeps one canonical
  logbook per (user, orid) and prefers the first Space that received a verdict, so a new Space
  will not replace an already-judged one. Update the original.
- **Theory/analysis claims in the registry count**: a numerical audit (implement the setup,
  check the stated equalities/gradients hold, add a relaxed-condition control) is the expected
  reproduction for theorem-like claims and needs no GPU. Skipping them = 0 pts each.
- **Partial numeric matches fail**: for a claim like "improves metric from A (baseline) to B",
  reproducing B and the ordering is not enough — if the baseline A is far off the paper's
  value, the *relative gain* is unconfirmed and the claim goes `inconclusive`. Depressed
  baselines cost points; fix baseline hyperparameters before republishing.
- **The judge reads ONLY the logbook markdown** (`logbook_md`, may be truncated) and follows a
  strict INDEPENDENCE RULE: it ignores every self-reported verdict/status ("we verified X" is
  worthless) and judges only from concrete setup, commands, artifacts, and numbers *in the
  markdown*. Consequences, verified against `logbook-judge/app.py` (JUDGE_SYSTEM): (a) put the
  evidence INLINE on each claim page — a linked GitHub repo or bucket data is NOT read; (b) every
  claim page must carry "paper reports X, I measured Y" with the command/setup that produced Y;
  (c) front-load the numbers (truncation drops the tail); (d) "verified" (2 pts) needs concrete
  evidence on a NON-toy setup — a documented backend/model substitution at real scale is NOT toy,
  but a data subset / proxy task / far-smaller model IS. This inline-numbers discipline is the
  single biggest lever between 0/N and 2N/N.
- **Leaderboard rank = SUM of points across ALL of a user's papers** (`leaderboard.js`: one
  scoring logbook per paper, points summed per user). One 12/12 gets you on the board; leading
  needs VOLUME of perfect papers. The top of the board is dominated by **theory / optimization
  papers** (mirror descent, FTRL, k-means, Adam bias, NMF, error-feedback) — CPU-trivial, claims
  = proofs / small numerical experiments → easy `verified`. This is the efficient path to points:
  batch-reproduce optimization papers, each to 12/12, using [[choosing-a-reproducible-paper-target]].

## Scope / GPU expectations (affects scoring, not publishing)
- The README treats **local/CPU as smoke-test tier**; the substantive run "should" be a HF **GPU
  Job** (recorded Job URL, GPU flavor, cost). GPU Jobs need a `job.write`-scoped token under the
  user's OWN namespace (the org does not grant job.write) and **credits** (402 if none; the free
  $20 credits were exhausted by 17 Jul 2026).
- BUT `toy` is defined as *reduced scale/scope* (data subsets, proxy tasks, sub-class models). A
  **full-data, full-protocol run on CPU that matches the paper's numbers is a legitimate full
  reproduction**, honestly labelled as CPU-run — fine for the certificate-of-participation path.
- A documented backend/model swap alone does NOT make a reproduction `toy`.

## Notes
- Submission = joined org + published logbook carrying the two tags. Discovery is tag-based; no
  separate "submit" step.
- The Conclusion must carry a reproduction bundle (via `trackio.log_artifact()` on a bucket) OR at
  minimum link the code repo; code cells alone "do not count" per the README (bundle needs write).

## Batch-reproduction campaign (the volume path to leaderboard points)

Proven 22/07/2026. Command centre: `~/development/projects/icml2026-campaign/`. Pipeline:
1. **Screen the registry.** Fetch `papers.json` (6341 papers; `papers[]` has orid/title/area/
   arxiv, `abstracts` keyed by orid) + `claims_anchored.json` (per-orid claims). Filter to
   areas **Theory (452) / Optimization (230) / Probabilistic Methods (179)** and rank by claim+
   abstract keywords that signal a self-contained numerical/theoretical audit (converg/rate/
   regret/bound/gradient/variance/...) minus GPU-scale signals (imagenet/llm/transformer/...).
2. **Discovery workflow** (sonnet, ~40-50 agents, one per candidate): each reads the claims+
   abstract and returns per-claim reproducibility + a concrete from-scratch experiment + go/no-go.
   ~85-95% come back `go`. Append go-papers to a `go_list.json` (NEVER re-sort — reproduction
   batches reference papers by index).
3. **Reproduction pipeline** (opus, `pipeline(indices, implement, verify, logbook)`): implement
   agent WebFetches the arxiv, writes+RUNS `repro.py` (numpy/scipy), reports "paper says X /
   measured Y" per claim; verify agent RE-RUNS the script and corrects/downgrades any number that
   doesn't match (the honesty firewall); logbook agent scaffolds + fills inline + validates.
   ~8 papers/batch, ~45 min wall-clock; batch 1 validated 8/8.
4. **Publish** sequentially with a slug-guard helper (`publish_paper.py`) + verify sha advanced.

**Key unlock:** most theory/optimization claims reproduce WITHOUT the authors' repo — implement
the stated setup from the paper, measure the rate/identity/bias, add a relaxed-condition control.
This removes the clone-and-patch-GPU-code failure mode entirely.

## toy vs verified — the calibration that decides 1 vs 2 pts/claim
- **Empirical/benchmark paper** (e.g. eNMF): demonstrating a claim on a synthetic slice or a
  data subset scores **toy (1)**, not verified. Verified needs the paper's ACTUAL datasets +
  scale. (eNMF exact-recovery slice → 6/12: 1 verified, 4 toy, 1 inconclusive.)
- **Theory/theorem paper**: a faithful from-scratch audit of the EXACT stated setup (same
  function/dimensions/constants) PLUS a falsification control (set the condition just outside its
  stated bound and show the property breaks) is the expected reproduction → **verified (2)**.
  A shrunken proxy or wrong-scale test → toy. Make agents match the paper's literal setup.
- **Judge queue delay:** verdicts lag publication by many minutes to hours (one judge draining
  2758+ submissions). Do NOT gate batch launches on verdict feedback — trust the agents' honest
  self-classification and keep throughput up; poll `verdicts.json` opportunistically.
- **`verdicts.json` is keyed by space_id; the same `orid` appears for MANY users** (everyone who
  reproduced that paper). Always filter by your username before reading per-claim detail, or you
  will analyse a stranger's logbook.

## The three failure modes the judge actually penalises (measured over 60 toy/inconclusive claims, 23/07)
A logbook's own `repro.py` printing "verified" does NOT mean the judge agrees — the judge is
stricter, so run.log-parsed score estimates run HOT (e.g. a paper self-scoring ~12 was judged 7).
The weak claims cluster into three fixable modes; an improve pass must target all three, not just scale:
1. **Reduced scale (~1/3):** scalar/d=1/d=2 setups. Fix: the paper's actual dimension (d=50-200+), real problem family, adequate seeds.
2. **Not faithful to the paper's setup (~1/5):** a proxy, a DIFFERENT algorithm, or — the big one — a "construction that trivially attains the bound" (an equal-tail/boundary instance that pins a constant at the sandwich edge instead of EXHIBITING the rate). Fix: implement the paper's EXACT algorithm on its actual generic/hard instance so the result EMERGES; never satisfy a bound by construction.
3. **Exponent/constant mismatch (~1/5):** measured 1.22 vs paper's 1.0, slope off. Usually not in the asymptotic regime. Fix: increase T/n/d until the measured exponent CONVERGES (log-log tail fit, drop the transient).
The rest (~1/8) are genuinely unfixable on CPU (needs real proprietary data, GPU-scale nets, or a
minimax/lower-bound proof over ALL algorithms) — leave those honestly toy/inconclusive.

## THE binding constraint: 20 new Spaces per day (plan around it)
Verified 22/07/2026: HF caps **Space creation at 20 per day** per account. The 21st
`trackio logbook publish` of a NEW slug fails with `429 ... rate limit for space creation
(20 per day). You can retry this action in 1 day`. Consequences for a batch campaign:
- **The scarce resource is the 20 daily slots, NOT reproduction throughput.** Reproduction can
  build 60+ validated logbooks, but only 20 become live Spaces per day. So spend slots on the
  HIGHEST-expected-score papers first; keep the rest as inventory to publish when the quota frees.
- **Republishing an EXISTING space ALSO counts against the 20/day cap** (verified 23/07 — a
  republish while at the limit fails with the SAME `429 space creation (20 per day)` and the sha
  does NOT advance). `trackio logbook publish` makes `create_repo` calls for the space + its
  `-traces`/`-artifacts` companions on every publish, and those hit the creation limiter. So
  score improvements (strengthening toy/inconclusive claims) do NOT re-judge for free — they
  compete with new publishes for the daily 20 slots. Queue them in the drainer alongside new
  inventory, ranked by value (republish value = improved score); they publish when the quota
  frees. It DOES re-judge once it goes through (new sha), it just isn't unlimited.
- **Reset appears to be a rolling ~24h** ("retry in 1 day"); it MAY align to 00:00 UTC. Don't
  assume — attempt a pending publish shortly after the expected reset and check whether it 201s.
- **Value per slot is the whole game** (verified 24/07): a slot spent on a NEW improved paper
  earns its FULL score (~+8-12); a slot spent REPUBLISHING an already-live paper earns only the
  DELTA (new-old, ~+2-4; gxxOL0iXpr 6→7 was +1). So a new paper is 2-5x better per slot. Rank the
  drainer by MARGINAL GAIN (new=exp_pts, republish=improved-judged) → new inventory always
  publishes before republishes; the republishes fire only once new inventory is exhausted.
- **Therefore: improve INVENTORY before it publishes (free, no slot — lifted first-judge avg 8→10.3),
  but do NOT burn slots republishing live papers while un-published inventory exists. Reproduce
  MORE new papers instead** — that keeps the ~19/night pipeline fed at +8-12/slot.
- **Best of all: bake the three failure-mode fixes (faithful scale / exact-algorithm-emerges /
  asymptotic regime) into the REPRODUCTION prompt** so new papers score ~10/12 on first publish —
  eliminates the reproduce-then-improve two-step entirely.
- Practical loop once at the cap: (a) keep reproducing NEW papers (enhanced prompt) to grow a
  prioritised inventory; (b) publish new spaces top-of-inventory-first as slots free; (c) republish
  improved live papers ONLY as a last resort when inventory is empty.

## Operational gotchas (batch publishing)
- **96-char slug trap at scale:** long paper titles produce slugs where `slug+"-traces"` > 96 →
  publish aborts silently. The traces repo name is NOT overridable, so **shorten the slug in
  `.trackio/metadata.json` `space_id` to <=85 chars** (cut at a hyphen, keep `repro-` prefix)
  before publishing. Then verify the space sha advanced + both discovery tags present.
- **Scaffold "File name too long":** the installed trackio may lack `lb.scaffold_icml_logbook`
  and fall back to slugging page dirs from FULL claim text → OSError Errno 63 on long claims.
  Pass CONCISE labels to `--claims-json` (slugs only need the `claim-N-` prefix) and put the
  EXACT registry claim text verbatim in each page's H1 + body.
- **Validator takes no positional arg:** run `validate_icml_logbook.py` BARE from the paper dir
  (it reads `metadata.space_id`); passing `.` errors. A "no GitHub URL" warning is fine for a
  no-code theory paper — do not fabricate a repo URL.

## References
- Challenge Space: https://huggingface.co/spaces/ICML-2026-agent-repro/challenge
- Related: `selfrec-recsys-reproduction-cpu-patches` (the actual repro patches for this paper family).
- Related: `workflow-args-defensive-parse` (the discovery/reproduction workflows depend on it).
