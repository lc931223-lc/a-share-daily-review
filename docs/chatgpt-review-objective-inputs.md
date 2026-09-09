# ChatGPT Review Input Pack

## Ownership

The production delivery hook now publishes an allowlisted objective projection,
not the old support dump. Mainline ranks, final ratings, lifecycle labels, final
stock roles, six-dimension scores, causal explanations, expectation-gap judgments
and investment conclusions are excluded. `additionalProperties: false` applies
to every fixed object in the full and compact schemas.

Production Formal Review Support no longer invokes legacy lifecycle, final-role
or score-support helpers. Historical support archives and immutable imported
ChatGPT formal reviews are not rewritten. The existing feedback subsystem is not
re-scored: its historical outcome categories are excluded from this input pack.

## Entry Points

Replay from existing local artifacts, without fetching or producing a review:

```console
python tools/build_chatgpt_review_inputs.py --date 2026-09-08
```

Normal daily-close and formal-import queue publication use the same builder.
Successful queue publication includes `chatgpt_review_input_path` and
`chatgpt_review_input_compact_path` as the preferred handoff paths. Input validation
failure still produces a FAILED daily-run manifest, not a green pipeline.
The workflow already commits the entire `data/chatgpt_review_inputs` directory.
Outputs:

- `data/chatgpt_review_inputs/YYYY-MM-DD.json`
- `data/chatgpt_review_inputs/YYYY-MM-DD_compact.json`
- `schemas/chatgpt_review_inputs.schema.json` (`chatgpt_review_inputs.1`)
- `schemas/chatgpt_review_inputs_compact.schema.json` (`chatgpt_review_inputs_compact.1`)

The imported ChatGPT record contract remains `formal_review.3`.

## Measurement Contract

- `as_of` is the end of the stated Shanghai calendar day, not the 15:05 close.
  Same-day evening disclosures may be included. This is an EOD archive replay,
  not evidence that every input was available at 15:05.
- Sources are pinned by relative path, source date and exact local file SHA-256.
  JSON sources also include `canonical_sha256`: UTF-8, sorted keys, no extra
  separators/whitespace, unescaped Unicode. This fingerprint is stable across
  platforms; legacy non-finite JSON constants are normalized to null with a gap.
  The original byte hash still identifies the unsanitized source. It also bridges
  Windows CRLF and Git LF. Do not compare the local byte SHA directly with a
  newline-normalized Git blob. Local historical files and FactStore partitions
  may not be committed; a clone without those archives reports missing metrics.
  Missing/wrong-date inputs and future-dependent derived inputs are excluded.
  Publication timestamps are compared in Asia/Shanghai, including UTC boundaries.
  Current-only observations without an exact matching date are rejected.
- `amount` is CNY where upstream supplies normalized CNY. Archived THS sector
  amounts without unit metadata remain null. `amount_change_vs_previous` is the
  absolute CNY difference against the exact preceding exchange session, not a
  cached upstream percent. Return, breadth, failed-limit rate and turnover use
  percent units. Six-session archive persistence is the fraction of positive
  return days (0..1); missing sessions invalidate the corresponding window.
- `first_seen_date` is first observed in the six-session archive window, **not**
  thematic inception. Strength change is the difference in daily return, in
  percentage points. Unobserved leader/capacity persistence remains null.
- Styles retain sample count, coverage and methodology. Largest/smallest sample
  return selects strongest/weakest style; this is not an investability judgment
  or a claim of full-market coverage. Role scores reuse existing RI scores,
  capacity and market cap reuse Capital Preference inputs. No new scoring model.
- Median stock return is emitted only when the local same-date FactStore row
  count matches market breadth counts and every return is available. FactStore
  is reused read-only. These partitions do not establish a release-vintage audit;
  replay establishes dated observations, not historical revision-free snapshots.
- All 41 factors are retained. Category-based links are PARTIAL_EVIDENCE, not
  confirmation of a causal driver. Unmapped factors are DATA_UNAVAILABLE, not
  NO_EVIDENCE. Tier and source confidence describe provenance only.
- A disclosure title is not an extracted order, shipment, revenue or profit
  fact. An official positive disclosed contract amount without clarification or
  uncertainty can yield ORDER_CONFIRMED. Tier4 cannot confirm realizations.
  Tiers require source metadata and recognized official domains, not an inherited
  A/B/C/D research rating. Unrecognized official/association domains conservatively
  remain Tier4 until their provenance is independently established.
- Evidence counts count distinct observed nodes, not full-market search coverage.
  Stock announcement support is a node count; zero is not proof of no announcement.
- Divergences compare observable pairs only. Different units are not subtracted;
  severity remains null because no new severity model is introduced.
- `very_high_turnover` uses a transparent >=30% observation threshold, not a price
  forecast. Other price/fundamental anomalies require comparable baselines and
  remain absent with gaps when those baselines do not exist. Cross-market rows
  require timestamped measurements from the existing packet, not live fetching.

## Previous Formal Review

The only allowed prior review is the exact previous exchange trading day. Missing
that day yields `PREVIOUS_FORMAL_REVIEW_UNAVAILABLE`, even if older reviews exist.
Each of the four condition types receives its own metric result. A legacy generic
predicate belongs only to `validation_point`; it is not reused for the opposite
weakening or falsification condition. Explicit `predicates[condition_type]` are
supported when present. Free text is NOT_EVALUABLE rather than guessed.

Outputs include actual value, threshold, condition_met and evidence, but no
CONFIRMED/PARTIAL/FAILED research outcome, hit rate or objective-support hypothesis.
Existing feedback records remain separate and unchanged.

## Compact Selection

Select up to 10 themes by observed amount, then stable identity; 20 linked stocks
by amount; 30 evidence nodes, risk disclosures first then source tier. This is
mechanical selection, not formal ranking. All 41 factor slots remain and evidence
references resolve within the compact pack. Selection counts and a truncation gap
make omissions explicit. Full pack remains the authoritative evidence inventory.

## 2026-09-08 Replay Limits

The archived Market Packet remains FAIL; creating this input does not upgrade it.
The exact previous formal review for 2026-09-07 is absent. Official policy records,
verified limit-down counts, several continuity metrics and comparable cross-market
baselines remain unavailable. The archived announcements are mostly risk/general
disclosures: do not infer confirmed orders or growth from them. No formal Markdown
market review is produced and no 2026-09-09 market data is synthesized.
