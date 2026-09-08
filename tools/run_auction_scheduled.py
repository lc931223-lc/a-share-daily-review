"""Bounded scheduled entry. Never sleeps through post-open or rewrites a frozen report."""

from pathlib import Path
import argparse
import json
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.auction.pipeline import AuctionPipeline
from src.auction.production import read, update_run


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=["live", "post-open", "eod"], required=True)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--sync", action="store_true")
    args = parser.parse_args()
    day = datetime.now(ZoneInfo("Asia/Shanghai")).date()
    sync_status = None
    if args.sync and args.stage == "live":
        from src.auction.git_sync import refresh

        try:
            sync_status = refresh(ROOT)
        except Exception:
            sync_status = "REFRESH_FAILED_CONTINUE_LOCAL"
    pipeline = AuctionPipeline()
    calendar = pipeline.calendar_loader(day)
    if not any(d.cal_date == day and d.is_open for d in calendar):
        update_run(ROOT, day, "NOT_STARTED", status="SKIPPED_NON_TRADING_DAY")
        print("SKIPPED_NON_TRADING_DAY")
        return 0
    # Atomic directory lock avoids overlapping local scheduler launches; manual
    # recovery of an abandoned lock is explicit so two collectors cannot coexist.
    lock = ROOT / "data/auction_runs" / f"{day}.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    try:
        if sync_status:
            previous = read(ROOT / "data/auction_runs" / f"{day}.json", {})
            update_run(ROOT, day, previous.get("stage", "NOT_STARTED"), sync_status=sync_status)
        lock.mkdir()
    except FileExistsError:
        print("RUN_ALREADY_ACTIVE_OR_STALE_LOCK")
        return 1
    try:
        if args.stage == "live":
            result = pipeline.run_live(day, force=args.force)
            if result.get("packet", {}).get("data_quality", {}).get("status") == "FAIL":
                raise RuntimeError("LIVE_DATA_FAILURE")
            print(json.dumps({"status": result.get("status") or result["packet"]["report_status"]}))
        elif args.stage == "post-open":
            pipeline.run_post_open(day)
        else:
            if pipeline.reconcile_eod(day)["status"] != "PASS":
                raise RuntimeError("EOD_INCOMPLETE")
        return 0
    except Exception as exc:
        path = ROOT / "data/auction_runs" / f"{day}.json"
        receipt = read(path, {})
        update_run(
            ROOT,
            day,
            receipt.get("stage", "NOT_STARTED"),
            status="FAILED",
            failures=receipt.get("failures", [])
            + [{"stage": args.stage, "error_type": type(exc).__name__}],
            retry_count=receipt.get("retry_count", 0) + 1,
        )
        print(json.dumps({"status": "FAILED", "error_type": type(exc).__name__}))
        return 1
    finally:
        lock.rmdir()
        if args.sync:
            from src.auction.git_sync import persist

            try:
                persist(ROOT, day)
            except Exception:
                receipt = read(ROOT / "data/auction_runs" / f"{day}.json", {})
                update_run(
                    ROOT,
                    day,
                    receipt.get("stage", "NOT_STARTED"),
                    sync_status="PERSIST_FAILED_LOCAL_ARTIFACTS_RETAINED",
                )


if __name__ == "__main__":
    raise SystemExit(main())
