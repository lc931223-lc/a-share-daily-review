# Windows Auction Host Recovery - 2026-09-09

## Failure Root Cause

Primary classification: **TASK_NOT_TRIGGERED** at the intended 09:12 slot.
This was a powered-off host, not an unregistered task or an assumed source failure.
System event 1074 at 03:54:58 records RuntimeBroker initiating power-off on behalf
of the current user. Kernel-General event 13 records shutdown at 03:55:16.
Kernel-General event 12 records the next boot at 09:15:11.500 (Shanghai time).
The operating system was therefore not running at 09:12. No evidence attributes
this shutdown to Windows Update. The live task subsequently ran at 09:19.

Secondary classification: **GIT_SYNC_FAILED**. The old run receipt records
PERSIST_FAILED_LOCAL_ARTIFACTS_RETAINED. A real Task Scheduler dry run reproduced
FileNotFoundError / WinError 2 launching `git`: the scheduler PATH did not contain
the Codex-bundled Git used by the interactive terminal. The original runner
discarded exception details, so the exact original failing Git command is not
recoverable. Direct GitHub connectivity had also failed in prior runs. Both the
absolute executable resolution and configured Windows loopback proxy are now
handled explicitly; neither is inferred from the presence of a local packet.

Collection was real but incomplete: 131 watched stocks, 65 formal matches,
66 `formal opening match unavailable` failures. It started 09:19:26.226, froze
09:25:02.461 and generated the report 09:25:10.169. Live acceptance is FAIL,
not a successful full-session run. This audit does not claim a proven server-side
reason for those 66 empty responses. Two bounded missing-only live retries were
added for future runs; they do not recover or rewrite today's frozen observations.

## Registered Tasks

Read from actual Task Scheduler objects and exported XML, not inferred from the
installer. All five original tasks exist, Enabled=true, State=Ready.

| Task | LastRunTime as returned by CIM | Result | NextRunTime as returned by CIM |
|---|---|---:|---|
| Ashare-Auction-Live | 2026-09-09 09:19:19 | 1 | 2026-09-10 09:12:12 |
| Ashare-Auction-0935 | 2026-09-09 09:35:35 | 0 | 2026-09-10 09:35:35 |
| Ashare-Auction-0945 | 2026-09-09 09:45:45 | 0 | 2026-09-10 09:45:45 |
| Ashare-Auction-1000 | 2026-09-09 10:00:00 | 0 | 2026-09-10 10:00:00 |
| Ashare-Auction-EOD | 2026-09-09 19:44:44 | 1 | 2026-09-10 15:15:15 |

These are the API-returned timestamps, including their seconds; actual exported
daily trigger boundaries are 09:12:00 / 09:35:00 / 09:45:00 / 10:00:00 / 15:15:00.
The last run can be a retry, not necessarily the first activation of that day.
TaskScheduler/Operational was disabled. Enabling it was attempted and returned
Access Denied; missing historical task events were not fabricated.

Common registered settings after repair:

- Principal: current Windows user (LAPTOP-KACLO32K\愚者), InteractiveToken, Limited.
- WakeToRun=true, StartWhenAvailable=true, execution limit PT25M.
- RestartCount=2, RestartInterval=PT1M, MultipleInstances=IgnoreNew.
- DisallowStartIfOnBatteries=false; StopIfGoingOnBatteries=false.
- Program: Windows PowerShell executable under System32, with `-NoProfile
  -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass`.
- Action script: `<repo>/tools/run_auction_task.ps1 -Stage <stage>`.
- WorkingDirectory: `D:\桌面\新建文件夹\a_share_daily_review_codex-sync`.
- Wrapper invokes that repo's `.venv/Scripts/python.exe`, verified Python 3.12.14.
- Git path is resolved during installation and stored in ignored
  `data/auction_host_config.json`; currently it is the Codex native runtime Git.
- A daily Ashare-Auction-Watchdog task is registered for 09:13:00, same identity.

All program/script paths exist. A task-launched dry run exercised the Chinese
directory name, spaces, working directory and Python path successfully. The old
`a_share_daily_review_codex` copy also exists, but its scan found no 9/9 auction
data; the scheduler uses the current main-delivery checkout, not that old copy.

## Login And Power Boundary

