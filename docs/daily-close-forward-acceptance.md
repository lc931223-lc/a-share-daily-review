# Daily production forward recovery audit

Audited September 14, 2026 against current main. Execution was local Codex and
real provider requests, not a Codex Cloud session. No new research algorithm,
formal judgement or auction scoring change was introduced.

## Root causes and existing coverage

The old claim that Review Context stopped at September 4 is no longer current:
main already contained September 4 and September 7-11 contexts. The orchestrator,
Actions schedule, manifests, formal-review import, 41-factor schema, role fields,
lifecycle fields and forward feedback already existed. Their existence did not
guarantee every artifact was accepted or every missed date was repairable.

The audit found four production defects: the default CLI selected a prior closed
day even on a holiday/pre-close run; backfill searched only after the latest
context filename; Market Packet acceptance checked daily rows but ignored other
declared hard gates; backward feedback evaluation could reuse later validation.
Missing compact artifacts also were not validated/rebuilt, and the feedback
success envelope overwrote its WAITING step status.

All core data producers accept an explicit trading date. The unified CLI supplies
dates automatically; individual CLIs remain available for operator diagnostics.
Auction live sampling/reconciliation remains a separate scheduled subsystem and
is only consumed when its accepted, same-date artifact exists. ChatGPT formal
conclusions require an import; they are not missing automatic Codex calculations.

## Changes by file

- `config/daily_close.json`: explicit first production date, not a fixed target.
- `tools/run_daily_close_pipeline.py`: default today; explicit latest/recovery.
- `src/daily_close/orchestrator.py`: whole-chain hole detection, compact schema/date
  checks, all declared hard gates, failed-quality rejection, WAITING preservation.
- `src/feedback/integrated.py`: optional non-persisting evaluation for replay.
- `src/feedback/forward.py`: as-of snapshots, immutable prior validation archive,
  no later-result fallback or backward mutation of canonical validation records.
- `tests/unit/test_daily_close_recovery_boundaries.py`: default/closed-day routing,
  earlier holes, hard gates, compact rejection and WAITING regression tests.
- `tests/unit/test_daily_close_orchestrator.py`: complete compact fixtures and
  production-start recovery expectations.
- `tests/integration/test_feedback_forward.py`: waiting/forward/backward/repeated
  checks and proof that later canonical results do not enter earlier snapshots.
- `tests/integration/test_first_formal_review_handoff.py`: complete external-producer
  compact fixtures; real formal/schema/context/handoff guards remain enabled.
- `CHECKPOINT.md`: current production status instead of treating old samples as
  evidence that scheduling is absent.

No replacement orchestrator, new quote database or duplicate scoring model was
created. Existing Actions scheduling/retries/failure-only publication remain used.

## Dependency and execution

Calendar + close-time guard -> credential/API availability -> Market Packet ->
Inflection -> Review Intelligence -> Capital Preference -> Review Context ->
Formal Review Support -> ChatGPT objective input full/compact -> review queue ->
Feedback prediction/validation/review/correction -> daily manifest.

Accepted auction data and exact previous ChatGPT formal records are optional
inputs with explicit availability; absent formal records are never synthesized.

```
python tools/run_daily_close_pipeline.py
python tools/run_daily_close_pipeline.py --latest --backfill-missing
python tools/run_daily_close_pipeline.py --date 2026-09-07
python tools/run_daily_close_pipeline.py --date 2026-09-08
```

The configured production start is September 4. The end date advances with the
real exchange calendar. Recovery checks every date in that interval, not just
dates beyond the latest filename. A failed intermediate day is explicitly blocked,
not silently skipped. No-argument execution on September 14 before close actually
returned MARKET_NOT_CLOSED and did not create a formal close packet.

## Real acceptance and limitations

September 7: all six major upstream artifacts validated as PARTIAL; the real
pipeline completed without blockers and produced objective ChatGPT inputs/queue.
The full/compact context files exist with the exact September 7 source date.

September 8: Tushare daily contains 5,549 rows. A fresh Eastmoney limit-down pool
request remained empty; Tushare stk_limit did not grant permission. An empty pool
cannot prove zero limit-down stocks without authoritative daily bands/exemptions.
The limit-ecology hard gate therefore fails. The real pipeline returned FAILED
at Market Packet and did not proceed to new accepted downstream artifacts.

The latest failed packet is kept in
`data/daily_runs/diagnostics/2026-09-08-recheck/`, not published as a replacement
successful packet. The new failure manifest remains at
`data/daily_runs/2026-09-08.json`. Existing September 8 downstream files are historical
files, not evidence that this rerun passed. Same-date does not imply valid quality.

Actual recovery also repaired September 4's missing/stale delivery pieces before
stopping at September 8. Thus recovery mechanics are verified, but uninterrupted
production acceptance remains BLOCKED by September 8 limit-down verification.

The exact September 7 formal review is absent. September 8 correctly reports
PREVIOUS_FORMAL_REVIEW_UNAVAILABLE with no formal hypotheses or hit rate. There
is no independently verifiable consecutive formal lifecycle transition to show.
Existing formal-record claims are not relabelled as verified transitions.

The complete machine-readable 41-factor example is the September 7 objective
candidate in `reports/daily_close_acceptance/2026-09-14.json`. It is not a Codex
final mainline judgement. Formal scoring explanations and state/role schemas were
reused, not replaced with an automatic final assessment.

Feedback at the September 7 as-of: still waiting 1, newly validated 0, evaluable 1.
These are the existing objective research cohorts, not formal-review hit rates.
September 8 feedback was not advanced because its market gate failed. As-of
snapshots are in `research_feedback/as_of/`; canonical later results remain intact.

## Acceptance scope

Final verification: targeted suite 46 passed; full non-real-data suite 576 passed,
1 real-data test deselected by the requested marker; compileall passed. Real
sequential execution and recovery are reported separately from fixture success.

The task is PARTIALLY COMPLETE, not a claim that September 8 production recovered.
Remaining data blocker: a verifiable September 8 limit-down pool, or authorized
same-date exact price bands/exemption evidence. No secret values were inspected
or embedded in code, reports or workflow. Provider access uses the existing
environment configuration; no secret configuration was changed.
