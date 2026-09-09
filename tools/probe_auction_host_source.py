"""Five-stock transport diagnostic; never writes auction facts or packets."""

# ruff: noqa: BLE001
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.auction.eltdx_source import EltdxAuctionSource
from src.auction.production import write


def probe(source_factory=EltdxAuctionSource):
    source = source_factory()
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    result = {
        "observed_at": now.isoformat(),
        "scope": "TRANSPORT_DIAGNOSTIC_NOT_LIVE_ACCEPTANCE",
        "connect_result": "FAIL",
        "requests": [],
    }
    start = time.perf_counter()
    try:
        source.connect()
        result.update(
            connect_result="PASS", connect_latency_ms=round((time.perf_counter() - start) * 1000, 3)
        )
        codes = ["000001", "000333", "300750", "600519", "601318"]
        for code in codes:
            for kind, operation in (
                ("quote", lambda c=code: source.client.quotes.get_snapshots([c])),
                ("process", lambda c=code: source.client.auctions.series(c)),
                (
                    "formal_match",
                    lambda c=code: source.client.trades.opening_match_today(c, max_pages=4),
                ),
            ):
                started = time.perf_counter()
                try:
                    value = operation()
                    if kind == "process":
                        count = len(getattr(value, "points", ()))
                    elif kind == "formal_match":
                        count = int(
                            value is not None
                            and getattr(value, "event_kind", None) == "opening_match"
                        )
                    else:
                        count = len(value) if hasattr(value, "__len__") else 0
                    result["requests"].append(
                        {
                            "code": code,
                            "interface": kind,
                            "status": "PASS" if count else "EMPTY",
                            "row_count": count,
                            "latency_ms": round((time.perf_counter() - started) * 1000, 3),
                        }
                    )
                except Exception as exc:
                    result["requests"].append(
                        {
                            "code": code,
                            "interface": kind,
                            "status": "FAIL",
                            "error_type": type(exc).__name__,
                            "error": str(exc)[:300],
                            "latency_ms": round((time.perf_counter() - started) * 1000, 3),
                        }
                    )
    except Exception as exc:
        result.update(
            connect_latency_ms=round((time.perf_counter() - start) * 1000, 3),
            error_type=type(exc).__name__,
            error=str(exc)[:300],
        )
    finally:
        source.close()
    result["success_count"] = sum(row["status"] == "PASS" for row in result["requests"])
    result["failure_count"] = sum(row["status"] != "PASS" for row in result["requests"])
    result["timeout_count"] = sum(
        "timeout" in (row.get("error_type", "") + row.get("error", "")).lower()
        for row in result["requests"]
    )
    return result


if __name__ == "__main__":
    result = probe()
    path = (
        ROOT
        / "data/auction_host_audit"
        / datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y%m%d-%H%M%S")
        / "source_probe.json"
    )
    write(path, result)
    print(json.dumps(result, ensure_ascii=False))
