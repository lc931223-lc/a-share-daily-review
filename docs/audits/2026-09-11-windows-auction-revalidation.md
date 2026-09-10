# Windows Auction Revalidation - 2026-09-11

## Scope And Root Cause

Revalidated the existing implementation against remote main a309fdf34feaf93c498a1eb222aff6a22edecac6.
No scoring, market inference, historical auction reconstruction or frozen bytes were changed.

Primary 2026-09-09 classification: TASK_NOT_TRIGGERED at 09:12.
System events were read again on this host: RuntimeBroker power-off at 03:54:58,
Kernel-General shutdown at 03:55:16, next boot at 09:15:11.500 Shanghai time.
This was a powered-off machine, not a proven sleep or quote-source failure.
The later scheduled live task ran at 09:19; collection started 09:19:26.226,
froze at 09:25:02.461 and generated the report at 09:25:10.169.
Only 65/131 formal matches succeeded. Quality and timeliness remain FAIL.
The reason for 66 missing formal matches is not established by the retained evidence.

Secondary classification: GIT_SYNC_FAILED, recorded by the original receipt.
The earlier recovery reproduced missing Git on the scheduler PATH and fixed
absolute executable resolution and local proxy use. The original failing Git
command cannot be recovered because its exception details were not retained.
The 9/9 packets and PUSHED receipt already exist on current remote main.
Full/compact remote bytes match the immutable local SHA; the mutable run receipt
matches semantically (Git newline conversion is not a frozen packet change).

## Actual Registered Tasks

Read from Task Scheduler, including exported XML, on 2026-09-11.
All six tasks are enabled and Ready, current-user Interactive logon.

| Task | Last run returned by CIM | Result | Trigger from XML |
| --- | --- | --- | --- |
| Ashare-Auction-Live | 2026-09-09 09:19:19 | 1 | 09:12:00 daily |
| Ashare-Auction-0935 | 2026-09-09 09:35:35 | 0 | 09:35:00 daily |
| Ashare-Auction-0945 | 2026-09-09 09:45:45 | 0 | 09:45:00 daily |
| Ashare-Auction-1000 | 2026-09-09 10:00:00 | 0 | 10:00:00 daily |
| Ashare-Auction-EOD | 2026-09-09 19:44:44 | 1 | 15:15:00 daily |
| Ashare-Auction-Watchdog | 2026-09-09 21:01:01 | 0 | 09:13:00 daily |

NextRunTime returned by CIM is 9/11 at 09:12:12, 09:35:35, 09:45:45,
10:00:00, 15:15:15, and 09:13:13 respectively. These displayed seconds
are not substituted for the actual XML trigger boundaries.
Common settings: WakeToRun=true, StartWhenAvailable=true, limit PT25M,
two retries one minute apart, IgnoreNew, battery start allowed and no battery stop.
The task identity and full absolute paths are retained in the local exported XML.
All tasks invoke System32 Windows PowerShell with hidden/noninteractive flags,
the active checkout's tools/run_auction_task.ps1, and stage live/post-open/eod/watchdog.
WorkingDirectory is the active a_share_daily_review_codex-sync checkout.
The wrapper uses its existing .venv/Scripts/python.exe, Python 3.12.14.
The other discovered a_share_daily_review_codex checkout has no matching 9/9 auction files.

## Host Boundaries

The host was awake at audit time. AC and DC wake timers both remain enabled.
Enumerating actual wake timers requires elevation; no physical sleep/wake test was done.
TaskScheduler/Operational is still disabled, so past task-level trigger events
are unavailable. System shutdown/boot evidence does remain available.
WakeToRun cannot start an already powered-off machine. Locking is not sign-out;
the present Interactive task identity requires the user to remain logged in.
The source itself requires no GUI. Logged-out operation needs locally provisioned
Password logon and testing of that identity's network/proxy/Git credentials.
No Windows password has been obtained, guessed, stored in this repository or logged.
The existing installer supports provisioning via a locally supplied PSCredential:

```powershell
$Credential = Get-Credential
.\tools\install_auction_tasks.ps1 -LogonType Password -Credential $Credential
```

Reboots, updates, power-off and sign-out can still interrupt collection. Late-start
classification remains PASS through 09:15:05, PARTIAL through 09:16:00, otherwise FAIL.

## Fresh Diagnostics And Repairs

Added -AuditDate to host readiness, replacing the hard-coded file date and today's-only
event lookup. Added --dry-run-date restricted to dry runs; it selects review context
only, never the live collection date. Observation/start timestamps remain actual.
Preflight now fails explicitly on a missing exact previous formal review even if
the source connects. No fallback to an older review and no quality gate reduction.

At 00:18 Shanghai, five stocks through quote/process/formal interfaces returned
15/15 nonempty responses, no failures/timeouts, connect 682.604 ms,
requests 13.924-74.091 ms. This is transport evidence only, not same-day auction
facts or an accepted live session. Diagnostic rows were not imported into packets.

A temporary task cloned the production task identity, settings, executable and
working directory, appending -DryRun -DryRunDate 2026-09-09. Task result was 0.
It read exact 9/8 review READY, connected to eltdx, obtained 15/15 responses,
wrote isolated receipts and completed authenticated Git push --dry-run.
The temporary audit task is removed after verification, not any production task.

Local retained evidence:
- data/auction_host_audit/20260911-001824/: current inventory and source probe.
- data/auction_host_audit/20260911-002034/: 9/9 event and repository-file audit.
- data/auction_dry_runs/: timestamped task-launched diagnostic receipts and logs.
- data/auction_host_audit/20260909-203507/: original failure receipt and task XML.

Tests: 26 targeted tests passed; full non-real-data suite 512 passed, 1 deselected;
compileall passed. Added historical-date live rejection, diagnostic isolation,
and missing/present exact review preflight cases. Existing tests retain bare-remote
commit/push, retry, immutable SHA, lock, stage and source-failure coverage.

## Recovery And Next Session Acceptance

The existing watchdog at 09:13 uses the shared OS lock and only launches for a
missing/NOT_STARTED receipt. It does not overwrite frozen/failed completed runs.
Durable logs and stage receipts remain local-first. A failed push preserves
immutable facts and can be retried without importing any collector:

```powershell
.venv\Scripts\python.exe tools/retry_auction_sync.py --date 2026-09-09
```

Current 9/11 preflight confirms 9/10 Market Packet and Review Context available,
but exact 9/10 formal review MISSING: PREVIOUS_FORMAL_REVIEW_UNAVAILABLE.
That review must be supplied by its authorized author before live collection;
Codex does not fabricate it. The machine must also be powered on and logged in.

Required next live evidence: 09:12 scheduler receipt, 09:15 collection, checkpoints
through 09:25, formal match and immutable freeze, full/compact report before 09:26,
then acknowledged remote main publication of both packets and the run receipt.
PUSHED is distribution status, not evidence that quality or timeliness passed.
No future live session is claimed to have occurred at this midnight audit.

Current readiness: PARTIALLY_READY. Missing 9/10 formal review, unverified logged-out
operation and lack of a newly completed live session prevent a stronger claim.
