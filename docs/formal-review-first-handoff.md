# First Formal Review Handoff

Initial verified baseline: 6a2c17b10784a8338e288a8715d983d450a1aed3 (remote main).
At preparation time the 2026-09-08 queue was WAITING_FOR_CHATGPT_REVIEW.
Before delivery, remote main advanced to d0e8153, including the real ChatGPT
import in 8646ad0. After integration the queue is FORMAL_REVIEW_READY with
validation_status PASS. This preparation task did not import its blank template.

## Recommended Production Path

ChatGPT/integration delivers its completed UTF-8 JSON to
`data/formal_review_inbox/2026-09-08.json`, then immediately runs:

```powershell
.venv\Scripts\python.exe tools/import_formal_review_record.py --inbox
```

Do not wait for the next daily close: the 9/9 morning consumer needs the previous
review already imported. The inbox itself is not a live watcher; daily-close scans
it when the close pipeline runs. A rejected inbox item gives exit code 2.

The same validator is available through stdin (`-`) or a single-file CLI:

```powershell
Get-Content -Raw -Encoding UTF8 data/formal_review_inbox/2026-09-08.json | .venv\Scripts\python.exe tools/import_formal_review_record.py -
.venv\Scripts\python.exe tools/import_formal_review_record.py data/formal_review_inbox/2026-09-08.json
```

For an API caller, pass UTF-8 JSON bytes to subprocess stdin directly, avoiding
shell encoding conversions. Do not embed a JSON payload or credentials in arguments.

## Template Contract

`docs/templates/formal_review.3-2026-09-08.json` is complete JSON, validates under
the current schema and import validator, and contains no market judgement.
It deliberately has an empty main_themes array and NOT_ASSESSED market regime.
Current schema allows empty arrays but requires a non-null lifecycle enum for
every supplied theme. Thus a populated theme template cannot be both judgement-free
and a finished formal theme. No schema or scoring changes were made to hide this.

Once ChatGPT supplies a theme, that theme must contain all required score aliases,
six score components, lifecycle, stock roles, next-day validation, uncertainties,
and exactly 41 ordered factor entries with the catalog's exact factor names.
The end-to-end fixture exercises a fully populated theme with all 41 factors.
The blank template must not be submitted as a completed review: the existing
importer would accept it and mark the queue ready. It has not been imported here.

Close validation predicates are stored under each theme's next_day_validation:
`predicate = {"field": "amount", "operator": "gte", "threshold": <ChatGPT supplied number>}`.
Supported close fields are change_pct, amount, rise_count, fall_count,
limit_up_count and limit_down_count; operators are gte/lte. Free text without a
predicate is NOT_EVALUABLE. Top-level tomorrow_checks belongs to the existing
auction/post-open interface, not the close hit-rate denominator.

## File Effects And Timing

Immediately on successful import:

- `data/formal_reviews/2026-09-08.json`: canonical immutable formal_review.3.
- `data/official_reviews/2026-09-08.json`: derived immutable compatibility projection.
- `data/formal_review_queue/2026-09-08.json`: FORMAL_REVIEW_READY, validation_status PASS.
- `data/chatgpt_review_inputs/2026-09-08_compact.json`: refreshed from existing objective inputs.
- CLI output includes SHA-256 of canonical bytes; projection.source_sha256 is identical.

On the subsequent 2026-09-09 close run with same-date facts:

- `data/review_context/2026-09-09.json` and `_compact.json`: exact prior formal provenance.
- `data/formal_review_support/2026-09-09.json`: evaluated formal previous_day_validation,
  with objective support hypotheses separately labelled and excluded.
- `research_feedback/formal/2026-09-09.json`: persistent formal-only validation and rates.
- `data/feedback_records/2026-09-09/`: normal objective-context feedback; not converted
  into formal results simply because the preceding day had a formal review.
- `data/daily_runs/2026-09-09.json`: per-step status, SHA receipts and inbox import outcomes.

Import alone cannot generate next-day actual results. Formal feedback is written
only when the existing feedback stage runs; no synthetic forward data is generated.
The validated bytes, projection digest, prior-review manifest digest and formal
feedback source digest must agree. Repeated identical imports return UNCHANGED;
conflicting same-date content is rejected without overwriting the formal record.

## Exact Date And Test Boundary

2026-09-09 reads only the 2026-09-08 canonical formal file. A missing 9/8 record
returns PREVIOUS_FORMAL_REVIEW_UNAVAILABLE with expected_date=2026-09-08, even if
9/7 formal, 9/8 support or an embedded previous_review is present.

Integration tests use temporary directories, injected clock/calendar and mock
upstream data producers, but real CLI import, canonical/projection persistence,
Review Context, support evaluator, Feedback and Daily Close orchestration. They
assert one confirmed and one failed formal predicate gives 50% hit rate; an
unstructured formal condition is excluded from the denominator, and objective
support hypotheses never enter the formal records. No 9/9 production facts are written.

Verification on 2026-09-09: handoff integration tests 6 passed; complete offline
suite 319 passed, 1 real_data test deselected; compileall passed for src, scripts,
tools and tests. No runtime modules, schemas or scoring algorithms were changed.
