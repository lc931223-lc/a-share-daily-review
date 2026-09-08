# Phase A2.1 Production Remediation

Baseline: fde4a0060c5fc56055f3ce72dc4eef1e8f098eec.

## A. Before

P0 confirmed: live collection slept to 09:30:05; no morning scheduler; the new
canonical formal record was not projected into the old auction contract; no real
live E2E acceptance. An additional timing issue was synchronous 60-day network
baseline backfill before live collection. P1: sector breadth counted as market
environment, catalyst tier alone assigned 15 points, generic earnings keywords
caused negative deductions, prose checks used breadth proxies, post-open rewrote
the original report.

## B. Changes

- live_runner / pipeline: end immediately after formal match, cached-only baselines,
  no realtime-open call in Stage A/B, source deadline, strict event-time cutoff.
- production: durable stages, frozen raw collection recovery, packet SHA reuse,
  independent timestamped post-open snapshots and separate EOD result.
- score_rules / scoring / conditions / verification: availability-aware fixed
  rubrics, negative semantic rule IDs, supported predicates, direction contract guard.
- formal_review delivery/persistence: canonical v3 remains authoritative; immutable
  official_reviews projection, import-ready queue and consolidated ChatGPT input.
- previous_context / watchlist: exact prior canonical review, legacy-shape projection,
  no rejected simulated review leaking into candidate roles.
- schemas: optional structured tomorrow_checks, timeliness and frozen-report fields.
- tools: bounded scheduled runner, preflight, local task installer, production validator.
- workflows: standalone auction live, post-open/EOD and Ubuntu connection probe;
  daily close additionally persists review queues and ChatGPT inputs.

## C. Timeline

| Shanghai time | Owner / action |
| --- | --- |
| 09:12 | Local Task Scheduler starts hidden Python; bounded Git refresh; real calendar gate |
| 09:15 | Live process sampling every 30 seconds; late start recorded |
| 09:20 | Continue process data with the same source and checkpoint contracts |
| 09:25:00 | Last standard checkpoint; no later event enters the frozen packet |
| 09:25:02+ | Formal match, raw freeze, immediate full/compact/report/scoring build |
| 09:30 | No collector is waiting for this time; separate post-open stage becomes eligible |
| 09:35 / 09:45 | Independent actual-time validation snapshot |
| 10:00 | Final independent validation snapshot; delayed/stale data is not relabelled |
| 15:15 | EOD Tushare open reconciliation stored separately |

09:25:05 is a target, not a measured production SLA. Live acceptance requires
observed start/match/report timestamps. More than one minute late at collection
start forces FAIL timeliness; late diagnostics are still allowed before 09:30.
Historical replays do not pass live timeliness. An incomplete watchlist degrades
coverage. No process point after 09:25 is accepted into Stage B.

## D. Scoring

- Market environment 10: prior operability 3, focused-watch-universe breadth 4,
  previous formal leader/capacity feedback 3. Focused scope is explicitly not the
  full market. Samples below 100 reduce available breadth points. No sector input.
- Mainline 15: exact prior quality 4, sector breadth 4, minimum leader/capacity
  strength 4, supported tomorrow-check outcome 3. Missing observations are N/A.
- Catalyst 15: source reliability 6, explicit event-type materiality 5, timestamp
  freshness 2, direct relevance 2. The four parts use one evidence item, never
  cherry-picked fields from unrelated events. Routine A evidence is not 15;
  unclassified materiality is N/A. D receives no hard-validation credit.
- Risk 0-20: stable rule IDs with matched evidence; earnings reductions/losses/downward
  revisions are negative, generic earnings/growth/return-to-profit are not.
- Unsupported prose is unverified/UNSUPPORTED_CONDITION. Structured stock/theme/market
  conditions use whitelisted metrics/operators. Unmatched absolute volume is never
  called buy-side strength without a source_contract_reference.

## E. Automation And Environment

Primary deployment: five `Ashare-Auction-*` Windows Task Scheduler entries were
registered locally on 2026-09-09 before the session. Trigger boundaries are 09:12:00,
09:35:00, 09:45:00, 10:00:00 and 15:15:00 Shanghai. They use project pythonw.exe,
ignore overlapping task launches, wake the machine where supported, and retry twice
at one-minute intervals. They require this machine to remain available and the
interactive Windows user to remain logged in. A powered-off or logged-out machine
is not promised automatic collection. No password or token is stored in task arguments.

The scheduled entry performs real exchange calendar gating. Holidays return
SKIPPED_NON_TRADING_DAY without packet generation. Lock directories prevent overlap;
an abandoned lock is an explicit recovery condition, not silently stolen. Network
sync is bounded and data-only; failure keeps local artifacts. Frozen packet bytes
are SHA checked on restart. An interrupted post-freeze build reuses archived raw
collection instead of recollecting different 09:25 facts. Force is explicit.

Local eltdx 3.1.3 connection probe: PASS. Current environment Python 3.12.14/Windows.
This is connection evidence, not a 100-stock live throughput or E2E acceptance.
The package has a Linux manylinux wheel and does not require a Windows quote client.
Ubuntu GitHub IP reachability must be measured by auction-source-probe.yml.
Cloud live/post-open cron is deliberately gated by AUCTION_EXECUTION_ENV=github;
do not enable it simultaneously with local production without choosing one owner.

GitHub cron itself may be delayed; it cannot promise a strict 09:25 SLA. Thus a
workflow definition alone is not claimed to solve timing or source feasibility.
References: [GitHub scheduling limits](https://docs.github.com/en/actions/how-tos/troubleshoot-workflows),
[eltdx 3.1.3 Linux distribution](https://pypi.org/project/eltdx/3.1.3/).

## F. Formal Review Closure

After close: existing review_context and objective support plus formal_review_queue
and chatgpt_review_inputs/YYYY-MM-DD_compact.json are generated. ChatGPT still writes
the final structured v3 review; Codex never invents its judgement. The existing
stdin/inbox import validates the canonical schema, dates, 41 factors, evidence and
ownership, writes an immutable official-shaped projection, and marks the queue READY.
Existing conflicting official files are never overwritten. The auction reads only
the exact previous trading date, preferring validated canonical v3 and deriving
the same projection in memory. Missing review means degraded, not blocked collection.

Real preflight on 2026-09-09: previous date 2026-09-08; Market Packet and context
present; formal review MISSING; source connected. The 9/8 queue is WAITING_FOR_CHATGPT_REVIEW.
Without actual ChatGPT delivery, full acceptance cannot be READY even if collection works.

## G. Verification

compileall: PASS. Full non-real-data suite: 313 passed, 1 deselected. Targeted
auction unit/integration/EOD tests: 39 passed. All JSON schemas validate; three new
workflow YAMLs parse successfully. This static check is not a remote execution proof.

Unit/integration fixtures cover immediate return at 09:25:02, 20-stock live assembly
without realtime-open calls, idempotent freeze reuse, independent incremental post-open
bytes, current-only date rejection, calendar skip, exact prior review, rules/conditions,
and no unavailable-direction inference. The legacy 2026-09-04 artifact is preserved; validation reports
PARTIALLY_READY / LIVE_ACCEPTANCE_PENDING, not READY.

## H. Readiness

PARTIALLY READY: implementation and local scheduling are in place; LIVE ACCEPTANCE
PENDING for the next upcoming real session, 2026-09-09. Remaining acceptance requires
the actual timed collection/freeze, exact 9/8 ChatGPT review, independent 09:35/10:00
observations, and EOD reconciliation. No synthetic production observations were written.
