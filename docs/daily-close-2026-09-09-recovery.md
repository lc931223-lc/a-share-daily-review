# Daily Close Recovery and Objective Theme Types

## Audited Failure

GitHub run `34325288683`, commit `b90d8151ad314fbd10fce1038cb7fe7ddef9baa9`,
failed at `Run close pipeline with retries` three times. The actual log shows
`TUSHARE_TOKEN` missing and the full-market daily gate failing. The job skipped
the success-only artifact commit. No original 9/9 manifest was present on main.
The retrospective audit receipt is stored separately at
`data/daily_runs/diagnostics/github-34325288683.json`; it is not a new run receipt.

At this audit, the workflow API still reports that run as the latest daily-close
run. Current main already wires `${{ secrets.TUSHARE_TOKEN }}`, runs credential
preflight before acquisition, publishes failure manifests separately and uploads
failure diagnostics. Those fixes were not in the failed run's old commit.
The latest failed log does not reveal whether the repository secret was configured
subsequently. Local credential presence is AVAILABLE; no secret value is stored.

## Secret Contract

For future GitHub runs, confirm the repository secret under Settings -> Secrets
and variables -> Actions -> New repository secret, name `TUSHARE_TOKEN`.
Only the repository owner supplies the value. Neither logs, fixtures, source code
nor this document contain it.

Actions -> A-share daily close production -> Run workflow:
`trade_date = 2026-09-09`.

Local recovery command:

```console
python tools/run_daily_close_pipeline.py --date 2026-09-09
```

## Production Contracts

No full-market row threshold or quality scoring was changed. Missing credentials
fail with MISSING_TUSHARE_TOKEN. Both success and failure manifests now expose
`failed_step`, `blocker`, `credential_health`, `retry_count`, `source_health`,
`upstream_available`, `upstream_missing`, `started_at` and `completed_at`, retaining
the existing fields for compatibility. Native same-date stages precede input/queue
publication; feedback follows publication. Failed upstream stages do not generate
the new input, even if stale support artifacts exist. The standalone input builder
also enforces the existing full-market daily PASS check.

Formal review source hashes normalize only CRLF to LF, matching the canonical
import bytes and GitHub main. No formal review content or judgments are changed.
Exact previous-day selection is unchanged; 9/9 reads only 9/8. Prose conditions
without machine predicates remain NOT_EVALUABLE, not invented confirmations.

## Theme Taxonomy

`theme_type` uses explicit source metadata, industry names already in the Market
Packet and deterministic name rules. Fund/insurance holdings are OWNERSHIP_TAG,
margin eligibility FINANCING_TAG, earnings guidance PERFORMANCE_TAG and A/H labels
STYLE_TAG. Industry, concept, event and index categories use their source taxonomy;
unknowns remain OTHER. This is not eligibility, exclusion or mainline priority.

Compact still selects by amount then identity, without type filtering or weighting.
`selection_metadata` exposes available, retained and truncated counts for every
type. The observed-sample style max/min method and its coverage metadata are intact.

## Optional Auction

All consumers share a read-only same-date, frozen, schema, SHA and timing check.
An invalid optional auction is UNAVAILABLE, not a daily-close failure. No auction
collection or scoring algorithm was changed. The frozen real 9/9 files pass date,
schema and provenance checks but fail timing and quality; they are not used.

## Real Recovery

The local run obtained 5,550 same-date Tushare daily rows. Market Packet core checks
passed; quality remained PARTIAL, score 83, with policy, northbound and margin gaps
preserved. The complete dated artifact chain was generated, without substitution
of a previous day or a sample universe. Queue status is WAITING_FOR_CHATGPT_REVIEW.
No 9/9 ChatGPT formal review or final research conclusion is produced by Codex.
