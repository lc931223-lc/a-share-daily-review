"""Traceable evidence nodes, not explanations of price action."""

from datetime import datetime
from urllib.parse import urlparse
from zoneinfo import ZoneInfo
import hashlib
import json
import math

from src.domain.constants import DRIVER_TYPES

OFFICIAL_DOMAINS = ("cninfo.com.cn", "sse.com.cn", "szse.cn", "bse.cn", "gov.cn", "pbc.gov.cn")
FACTORS = {
    "order": 19,
    "contract": 19,
    "customer": 31,
    "earnings": 23,
    "product": 13,
    "restructuring": 27,
    "buyback": 30,
    "increase_holding": 30,
}
FACT_TYPES = {
    "order": "order_confirmation",
    "contract": "order_confirmation",
    "customer": "customer_validation",
    "product": "product_validation",
    "capacity": "capacity_expansion",
    "earnings": "earnings_disclosure",
}
NODE_TYPES = {
    "price_change",
    "policy_release",
    "order_confirmation",
    "shipment_confirmation",
    "revenue_growth",
    "margin_change",
    "profit_growth",
    "capacity_expansion",
    "customer_validation",
    "product_validation",
    "industry_inventory",
    "industry_utilization",
    "overseas_peer_move",
    "cross_market_move",
    "capital_flow_change",
}
REALIZATIONS = {
    "policy_release": "POLICY_ONLY",
    "product_validation": "PRODUCT_VALIDATION",
    "customer_validation": "CUSTOMER_VALIDATION",
    "price_change": "PRICE_CHANGE",
    "order_confirmation": "ORDER_CONFIRMED",
    "shipment_confirmation": "SHIPMENT_CONFIRMED",
    "revenue_growth": "REVENUE_CONFIRMED",
    "margin_change": "MARGIN_CONFIRMED",
    "profit_growth": "PROFIT_CONFIRMED",
    "market_price": "MARKET_ONLY",
}


def number(value):
    if isinstance(value, bool):
        return None
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def available_at(value, day):
    if not value:
        return False
    try:
        stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if stamp.tzinfo:
            stamp = stamp.astimezone(ZoneInfo("Asia/Shanghai"))
        return stamp.date().isoformat() <= str(day)
    except ValueError:
        return False


def source_tier(row):
    host = (urlparse(str(row.get("url") or "")).hostname or "").lower()
    if (row.get("is_official") or row.get("source_type") == "official") and any(
        host == domain or host.endswith("." + domain) for domain in OFFICIAL_DOMAINS
    ):
        return 1
    kind = row.get("source_type")
    if kind == "reputable_media" and row.get("original_source_url"):
        return 2
    if kind in {"broker", "industry_research", "third_party", "objective_calculation"}:
        return 3
    return 4


def evidence_nodes(market, day, gaps):
    stocks = {str(s.get("stock_code", "")).split(".")[0]: s for s in market.get("stocks", [])}
    output = {}
    for section in ("announcements", "policies", "industry_events"):
        data = market.get(section) or {}
        rows = data if isinstance(data, list) else data.get("records", [])
        for row in rows:
            stamp = row.get("published_at") or row.get("source_date")
            if not available_at(stamp, day):
                gaps.append({"field": section, "reason": "UNDATED_OR_FUTURE_EVIDENCE_EXCLUDED"})
                continue
            tier = source_tier(row)
            code = str(row.get("stock_code") or "").split(".")[0]
            themes = sorted(
                set(row.get("related_themes") or stocks.get(code, {}).get("themes") or [])
            )
            category = row.get("category")
            fact_type = (
                "policy_release"
                if section == "policies"
                else FACT_TYPES.get(category, "disclosure")
            )
            flags = list(row.get("clarification_flags") or []) + list(row.get("risk_flags") or [])
            uncertain = bool(row.get("uncertainty_flag") or row.get("clarification_flags"))
            value = {
                key: row.get(key)
                for key in (
                    "title",
                    "contract_amount",
                    "revenue",
                    "revenue_yoy",
                    "net_profit",
                    "net_profit_yoy",
                    "customer_name",
                    "revenue_ratio_if_disclosed",
                )
                if row.get(key) is not None
            }
            # A disclosure title is not an extracted operating fact, even on an official site.
            observed = fact_type == "policy_release" and tier == 1
            if fact_type == "order_confirmation":
                observed = (
                    tier == 1 and (number(row.get("contract_amount")) or 0) > 0 and not uncertain
                )
            # Already-structured operating measurements can be reused without
            # inferring them from a category or a headline.
            if row.get("fact_type") in NODE_TYPES:
                fact_type = row["fact_type"]
                measured = number(row.get("value"))
                value["measurement"] = measured
                value["unit"] = row.get("unit")
                observed = (
                    tier == 1 and measured is not None and bool(row.get("unit")) and not uncertain
                )
                if fact_type in {
                    "order_confirmation",
                    "shipment_confirmation",
                    "revenue_growth",
                    "profit_growth",
                }:
                    observed = observed and measured > 0
            candidates = [
                (fact_type, observed, FACTORS.get(category) if section != "policies" else 5)
            ]
            if category == "earnings" and tier == 1 and not uncertain:
                for field, kind, factor in (
                    ("revenue_yoy", "revenue_growth", 23),
                    ("net_profit_yoy", "profit_growth", 26),
                ):
                    if (number(row.get(field)) or 0) > 0:
                        candidates.append((kind, True, factor))
            for kind, observed, factor in candidates:
                node = dict(
                    fact_type=kind,
                    status="OBSERVED" if observed else "DISCLOSED_UNVERIFIED",
                    date=str(stamp),
                    value=value,
                    source=row.get("source") or row.get("agency"),
                    url=row.get("url"),
                    source_type=row.get("source_type") or "unknown",
                    tier=tier,
                    related_theme=themes,
                    related_company=code or None,
                    factor_id=factor,
                    risk_flags=flags,
                )
                identity = [kind, node["url"], node["date"], code, value]
                node["evidence_id"] = hashlib.sha256(
                    json.dumps(identity, sort_keys=True, ensure_ascii=False).encode()
                ).hexdigest()[:20]
                output[node["evidence_id"]] = node
    return sorted(output.values(), key=lambda n: n["evidence_id"])


def factor_evidence(nodes):
    result = []
    for fid, name in DRIVER_TYPES.items():
        linked = [node for node in nodes if node["factor_id"] == fid]
        # Mapping is partial: an order does not establish a large or unexpected order;
        # reported growth does not establish an earnings surprise.
        result.append(
            dict(
                factor_id=fid,
                factor_name=name,
                evidence_status="PARTIAL_EVIDENCE" if linked else "DATA_UNAVAILABLE",
                evidence=[n["evidence_id"] for n in linked],
                source_type=sorted({n["source_type"] for n in linked}),
                source_date=sorted({n["date"] for n in linked}),
                tier=min((n["tier"] for n in linked), default=None),
                confidence="SOURCE_ONLY" if linked else "NONE",
                data_available=bool(linked),
            )
        )
    return result


def realization_facts(nodes):
    return [
        dict(
            evidence_id=n["evidence_id"],
            related_theme=n["related_theme"],
            related_company=n["related_company"],
            fact_level=REALIZATIONS.get(n["fact_type"], "UNKNOWN")
            if n["status"] == "OBSERVED" and n["tier"] <= 3
            else "UNKNOWN",
        )
        for n in nodes
    ]
