"""Scheduler boundary: log before heavy imports; preserve local frozen facts."""

# ruff: noqa: BLE001
import argparse
import getpass
import os
import platform
import socket
import sys
import traceback
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.auction.production import log_event, read, update_run, write


def execute(args, root, day):
    from src.auction.pipeline import AuctionPipeline
    from src.auction.previous_context import load_previous_context

    pipeline = AuctionPipeline(root=root)
    update_run(root, day, "PREFLIGHT_RUNNING", status="PREFLIGHT_RUNNING")
    calendar = pipeline.calendar_loader(day)
    if not any(d.cal_date == day and d.is_open for d in calendar):
        update_run(root, day, "NOT_STARTED", status="SKIPPED_NON_TRADING_DAY")
        return 0
    previous = load_previous_context(root, day, calendar)
    update_run(
        root,
        day,
        "PREFLIGHT_RUNNING",
        previous_trade_date=previous["previous_trade_date"],
        previous_official_review_status="READY"
        if previous["official_review_loaded"]
        else "MISSING",
    )
    if args.stage == "live" and not previous["official_review_loaded"]:
        raise ValueError("PREVIOUS_FORMAL_REVIEW_UNAVAILABLE")
    if args.stage == "live":
        result = pipeline.run_live(day, force=args.force)
        quality = result.get("packet", {}).get("data_quality", {}).get("status")
        update_run(
            root,
            day,
            "REPORT_READY",
            status="LOCAL_REPORT_READY",
            collection_quality=quality,
            packet_generated_at=result["packet"]["meta"].get("auction_report_generated_at"),
            packet_paths=result["paths"],
        )
        return 1 if quality == "FAIL" else 0
    if args.stage == "post-open":
        pipeline.run_post_open(day)
        return 0
    return 0 if pipeline.reconcile_eod(day)["status"] == "PASS" else 1


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=["live", "post-open", "eod", "watchdog"], required=True)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--sync", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--dry-run-date", type=date.fromisoformat)
    args = parser.parse_args(argv)
    if args.dry_run_date and not args.dry_run:
        parser.error("--dry-run-date requires --dry-run; historical collection is forbidden")
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    if args.dry_run_date and args.dry_run_date > now.date():
        parser.error("--dry-run-date cannot be in the future")
    day = now.date()
    receipt_root = (
        ROOT / "data/auction_dry_runs" / now.strftime("%Y%m%d-%H%M%S") if args.dry_run else ROOT
    )
    log_event(
        receipt_root,
        day,
        "script_started_at",
        script_started_at=now.isoformat(),
        scheduler_triggered_at=os.getenv("AUCTION_SCHEDULER_TRIGGERED_AT"),
        hostname=socket.gethostname(),
        username=getpass.getuser(),
        cwd=os.getcwd(),
        repo_path=str(ROOT),
        python_executable=sys.executable,
        python_version=platform.python_version(),
        requested_stage=args.stage,
    )
    from src.auction.host_lock import AlreadyRunning, auction_lock

    try:
        with auction_lock(ROOT, day):
            if args.stage == "watchdog":
                receipt = read(ROOT / "data/auction_runs" / f"{day}.json", {})
                if receipt.get("stage", "NOT_STARTED") != "NOT_STARTED":
                    log_event(
                        ROOT,
                        day,
                        "WATCHDOG_NOOP",
                        reason="existing_receipt",
                        stage=receipt.get("stage"),
                    )
                    return 0
                if now.hour != 9 or now.minute > 25:
                    log_event(ROOT, day, "WATCHDOG_NOOP", reason="outside_live_window")
                    return 0
                args.stage = "live"
            update_run(
                receipt_root,
                day,
                "SCHEDULER_STARTED",
                status="SCHEDULER_STARTED",
                script_started_at=now.isoformat(),
                scheduler_triggered_at=os.getenv("AUCTION_SCHEDULER_TRIGGERED_AT"),
            )
            code = 1
            try:
                from src.auction.git_sync import git, persist, refresh

                try:
                    log_event(
                        receipt_root,
                        day,
                        "repository",
                        git_branch=git(ROOT, "branch", "--show-current"),
                        git_head_sha=git(ROOT, "rev-parse", "HEAD"),
                    )
                except Exception:
                    log_event(
                        receipt_root,
                        day,
                        "repository_metadata_unavailable",
                        exception_traceback=traceback.format_exc(),
                    )
                if args.dry_run:
                    from tools.auction_preflight import preflight
                    from tools.probe_auction_host_source import probe

                    update_run(receipt_root, day, "PREFLIGHT_RUNNING")
                    evaluation_time = (
                        now.replace(
                            year=args.dry_run_date.year,
                            month=args.dry_run_date.month,
                            day=args.dry_run_date.day,
                        )
                        if args.dry_run_date
                        else now
                    )
                    result = preflight(ROOT, now=evaluation_time)
                    result["started_at"] = now.isoformat()
                    result["diagnostic_observed_at"] = now.isoformat()
                    result["scope"] = "HOST_DIAGNOSTIC_NOT_LIVE_ACCEPTANCE"
                    result["source_probe"] = probe()
                    result["git_access"] = git(ROOT, "ls-remote", "origin", "refs/heads/main")
                    result["git_push_dry_run"] = git(
                        ROOT, "push", "--dry-run", "origin", "HEAD:main"
                    )
                    write(receipt_root / "result.json", result)
                    code = (
                        0
                        if result["status"] == "PASS"
                        and result.get("previous_review_status") == "READY"
                        and result["source_probe"]["connect_result"] == "PASS"
                        and result["source_probe"]["success_count"] == 15
                        else 1
                    )
                    update_run(
                        receipt_root,
                        day,
                        "SOURCE_CONNECTED" if code == 0 else "PREFLIGHT_FAILED",
                        status="DRY_RUN_PASS" if code == 0 else "DRY_RUN_FAIL",
                        result_path=str(receipt_root / "result.json"),
                    )
                    return code
                if args.sync and args.stage == "live":
                    try:
                        log_event(ROOT, day, "git_refresh", result=refresh(ROOT))
                    except Exception:
                        log_event(
                            ROOT,
                            day,
                            "git_refresh_failed_continue_local",
                            traceback=traceback.format_exc(),
                        )
                code = execute(args, ROOT, day)
            except Exception as exc:
                receipt = read(receipt_root / "data/auction_runs" / f"{day}.json", {})
                stage = (
                    "PREFLIGHT_FAILED"
                    if receipt.get("stage")
                    in {"SCHEDULER_STARTED", "PREFLIGHT_RUNNING", "PREFLIGHT_FAILED"}
                    else "COLLECTION_FAILED"
                )
                update_run(
                    receipt_root,
                    day,
                    stage,
                    status=stage,
                    exception_type=type(exc).__name__,
                    exception_traceback=traceback.format_exc(),
                    failures=receipt.get("failures", [])
                    + [{"stage": args.stage, "error_type": type(exc).__name__, "error": str(exc)}],
                )
            finally:
                if args.sync and not args.dry_run:
                    try:
                        from src.auction.git_sync import persist

                        persist(ROOT, day)
                    except Exception:
                        log_event(ROOT, day, "git_sync_failed", traceback=traceback.format_exc())
                        code = 1
            return code
    except AlreadyRunning:
        log_event(receipt_root, day, "RUN_ALREADY_ACTIVE")
        return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        log_event(
            ROOT,
            datetime.now(ZoneInfo("Asia/Shanghai")).date(),
            "BOOTSTRAP_FAILED",
            exception_traceback=traceback.format_exc(),
        )
        raise
