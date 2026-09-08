# Daily Close Production

## Entry Point

```bash
python tools/run_daily_close_pipeline.py --latest --backfill-missing
```

Historical recovery uses `--date YYYY-MM-DD`. `--force` regenerates valid artifacts and should be reserved for corrected source data or schema migrations.

The dependency order is:

```text
trade calendar / close gate
  -> Market Packet
  -> Inflection
  -> Review Intelligence
  -> Capital Preference
  -> Review Context
  -> formal-review objective support
  -> Feedback forward advancement
```

Auction is a same-date optional enhancement. Its absence is recorded as `UNAVAILABLE`; an older Auction Packet is never accepted.

Daily Close Production is implemented in the scheduled workflow. Auction Production Integration is not yet closed end to end: missing auction artifacts carry `optional_missing=true`. A deployed scheduled run still depends on repository Secrets and GitHub Actions being enabled.

## Formal Review Inbox

The daily entry automatically checks `data/formal_review_inbox/*.json` before assembling context. ChatGPT-generated structured records can be delivered to this inbox by the assistant/integration, or streamed directly to `python tools/import_formal_review_record.py -`. A single `python tools/import_formal_review_record.py --inbox` processes pending files immediately.

Only `data/formal_reviews/YYYY-MM-DD.json` is canonical for v3 formal reviews. Objective support and legacy fixtures are not substitutes. Imports require the real trading date, `previous_trade_date`, `final_judgement_owner=chatgpt`, the full schema and 41 factors, admissible evidence tiers, no future evidence, immutable content and SHA-256 provenance. Same-content retries are accepted; conflicting content is rejected. Inbox results are recorded in the daily manifest, and a newly imported prior review invalidates the cached next-day context.

Formal conditions may include `predicate` with `field`, `operator` (`gte`/`lte`) and numeric `threshold`. Supported theme fields are change_pct, amount, rise_count, fall_count, limit_up_count and limit_down_count. Free-text-only conditions remain NOT_EVALUABLE rather than being guessed from price direction. Formal validation is persisted separately under `research_feedback/formal/`; objective support hypotheses are explicitly excluded from formal hit rates.

## Scheduler

`.github/workflows/daily-close.yml` runs at 15:30 Asia/Shanghai on weekdays. The orchestrator performs the real exchange-calendar check, so exchange holidays return `NON_TRADING_DAY` without producing close artifacts. Manual dispatch accepts an optional historical date and force flag.

Configure the repository secret `TUSHARE_TOKEN` in GitHub repository settings. The workflow references the secret as an environment variable and never stores its value in source or generated output. Public fallback sources may still run without it, but the full-market daily hard gate can block production if no admissible source succeeds.

## Status And Recovery

Each attempted date writes `data/daily_runs/YYYY-MM-DD.json`. Every core step records status, artifact path, source date, quality, timestamps, retry count, error, reuse flag, and SHA-256 digest. Final status is one of `PASS`, `PARTIAL`, `BLOCKED`, `FAILED`, `NON_TRADING_DAY`, or `MARKET_NOT_CLOSED`.

`--backfill-missing` discovers completed trading days after the latest persisted Review Context and runs them in order. A blocked or failed day stops the sequence, preventing a later date from bypassing a missing intermediate day. Re-running a completed date validates and reuses unchanged artifacts, then advances Feedback again idempotently.

## Formal Review Boundary

`data/formal_review_support/YYYY-MM-DD.json` is objective support, not a formal conclusion. ChatGPT's machine-readable review must validate against `schemas/formal_review_record.schema.json` and be imported with:

```bash
python tools/import_formal_review_record.py path/to/formal-review.json
```

The next Review Context accepts only the exact previous A-share trading day's non-simulated formal record. If it is absent, the manifest records the expected date as unavailable; no older review or embedded fallback is used.
