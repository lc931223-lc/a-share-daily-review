# September 11 daily-close recovery

Verified on September 13, 2026 (Asia/Shanghai).

- Tushare daily returned 5,550 rows for 20260911, zero duplicate codes and zero
  null pct_chg values. Credential presence was AVAILABLE; no credential value
  was written to this report.
- `python tools/run_daily_close_pipeline.py --date 2026-09-11 --force` completed
  with exit code 0, PARTIAL status and no blockers. Full-market daily gate PASS;
  Market Packet overall quality remains PARTIAL / 66. Missing optional evidence
  was not filled or assigned a higher quality score.
- Market Packet, Inflection, Review Intelligence, Capital Preference, Review
  Context, Formal Review Support, ChatGPT full/compact inputs and queue were
  generated for September 11. Same-date artifact checks and input schemas pass.
- Queue: WAITING_FOR_CHATGPT_REVIEW. No formal review or official projection
  was generated. Readiness: READY_FOR_GPT_REVIEW, not complete auction readiness.

## Empty-response behavior

An empty daily response is DATA_NOT_READY, not a credential failure. The CLI
retries after 60, 180 and 600 seconds (four calls maximum), retaining a diagnostic
manifest before each wait. Exhaustion exits 4 and is included in failure-manifest
publication. Only missing token takes the credential-preflight failure path and
exit 3. Authentication, permission and transport errors remain explicit API
failures; they are not converted into successful data.

The workflow retains its 15:30 run and adds 15:45, 16:15, 17:00 and 20:00 Shanghai
retry opportunities. Scheduling is configured, not a guarantee of exact runner
start time. No quality gate or auction scoring logic changed.

## September 14 Windows readiness

All six Ashare-Auction tasks are enabled and Ready: Live 09:12, Watchdog 09:13,
post-open 09:35 / 09:45 / 10:00 and EOD 15:15. Their next run date is September 14.
All use the same repository's tools/run_auction_task.ps1 with the appropriate
stage, the correct repository working directory and .venv/Scripts/python.exe
(Python 3.12.14). Scheduler logon mode is Interactive; the host must be powered
on and the user logged in. WakeToRun is enabled.

The calendar resolves September 14's exact previous trading day to September 11.
Market Packet and Review Context load successfully; official review is the only
missing previous-context item. No fallback to an older formal review is used.
eltdx connection succeeded; this is connection-only, not live auction acceptance.

Verification: targeted daily-close tests 25 passed; final full non-real-data suite
568 passed, 1 real-data test deselected; compileall passed.
