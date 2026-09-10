"""Build objective radar snapshots or an explicitly labeled as-of replay."""
import argparse
from datetime import date, datetime, time, timedelta
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.market_packet.trading_calendar import load_trading_calendar
from src.opportunity_radar.contracts import SHANGHAI, CATEGORIES
from src.opportunity_radar.pipeline import RadarPipeline
from src.opportunity_radar.schema import schema
from src.opportunity_radar.sources import archived_disclosures, fetch_series


def collection_end(day, snapshot, now):
    if day > now.date():
        raise ValueError("FUTURE_COLLECTION_DATE")
    if snapshot == "MORNING":
        return day-timedelta(days=1)
    if day == now.date() and now.time() < time(15, 5):
        raise ValueError("MARKET_NOT_CLOSED")
    return day


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", default="auto")
    parser.add_argument("--snapshot", choices=["MORNING", "EOD"], default="MORNING")
    parser.add_argument("--as-of")
    parser.add_argument("--collect", action="store_true")
    parser.add_argument("--collect-only", action="store_true")
    parser.add_argument("--enrich", action="store_true")
    parser.add_argument("--import-json", type=Path)
    parser.add_argument("--replay", action="store_true")
    parser.add_argument("--replay-start", type=date.fromisoformat)
    parser.add_argument("--replay-end", type=date.fromisoformat)
    parser.add_argument("--write-schema", action="store_true")
    args = parser.parse_args(argv)
    if args.write_schema:
        path = ROOT / "schemas/opportunity_radar_objective.schema.json"
        path.write_text(json.dumps(schema(), ensure_ascii=False, indent=2), encoding="utf-8")
        print(path)
        return 0
    now = datetime.now(SHANGHAI)
    day = now.date() if args.date == "auto" else date.fromisoformat(args.date)
    pipeline = RadarPipeline(ROOT)
    rows, receipts = archived_disclosures(ROOT)
    pipeline.store.append(rows)
    if args.enrich:
        from src.opportunity_radar.enrichment import collect_enrichment
        fresh, results, edges = collect_enrichment(ROOT, day)
        pipeline.store.append(fresh)
        receipts.extend(results)
        relation_path = ROOT / "data/reference/opportunity_relations.json"
        old = json.loads(relation_path.read_text(encoding="utf-8")) if relation_path.exists() else []
        from src.opportunity_radar.contracts import digest
        from src.auction.production import write
        from src.opportunity_radar.relations import merge_relations
        write(relation_path, merge_relations(old + edges))
    if args.import_json:
        # Imported records retain their source publication and observation timestamps.
        pipeline.store.append(json.loads(args.import_json.read_text(encoding="utf-8")))
    if args.collect:
        end = collection_end(day, args.snapshot, now)
        fresh, results = fetch_series(ROOT, end-timedelta(days=550), end)
        pipeline.store.append(fresh)
        receipts.extend(results)
    if args.collect or args.collect_only or args.enrich:
        path = ROOT / "data/opportunity_radar/diagnostics" / (now.strftime("%Y%m%dT%H%M%S") + ".json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"retrieved_at": now.isoformat(), "sources": receipts}, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"diagnostics": str(path), "observations": len(pipeline.store.all())}))
    if args.collect_only:
        return 0
    days = load_trading_calendar(day, cache_root=ROOT / "data/reference")
    if args.replay_start:
        end = args.replay_end or day
        history = pipeline.store.all()
        summaries = []
        for entry in sorted(days, key=lambda r: r.cal_date):
            if not entry.is_open or not args.replay_start <= entry.cal_date <= end:
                continue
            packet = pipeline.build(entry.cal_date, "EOD", replay=True, rows=history)
            summaries.append({"date": str(entry.cal_date), "positive_count": len(packet["positive_change_candidates"]),
                              "negative_count": len(packet["negative_risk_candidates"]),
                              "observation_count": sum(len(packet[k]) for k in CATEGORIES.values()),
                              "signal_first_seen": [{k: r[k] for k in ("entity", "theme", "signal_type", "signal_first_seen_date")} for r in packet["positive_change_candidates"] + packet["negative_risk_candidates"]],
                              "feedback": packet["lead_time_statistics"]})
        output = ROOT / "data/opportunity_radar/replay" / f"{args.replay_start}-to-{end}.json"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps({"mode": "AS_OF_REPLAY", "start": str(args.replay_start), "end": str(end),
                                     "days": summaries, "coverage": "Missing point-in-time evidence is not backfilled"}, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"replay": str(output), "sessions": len(summaries)}))
    if not any(r.cal_date == day and r.is_open for r in days):
        print("NON_TRADING_DAY")
        return 0
    packet = pipeline.build(day, args.snapshot, as_of=args.as_of, replay=args.replay)
    full, small, packet = pipeline.write(packet)
    print(json.dumps({"full": str(full), "compact": str(small), "mode": packet["meta"]["execution_mode"],
                      "positive": len(packet["positive_change_candidates"]), "negative": len(packet["negative_risk_candidates"]),
                      "company_specific": len(packet["company_specific_candidates"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
