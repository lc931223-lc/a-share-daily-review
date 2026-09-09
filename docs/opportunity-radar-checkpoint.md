# Opportunity Radar V2 checkpoint

Scope: objective evidence only, 16 categories, immutable point-in-time observations
in the existing FactStore; no Auction scoring or final-review changes.

Implemented: contracts, series changes, conservative archived disclosure reuse,
bounded numeric-source adapters, taxonomy vocabulary, evidenced depth-1/2/3 graph,
snapshot pipeline, strict as-of filtering, compact limits, fixed feedback rule,
CLI and historical replay summary.

Verified: 8 numerical series returned real responses; Morning 2026-09-10 frozen
with 5 positive/3 negative/0 company-specific changes. September 9 EOD is explicitly
AS_OF_REPLAY, not a live run. Replay covers 72 sessions, only 4 with admissible
archived observations. Four full/compact schemas and source provenance passed.
Tests: targeted 116 passed; full non-real-data 508 passed, 1 deselected;
compileall passed. Optional Daily Review context does not change existing scores.

Remaining data limitations (not fabricated as completed coverage): 6/16 families
have actual observations; most company disclosures are title-only. No verified
production company/transmission edges. No established pre-September-9 lead dates
or mature feedback rates. Ten counterexamples are synthetic tests.

Historical first-seen cannot be inferred from a historical price date. Source
publication timestamps unavailable on numeric providers must stay null. Taxonomy
vocabulary is not proof of any company relationship. Title-only disclosures do not
confirm orders or commercialization. Current lack of historical vintages may make
historical lead-time and false-positive metrics unavailable.
