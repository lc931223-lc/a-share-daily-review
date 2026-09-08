from pathlib import Path
import argparse
import hashlib
import json
import sys
from datetime import date, datetime, time
from zoneinfo import ZoneInfo
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.auction.production import read, write
from src.market_packet.trading_calendar import load_trading_calendar


def validate(root, day, calendar=None):
    calendar = (
        calendar
        if calendar is not None
        else load_trading_calendar(day, cache_root=root / "data/reference")
    )
    p = read(root / "data/auction_packets" / f"{day}.json", {})
    c = read(root / "data/auction_packets" / f"{day}_compact.json", {})
    run = read(root / "data/auction_runs" / f"{day}.json", {})
    post = read(root / "data/auction_post_open" / f"{day}.json", {})
    eod = read(root / "data/auction_eod" / f"{day}.json", {})
    schema_ok = True
    try:
        for value, name in ((p, "auction_packet"), (c, "auction_packet_compact")):
            Draft202012Validator(read(ROOT / "schemas" / f"{name}.schema.json")).validate(value)
    except Exception:
        schema_ok = False
    previous = max((d.cal_date for d in calendar if d.is_open and d.cal_date < day), default=None)
    timing = p.get("auction_timeliness", {})
    quality = p.get("market_auction_summary", {})
    snapshots = post.get("snapshots", {})
    observed = [
        datetime.fromisoformat(t).astimezone(ZoneInfo("Asia/Shanghai")).time() for t in snapshots
    ]
    scores = p.get("scored_stock_ranking", [])
    trace = bool(scores) and all(
        abs(
            sum(float(c["score"] or 0) for c in r["score"]["components"].values())
            - r["score"]["gross_score"]
        )
        < 0.01
        and r["score"]["final_score"]
        == round(max(0, r["score"]["gross_score"] - r["score"]["risk_deduction"]), 4)
        for r in scores
    )
    path = root / "data/auction_packets" / f"{day}.json"
    digest = hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
    checks = dict(
        trading_day=any(d.cal_date == day and d.is_open for d in calendar),
        live=p.get("meta", {}).get("mode") == "live",
        started_before_0915=bool(timing.get("collection_start_time"))
        and datetime.fromisoformat(timing["collection_start_time"]).time() <= time(9, 15, 5),
        eleven_checkpoints=quality.get("checkpoint_coverage") == 1,
        post920=quality.get("post_0920_checkpoint_coverage") == 1,
        formal_match=quality.get("formal_opening_match_success_rate") == 1,
        full_packet=bool(p),
        compact=bool(c),
        schema=schema_ok,
        previous_exact=p.get("previous_context", {}).get("previous_trade_date") == str(previous)
        and p.get("previous_context", {}).get("official_review_loaded") is True,
        score_trace=trace,
        unavailable_direction=all(
            not r.get("unmatched_direction")
            or r.get("unmatched_direction") == "unavailable"
            or r.get("source_contract_reference")
            for r in p.get("stock_auction_summary", [])
        ),
        report_before_0930=bool(timing.get("report_generated_at"))
        and datetime.fromisoformat(timing["report_generated_at"]).time() < time(9, 30),
        freeze_sha=bool(digest) and run.get("packet_sha256") == digest,
        post_open_independent=bool(snapshots) and post.get("auction_packet_sha256") == digest,
        post_open_0935=any(time(9, 35) <= t < time(9, 37) for t in observed),
        post_open_1000=any(time(10) <= t < time(10, 1) for t in observed),
        eod=eod.get("status") == "PASS",
    )
    status = "READY" if all(checks.values()) else "PARTIALLY_READY" if schema_ok else "NOT_READY"
    return dict(
        trade_date=str(day),
        status=status,
        live_acceptance="PASS" if status == "READY" else "LIVE_ACCEPTANCE_PENDING",
        checks=checks,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    args = parser.parse_args()
    result = validate(ROOT, date.fromisoformat(args.date))
    write(ROOT / "data/auction_acceptance" / f"{args.date}.json", result)
    print(json.dumps(result))
    raise SystemExit(0 if result["status"] == "READY" else 2)
