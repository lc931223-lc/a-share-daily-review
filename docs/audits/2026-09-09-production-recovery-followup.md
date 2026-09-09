# September 9 production recovery follow-up

## Original failure and current remote state

The original Actions run 34325288683 ran at commit
b90d8151ad314fbd10fce1038cb7fe7ddef9baa9 with an empty TUSHARE_TOKEN.
Its success-only commit step skipped the failure manifest. Diagnostics were
uploaded, but no original failure manifest was committed by that workflow.

At the start of this follow-up, origin/main was
f07f1a3fece97d0337bb2700ab2158b007a91a66. Contrary to the reported missing-file
state, every required September 9 full/compact artifact and the daily manifest
was already present in that remote commit. These were local production recovery
outputs, not a successful rerun of the original GitHub Actions job.

## Additional reliability fixes

- Workflow prints credential presence only, without failing before the CLI can
  persist its diagnostic manifest. Schedule and dispatch share the same job-level
  repository secret binding.
- Native production checks the real calendar and probes same-date Tushare daily
  before starting the Market Packet collector. API errors become status-only
  auth, permission, network, rate-limit, empty-response or date-mismatch blockers.
  Credential presence remains strictly AVAILABLE/MISSING.
- Collector instances with an explicitly isolated raw directory now also isolate
  default reference and fact storage. Previously unit-test producers could write
  one-row reference fixtures into the production reference directory.
- The collector reuses the shared exchange calendar and accepts a previous-day
  daily cache only for the exact calendar predecessor. No earlier-date fallback.
- The contaminated one-row stock_basic reference was quarantined locally, not
  copied into a replacement full-market list. The provider's hourly limit must
  not be bypassed by treating that fixture as a complete reference dataset.

## Live source audit

An independent live daily call returned 5,550 rows for 20260909, with zero
duplicate codes and zero null pct_chg values. The earlier persisted raw daily
receipt was fetched at 2026-09-09T14:32:48.457748+00:00.

A live stock_basic call returned 5,560 listed records. Subsequent refresh attempts
were rate limited (one call/hour). The numeric difference is 10, but the probe did
not retain the complete stock_basic response, so the exact missing-code set and
suspension attribution are NOT VERIFIED. Do not claim that this count difference
proves ten suspended stocks. The existing production gate was not changed; it
checks availability of full-market daily rows rather than reconciling every
listed security's suspension status.

A live trade_cal probe was also rate limited. The existing complete 2026 calendar
from tushare.trade_cal is available locally; its receipt was fetched on September
5. Calendar access does not require repeatedly fetching that low-frequency API.

## Actions recovery

The public workflow listing still showed only the original failed run during this
audit. Local credential availability does not prove Repository Secret availability.
No successful GitHub workflow rerun is asserted here.

The repository administrator should verify Settings -> Secrets and variables ->
Actions -> TUSHARE_TOKEN. Never commit its value. Then dispatch "A-share daily
close production" on main with trade_date=2026-09-09. The equivalent local command
is `python tools/run_daily_close_pipeline.py --date 2026-09-09 --force`.

On failure, the independent publisher commits only the matching current-run
manifest; the original step remains failed and diagnostics upload still runs.
On success/partial success, the generated objective artifacts are committed by
the normal publication step. Optional-source gaps are not concealed as PASS.

## Local recovery verification

The official CLI was run with `--date 2026-09-09 --force` and exited zero with
PARTIAL and no blockers. After quarantining the contaminated optional reference,
Market Packet and its affected downstream producers were refreshed, followed by
another official CLI validation/delivery run. The latter also exited zero with
PARTIAL and no blockers. The stock_basic source now explicitly reports failure
instead of presenting the one-row fixture as available.

Market Packet quality is 83/PARTIAL; Inflection, Review Intelligence, Capital
Preference and Review Context remain PARTIAL. The formal queue is
WAITING_FOR_CHATGPT_REVIEW. Ten full/compact schema/date checks and six native
core-artifact validations passed. The input metadata remains
OBJECTIVE_RESEARCH_INPUT, final_judgement_owner=chatgpt.

Verification: compileall passed; targeted tests 80 passed; full non-real-data
suite 398 passed, 1 deselected. No existing production threshold or research
scoring algorithm was changed.
