# Radar Evidence Enrichment Checkpoint

2026-09-14 Asia/Shanghai. Baseline main: 1045cc1036a4ecfd1be55872663e75baaa1f7435.

- Read existing contracts, FactStore, pipeline, body extraction, coverage, taxonomy,
  README, CODEX_MEMORY, CHECKPOINT, production CLI and scheduled workflow.
- Baseline contains only two LIVE trading dates, September 10 and 11, not three.
  September 11 has Morning and EOD; September 10 has Morning only.
- FactStore has 6,459 observation versions before eligibility/dedup filtering.
  Technology, expectation revision, competition and divergence have zero rows.
- Preserve all frozen packets, receipts, raw bodies, Parquet versions and tests.
- Implement additive official-body extraction, same-period expectation comparisons,
  evidenced economic relations, existing-FactStore price features and objective scores.
- User explicitly authorizes objective_opportunity_score, not final investment ranking.
- A newly retrieved historical document is historical backfill with actual first_seen.
  It cannot be inserted into an earlier LIVE snapshot or counted as an overnight event.
- September 14 EOD is not yet legal. Verify September 11 frozen EOD; exercise new
  EOD behavior with fixtures/replay without fabricating a September 14 close.
- Validation and real production run pending. No implementation acceptance yet.
- Leave unrelated untracked September 11 watchlist/September 12 auction receipt alone.

## September 15 Resumed Implementation

- Fast-forwarded to actual remote main cfbd385 without changing the in-progress edits.
- Added company body parsers, official discovery, same-period issuer expectation
  comparisons, terminal verified economic edges, current FactStore price features,
  decomposed scores, bounded compact output and coverage audit CLI.
- Real September 14 daily: 5,550 rows. Existing FactStore reused.
- September 15 Morning LIVE production succeeded PARTIAL; final missingness
  recheck/rebuild underway. September 14 EOD is preserved; enhanced replay separate.
- Earlier acceptance candidates and their receipts preserved in quarantine.
- Focused tests: 208 passed. Full suite: 623 passed, 1 skipped. Final re-run pending.
- Still PARTIAL: only 2 real expectation comparisons, incomplete technology subtypes,
  unknown exposure percentages, no forward PE/valuation vintages or full industry
  20-day PIT history. No real second/third-order economic chain fabricated.
- Final verification: compileall PASS; focused 208 passed; full 623 passed,
  1 real-data test skipped because its September 1 source gate did not pass.
- Accepted Morning full/compact schema, raw/provenance hashes, first_seen,
  previous-close source date, missingness and relation traversal checks PASS.
- Final snapshot: 10 technology, 2 distinct expectation, 8 competition and 35
  price/fundamental feature rows; 92 relation statements across 14 companies.
- Current corpus category presence 16/16, but every category remains PARTIAL.
- Commit includes the 60 existing FactStore price partitions actually referenced
  by the evidence receipt (June 23 through September 14), not a second database.
- Remaining at this checkpoint: scoped commit and push main.
