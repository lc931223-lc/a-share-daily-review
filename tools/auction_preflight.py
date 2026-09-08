from pathlib import Path
import argparse
import json
import platform
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.auction.eltdx_source import EltdxAuctionSource
from src.auction.previous_context import load_previous_context
from src.auction.production import write
from src.market_packet.trading_calendar import load_trading_calendar


def preflight(root=ROOT, *, now=None, source_factory=EltdxAuctionSource):
    now = now or datetime.now(ZoneInfo("Asia/Shanghai"))
    day = now.date()
    days = load_trading_calendar(day, cache_root=root / "data/reference")
    result = dict(
        trade_date=str(day),
        python=platform.python_version(),
        platform=platform.system(),
        started_at=now.isoformat(),
    )
    if not any(d.cal_date == day and d.is_open for d in days):
        result["status"] = "SKIPPED_NON_TRADING_DAY"
        return result
    previous = load_previous_context(root, day, days)
    result.update(
        previous_trade_date=previous["previous_trade_date"],
        previous_review_status="READY" if previous["official_review_loaded"] else "MISSING",
        review_context=previous["review_context_loaded"],
        market_packet=previous["market_packet_loaded"],
        report_status=previous["report_status"],
    )
    source = source_factory()
    try:
        source.connect()
        result["source_health"] = "CONNECTED_NOT_LIVE_ACCEPTED"
    except Exception as exc:
        result["source_health"] = "FAIL"
        result["source_error"] = type(exc).__name__
    finally:
        source.close()
    result["status"] = "PASS" if result["source_health"] != "FAIL" else "FAIL"
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-only", action="store_true")
    args = parser.parse_args()
    if args.source_only:
        source = EltdxAuctionSource()
        try:
            source.connect()
            result = dict(
                status="PASS",
                platform=platform.system(),
                scope="CONNECTION_ONLY_NOT_LIVE_ACCEPTANCE",
            )
        except Exception as exc:
            result = dict(status="FAIL", platform=platform.system(), error_type=type(exc).__name__)
        finally:
            source.close()
    else:
        result = preflight()
    write(
        ROOT / "data/auction_preflight" / f"{datetime.now(ZoneInfo('Asia/Shanghai')).date()}.json",
        result,
    )
    print(json.dumps(result))
    raise SystemExit(1 if result["status"] == "FAIL" else 0)