This collector does not require GUI or a desktop quote client. Interactive login
is currently an identity/credential provisioning dependency, not a market API
requirement. Registration of a non-interactive S4U dry-run task returned Access
Denied. S4U is not a production substitute for network-capable password logon:
[Microsoft documents its network/encrypted-file restrictions](https://learn.microsoft.com/en-us/windows/win32/api/taskschd/ne-taskschd-task_logon_type).

The installer now supports `-LogonType Password -Credential <PSCredential>` for
an administrator/user to provision locally. No password was requested in chat,
logged, put in source, or guessed. That mode and logged-out Git authentication
are NOT verified. Until provisioned and tested, the user must remain logged in.
Locking the desktop is compatible with that condition; signing out is not.

Wake timer policy was AC=important-only, DC=disabled. Both were changed to enabled
and the active plan reapplied. Battery-start and battery-stop restrictions were
removed from these tasks. A physical sleep/wake cycle was not performed, and
enumerating wake timers requires privileges not available in this session.
[WakeToRun covers sleep/hibernate](https://learn.microsoft.com/en-us/windows/win32/taskschd/tasksettings-waketorun),
not an already powered-off computer. Keep the host powered on before 09:12.
Reboot/Windows Update can interrupt the process; StartWhenAvailable cannot
retroactively recreate missed live snapshots. Late starts remain degraded.

## Local Evidence And Source Test

Pre-repair local files in the active repo:

- `data/auction_raw_frozen/2026-09-09.json`: 21,856,304 bytes, retained locally.
- `data/auction_packets/2026-09-09.json`: 2,933,834 bytes.
- `data/auction_packets/2026-09-09_compact.json`: 766,017 bytes.
- `data/auction_runs/2026-09-09.json`: original 1,217-byte failure receipt.
- `data/auction_post_open/2026-09-09.json`: 362,730 bytes.
- `data/auction_eod/2026-09-09.json`: 1,245,983 bytes.
- `data/auction_watchlists/auction_watchlist_2026-09-09.json`: 35,734 bytes.

Original packet SHA-256:
`7199891fe25a1f0744da4dca7edcaf77fbd9a2bdea5a8086d5e3c32087e4ae88`.
Original compact SHA-256:
`50ef0dbdc3c3f0355095f5299c30a4011d9b1a4c4755bbf6e573f015283f5762`.
The original run receipt was copied into the audit folder before any sync retry.

20:55 Windows diagnostic: 000001 / 000333 / 300750 / 600519 / 601318, each tested
through quotes, process series and opening-match-today. Connection 1,037.708 ms;
15/15 requests returned data, 0 failures, 0 timeouts, per-request 16.647-103.950 ms.
Process point counts were 74/79/88/184/218. These are after-hours interface
diagnostics, not proof of contemporaneous 09:15 retrieval. No diagnostic rows
were imported into FactStore, raw freeze, or Auction Packet.

## Logs, Receipts And Recovery

The PowerShell bootstrap logs before Python starts and captures stdout/stderr.
Python logs environment, repository revision, exact previous review, connect,
each checkpoint, formal match, raw freeze, report generation and Git commands.
Exceptions include type and traceback. Log records are flushed; JSON receipts
are fsynced then atomically replaced. Stage history is retained in the receipt.

`data/auction_logs/YYYY-MM-DD/live.log` is append-only. Local dry runs instead
use `data/auction_dry_runs/<timestamp>/`, so they cannot replace production runs.
Code/bootstrap import failures are observable even before 09:15.

Stages include SCHEDULER_STARTED, PREFLIGHT_RUNNING/FAILED, SOURCE_CONNECTED,
COLLECTING, COLLECTION_FAILED, FORMAL_MATCH_PENDING, AUCTION_FROZEN, REPORT_READY,
GIT_SYNC_PENDING/FAILED and PUSHED. `local_report_status=LOCAL_REPORT_READY` is
independent of distribution and collection quality. PUSHED does not mean that
the market-data acceptance passed.

Watchdog launches only for missing/NOT_STARTED receipts in the live window. The
primary, watchdog and retry command share an OS-released lock; a crashed process
does not leave an unrecoverable directory lock. Existing active/finished/failed
receipts are not blindly overwritten by watchdog. No duplicate collector runs.
Starts through 09:15:05 are PASS, through 09:16:00 PARTIAL, later FAIL. A slow
source connection is included in start classification.

Independent distribution command:

```powershell
.venv\Scripts\python.exe tools/retry_auction_sync.py --date 2026-09-09
```

It imports no collector. It checks packet, compact and local raw SHA, then stages
only allowed auction data. Pre-staged user work and unrelated local commits are
rejected. Push failure remains GIT_SYNC_FAILED; local facts and retryable commits
remain. Remote advancement gets one bounded fetch/rebase retry, never force push.
The successful receipt identifies the acknowledged data commit; it is published
in a following receipt commit to avoid a self-referential SHA.

## Verification And Next Session

Offline suite: 337 passed, 1 real_data test deselected. compileall passed.
Tests cover local bare-remote push, push failure/retry of existing commits, remote
advancement, SHA corruption, staged-work protection, OS lock, stage history,
watchdog no-duplicate behavior, pre-09:15 errors, late-start boundaries, bounded
formal retry and source cleanup. No score functions or weights were changed.

Task Scheduler dry run returned 0: correct Python/repo, 9/8 exact review READY,
eltdx requests, isolated local receipt and authenticated Git push dry-run passed.
Original failed dry-run logs are retained, including the missing-Git traceback.

Next trading session is 2026-09-10. Required before 09:12: host powered on and
logged in, Git executable and credentials accessible, exact 2026-09-09 formal
review and required previous-day inputs delivered. At audit time the exact 9/9
formal review, Review Context and Market Packet were not locally available.
The runner will record PREFLIGHT_FAILED, not fall back to 9/8.

Acceptance: scheduler receipt around 09:12; watchdog at 09:13 if needed; live
checkpoints from 09:15 through 09:25; formal match then immutable local freeze;
full/compact packet by 09:26; subsequent push must publish both packets and the
run receipt. A local report with delayed push is not discarded. Its quality,
timeliness and provenance must still pass independently of Git success.

Current readiness: **PARTIALLY_READY**. No claim is made that a repaired next-day
live session, physical wake cycle or logged-out production run has been accepted.

Local evidence directories (ignored by Git, not deleted):
`data/auction_host_audit/20260909-203507/` (original XML/receipt),
`data/auction_host_audit/20260909-205515/` (post-repair inventory/source test), and
`data/auction_dry_runs/20260909-204417/`, `20260909-204501/` (failed/successful task tests).
