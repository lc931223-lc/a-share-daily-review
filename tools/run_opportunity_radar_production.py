"""Scheduled production boundary; diagnostics survive failure and deadlines stay strict."""
import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.auction.production import write
from src.market_packet.trading_calendar import load_trading_calendar
from src.opportunity_radar.contracts import SHANGHAI, CATEGORIES
from src.opportunity_radar.coverage import coverage_metrics
from src.opportunity_radar.pipeline import RadarPipeline, read_context
from src.opportunity_radar.enrichment import collect_enrichment
from src.opportunity_radar.sources import archived_disclosures, fetch_series


def run(root, day, snapshot, *, replay=False):
    now = datetime.now(SHANGHAI)
    path = root / "data/opportunity_radar/diagnostics" / f"{day}_{snapshot.lower()}_production.json"
    receipt = {"trade_date": str(day), "snapshot": snapshot, "observed_at": now.isoformat(),
               "status": "RUNNING", "run_id": os.getenv("GITHUB_RUN_ID"),
               "retry_count": max(0, int(os.getenv("RADAR_ATTEMPT", "1"))-1), "sources": []}
    write(path, receipt)
    try:
        days = load_trading_calendar(day, cache_root=root / "data/reference")
        if not any(d.cal_date == day and d.is_open for d in days):
            receipt["status"] = "SKIPPED_NON_TRADING_DAY"
            return receipt
        pipeline = RadarPipeline(root)
        # Validate requested temporal window before any network work.
        pipeline.build(day, snapshot, replay=replay, rows=[])
        if not replay and (root / f"data/opportunity_radar/{day}_{snapshot.lower()}.json").exists():
            context = read_context(root, day, snapshot)
            receipt.update(status="FROZEN_ALREADY_EXISTS", full=context["path"])
            return receipt
        old, _ = archived_disclosures(root)
        pipeline.store.append(old)
        end = day - timedelta(days=1) if snapshot == "MORNING" else day
        series, series_receipts = fetch_series(root, end-timedelta(days=550), end)
        pipeline.store.append(series)
        fresh, receipts, edges = collect_enrichment(root, day)
        receipt["sources"] = series_receipts + receipts
        if not fresh:
            raise ValueError("NO_CURRENT_SOURCE_OBSERVATIONS")
        pipeline.store.append(fresh)
        from src.opportunity_radar.contracts import digest
        relation_path = root / "data/reference/opportunity_relations.json"
        prior = json.loads(relation_path.read_text(encoding="utf-8")) if relation_path.exists() else []
        from src.opportunity_radar.relations import merge_relations
        write(relation_path, merge_relations(prior + edges))
        packet = pipeline.build(day, snapshot, replay=replay)
        if not any(packet[field] for field in CATEGORIES.values()):
            raise ValueError("NO_AS_OF_ADMISSIBLE_OBSERVATIONS")
        full, small, packet = pipeline.write(packet)
        metrics = coverage_metrics(pipeline.store.all(), datetime.fromisoformat(packet["meta"]["as_of"]))
        metrics.update(verified_relation_count=len(packet["industry_transmission_mapping"]),
                       company_alpha_count=len(packet["company_specific_candidates"]),
                       morning_candidate_count=len(packet["positive_change_candidates"])+len(packet["negative_risk_candidates"]),
                       compact_size=small.stat().st_size, full_size=full.stat().st_size)
        write(root / "data/opportunity_radar/coverage" / f"{day}_{snapshot.lower()}.json", metrics)
        receipt.update(status="PARTIAL", full=str(full.relative_to(root)), compact=str(small.relative_to(root)),
                       mode=packet["meta"]["execution_mode"], coverage=metrics)
        return receipt
    except Exception as exc:
        receipt.update(status="FAILED", blocker=str(exc), error_type=type(exc).__name__)
        raise
    finally:
        write(path, receipt)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default="auto")
    parser.add_argument("--snapshot", choices=["AUTO", "MORNING", "EOD"], default="AUTO")
    parser.add_argument("--replay", action="store_true")
    args = parser.parse_args()
    now = datetime.now(SHANGHAI)
    day = now.date() if args.date == "auto" else date.fromisoformat(args.date)
    snapshot = ("MORNING" if now.hour < 12 else "EOD") if args.snapshot == "AUTO" else args.snapshot
    print(json.dumps(run(ROOT, day, snapshot, replay=args.replay), ensure_ascii=False))
