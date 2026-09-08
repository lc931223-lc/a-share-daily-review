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
