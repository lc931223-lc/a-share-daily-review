# Formal Review Delivery Inbox

Deliver ChatGPT structured review JSON here. The daily close entry imports all
JSON files before building context. For immediate processing, run
`python tools/import_formal_review_record.py --inbox`.

The canonical destination is `data/formal_reviews/YYYY-MM-DD.json`. Imports
validate the v3 schema, trading dates, evidence tiers and hypothesis ownership.
Identical retries are idempotent; changed records for an existing date are rejected.
Objective support is not a formal review and must never be imported as one.
