"""Bounded public-source retrieval and conservative reuse of archived disclosures."""
from datetime import datetime
import hashlib
import json
from urllib.parse import urlparse

import requests

from src.market_packet.source_router import SourceRouter
from src.opportunity_radar.contracts import SHANGHAI, number
from src.opportunity_radar.storage import archive_json

DISCLOSURE_TYPES = {
    "order": "CUSTOMER_AND_ORDER", "contract": "CUSTOMER_AND_ORDER", "customer": "CUSTOMER_AND_ORDER",
    "earnings": "REVENUE_PROFIT_MARGIN", "product": "PRODUCT_COMMERCIALIZATION",
    "capacity": "CAPACITY_AND_UTILIZATION", "restructuring": "M&A_AND_CAPITAL_OPERATION",
    "buyback": "SHAREHOLDER_MANAGEMENT_ACTION", "increase_holding": "SHAREHOLDER_MANAGEMENT_ACTION",
    "decrease_holding": "SHAREHOLDER_MANAGEMENT_ACTION",
}


def tier(url, declared=None):
    host = (urlparse(url or "").hostname or "").lower()
    official = ("gov.cn", "cninfo.com.cn", "sse.com.cn", "szse.cn", "bse.cn", "pbc.gov.cn")
    if any(host == d or host.endswith("." + d) for d in official):
        return 1
    if declared == "reputable_media_with_original":
        return 2
    if declared in ("structured_market_data", "third_party", "broker"):
        return 3
    return 4


def archived_disclosures(root):
    rows, manifest = [], []
    for path in sorted((root / "data/market_packets").glob("????-??-??.json")):
        packet = json.loads(path.read_text(encoding="utf-8"))
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        rel = path.relative_to(root).as_posix()
        count = 0
        for section in ("announcements", "policies"):
            records = packet.get(section, {})
            records = records.get("records", []) if isinstance(records, dict) else records
            for r in records:
                category = "POLICY_AND_FISCAL" if section == "policies" else DISCLOSURE_TYPES.get(r.get("category"))
                seen = r.get("first_seen_at") or r.get("retrieved_at")
                published = r.get("published_at")
                if not category or not seen or not published:
                    continue
                # Existing summary/confirmed_fact can be title-derived, so never promote it.
                facts = {"stock_code": r.get("stock_code"), "stock_name": r.get("stock_name"),
                         "contract_amount": number(r.get("contract_amount")), "revenue_yoy": number(r.get("revenue_yoy")),
                         "profit_yoy": number(r.get("net_profit_yoy")), "title": r.get("title")}
                rows.append({"signal_type": category, "entity": r.get("stock_code") or r.get("agency") or r.get("title"),
                             "stock_code": r.get("stock_code"), "stock_name": r.get("stock_name"),
                             "theme": None, "metric": "disclosure", "value": None, "facts": facts,
                             "title": r.get("title"), "event_date": str(published)[:10], "published_at": published,
                             "first_seen_at": seen, "effective_date": None, "source_date": str(published)[:10],
                             "source": r.get("source") or r.get("agency"), "source_tier": tier(r.get("url")),
                             "url": r.get("url"), "source_path": rel, "provenance": {"sha256": sha, "kind": "ARCHIVED_DISCLOSURE_METADATA"}})
                count += 1
        if packet.get("data_quality", {}).get("status") in {"PASS", "PARTIAL"}:
            day = packet["meta"]["trade_date"]
            seen = packet["meta"].get("generated_at")
            benchmark = next((number(i.get("change_pct")) for i in packet.get("indices", []) if i.get("code") == "000001.SH"), None)
            for section in ("industries", "themes"):
                for item in packet.get(section, []):
                    name = item.get("theme_name") or item.get("industry_name")
                    value = number(item.get("amount"))
                    if not name or value is None or not seen or item.get("quality") not in {"PASS", "PARTIAL"}:
                        continue
                    rows.append({"signal_type": "MARKET_STRUCTURE_AND_FLOW", "entity": name, "theme": name,
                                 "metric": "board_amount", "value": value, "unit": "CNY", "currency": "CNY",
                                 "facts": {"amount": value, "return_1d": number(item.get("change_pct")),
                                           "rise_count": item.get("rise_count"), "fall_count": item.get("fall_count"),
                                           "benchmark_return_1d": benchmark,
                                           "limit_up_count": item.get("limit_up_count")},
                                 "event_date": day, "source_date": day, "effective_date": day,
                                 "published_at": None, "first_seen_at": seen,
                                 "source": item.get("source") or "MarketPacket", "source_tier": 3,
                                 "source_path": rel, "provenance": {"sha256": sha, "kind": "ARCHIVED_MARKET_FACT"}})
                    count += 1
        if count:
            manifest.append({"path": rel, "sha256": sha, "record_count": count, "status": "PARTIAL_TITLE_ONLY_NOT_HARD_EVIDENCE"})
    return rows, manifest


def fetch_series(root, start, end, *, session=None):
    router = SourceRouter(root / "config/opportunity_radar_sources.json")
    session = session or requests.Session()
    rows, receipts = [], []
    for name in router.datasets:
        route = router.route(name)
        fetched = datetime.now(SHANGHAI).isoformat()
        try:
            response = session.get(route["url"], params=route.get("params"), timeout=(5, 20))
            response.raise_for_status()
            if route["format"] == "sina_jsonp":
                text = response.text
                payload = json.loads(text[text.index("([") + 1:text.rindex("])") + 1])
                values = [(str(r["d"])[:10], number(r["c"])) for r in payload]
            else:
                payload = response.json()
                values = [(str(r["REPORT_DATE"])[:10], number(r["INDICATOR_VALUE"])) for r in payload["result"]["data"]]
            values = [(day, value) for day, value in values if start.isoformat() <= day <= end.isoformat() and value is not None]
            if not values:
                raise ValueError("EMPTY_SERIES")
            fetched = datetime.now(SHANGHAI).isoformat()
            raw = {"source": route["source"], "url": route["url"], "retrieved_at": fetched, "payload": payload}
            path = archive_json(root, name, raw)
            sha = hashlib.sha256(path.read_bytes()).hexdigest()
            for day, value in values:
                rows.append({"signal_type": "COMMODITY_PRICE", "entity": name, "theme": route["theme"],
                             "metric": route["metric"], "value": value, "unit": route["unit"], "currency": route.get("currency"),
                             "facts": {"instrument": name, "category": route["instrument_type"], "unit": route["unit"],
                                       "currency": route.get("currency"), "latest_value": value,
                                       "series_caveat": route["caveat"]},
                             "event_date": day, "source_date": day, "published_at": None, "first_seen_at": fetched,
                             "effective_date": day, "source": route["source"], "source_tier": 3,
                             "url": route["url"], "source_path": path.relative_to(root).as_posix(),
                             "provenance": {"sha256": sha, "kind": "FETCHED_SERIES_NOT_HISTORICAL_FIRST_SEEN"}})
            receipts.append({"source": name, "status": "PARTIAL", "rows": len(values), "fetched_at": fetched,
                             "path": path.relative_to(root).as_posix(), "sha256": sha,
                             "gap": "PUBLICATION_TIMESTAMP_UNAVAILABLE; backfilled series excluded from earlier as-of replay"})
        except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
            receipts.append({"source": name, "status": "UNAVAILABLE", "fetched_at": fetched, "error_type": type(exc).__name__})
    return rows, receipts
