# Daily Production Root-Cause Audit

Audit date: 2026-09-08
Baseline: `1d4ef115bc99fa052f42dafc1baa148085d8f911`

## Root-Cause Table

| Step | Arbitrary-date capability | Existing production integration | Root cause for 2026-09-07/08 gap |
|---|---|---|---|
| Trading calendar | Real Tushare/AKShare calendar and 15:05 auto-date exist | Each CLI resolves independently | No common close gate or missing-day discovery |
| Market Packet | Explicit date and auto are supported | The old daily command stops after this layer | No scheduler invoked it on 09-07/08 |
| Review Intelligence | Explicit date is supported when same-date daily facts exist | Standalone development CLI only | Same-date facts/Market Packet were never advanced |
| Inflection | Explicit date and history backfill are supported | Standalone development CLI only | Never called by the old daily command |
| Capital Preference | Explicit date is supported; same-date Review Intelligence is required | Standalone development CLI only | Same-date Review Intelligence is absent |
| Auction | Separate historical/live/post-open/eod commands exist | Not connected to daily close | No scheduled live run; should be optional at close |
| Review Context | Builder enforces same-date required inputs | Standalone development CLI only | Same-date Market/RI/Inflection/Auction are absent; Auction was unnecessarily hard-required |
| Formal review | Existing JSON can be validated/imported | Human-created file must already exist | No system component may invent ChatGPT's formal conclusion |
| Feedback | Range batch can create prediction/validation/review/correction | Requires intersection of five same-date artifact sets | WAITING records are not rescanned automatically when new daily facts arrive |
| Scheduler | None | None | No `.github/workflows`, cron, or deploy scheduler exists |

## Direct Answers

1. Market Packet, Review Intelligence, Inflection, Capital Preference, Auction, Review Context and Feedback expose date-based APIs or CLIs, but their prerequisites differ.
2. Every analytical CLI except Market Packet auto mode requires a manually supplied date.
3. Review Intelligence, Inflection, Capital Preference, Review Context, Auction reconciliation and Feedback only run from standalone scripts/tests.
4. The old `tools/run_daily_pipeline.py` does not invoke those modules, and no process invoked the old command on 09-07/08.
5. There is no unified close orchestrator. The old command is only a Market Packet plus optional official-review importer.
6. There is no scheduler, GitHub Action, cron entry, or deploy scheduler in the repository.
7. The absence is explicit; `deploy/` contains only static HTML.
8. Review Context rejects generation because same-date Market Packet, Review Intelligence, Inflection and Auction artifacts do not exist.
9. `WAITING_FOR_MARKET_DATA` records only advance when the whole Feedback range job is manually rerun; no automatic scanner exists.
10. The durable fix is one close orchestrator, a per-date manifest, strict artifact validation/reuse, missing-day backfill, and automatic Feedback rescanning.

## Contract Gaps

- The current official-review schema stores only selected driver references, not an exact 41-factor evaluation for each theme.
- Theme scores are totals without a fixed machine-readable rubric of raw score, available score, subcomponents, evidence and reason.
- Lifecycle values are labels, not a persisted transition state machine.
- Role classification exists as objective candidates but the formal-review contract does not expose all required role evidence.
- Review Context currently allows an older official review as historical context. That is valid as history but must never be represented as the immediately previous trading-day formal review unless dates match exactly.
