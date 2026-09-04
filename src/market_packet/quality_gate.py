from __future__ import annotations

from collections import defaultdict
from typing import Any

from src.market_packet.collector import CollectedDataset


QUALITY_VALUES = {"PASS": 100, "EMPTY_VALID": 100, "PARTIAL": 55, "STALE": 25, "UNAVAILABLE": 0, "FAIL": 0, "INVALID": 0}
DOMAIN_WEIGHTS = {"market_core": 35, "sector_theme": 20, "announcements": 15, "policies": 15, "capital_flow": 10, "continuity_audit": 5}


def audit_packet(packet: dict[str, Any], datasets: dict[str, CollectedDataset]) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    missing = set(packet.get("missing_data", []))

    def add(domain: str, item: str, status: str, source: str | None, detail: str, *, missing_key: str | None = None, hard_gate: bool = False) -> None:
        checks.append({"domain": domain, "item": item, "status": status, "source": source, "detail": detail, "hard_gate": hard_gate})
        if status in {"FAIL", "INVALID", "UNAVAILABLE", "STALE"} and missing_key:
            missing.add(missing_key)

    trading_status = "PASS" if packet.get("market_overview", {}).get("is_trading_day") else "FAIL"
    add("market_core", "交易日判断", trading_status, _source(datasets, "tushare_trade_cal"), "目标日期交易状态", missing_key="trading_day", hard_gate=True)
    daily = datasets.get("tushare_daily_all")
    add("market_core", "全市场日线", "PASS" if daily and daily.rows else "FAIL", daily.source if daily else None, f"rows={len(daily.rows) if daily else 0}", missing_key="full_market_daily", hard_gate=True)
    turnover = packet.get("liquidity", {}).get("total_market_turnover")
    add("market_core", "成交额", "PASS" if turnover is not None else "FAIL", "tushare.daily" if turnover is not None else None, f"value={turnover}", missing_key="total_market_turnover", hard_gate=True)
    breadth = packet.get("market_breadth", {})
    breadth_ok = all(breadth.get(key) is not None for key in ("rise_count", "fall_count"))
    add("market_core", "上涨下跌家数", "PASS" if breadth_ok else "FAIL", breadth.get("source"), f"rise={breadth.get('rise_count')} fall={breadth.get('fall_count')}", missing_key="market_breadth", hard_gate=True)
    indices = packet.get("indices", [])
    valid_indices = sum(1 for item in indices if item.get("quality") == "PASS" and item.get("close") is not None)
    index_status = "PASS" if valid_indices >= 3 else "PARTIAL" if valid_indices else "FAIL"
    add("market_core", "主要指数", index_status, "akshare.stock_zh_index_daily", f"valid={valid_indices}/{len(indices)}", missing_key="indices", hard_gate=True)
    limit_parts = [datasets.get(name) for name in ("limit_up", "failed_limit", "limit_down")]
    limit_failed = [item for item in limit_parts if item is None or item.quality in {"FAIL", "INVALID", "STALE"}]
    add("market_core", "涨跌停", "FAIL" if limit_failed else "PASS", "Eastmoney/AKShare", "/".join(f"{x.name}:{x.quality}" for x in limit_parts if x), missing_key="limit_pools", hard_gate=True)
    previous = datasets.get("previous_limit")
    dragon = datasets.get("dragon_tiger_daily")
    add("market_core", "昨日涨停反馈", previous.quality if previous else "FAIL", previous.source if previous else None, f"rows={len(previous.rows) if previous else 0}")
    add("market_core", "龙虎榜日明细", dragon.quality if dragon else "FAIL", dragon.source if dragon else None, f"rows={len(dragon.rows) if dragon else 0}")

    industry = datasets.get("industry_board_daily")
    concept = datasets.get("concept_board_daily")
    add("sector_theme", "行业数据", _section_status(packet.get("industries", []), industry, 30), industry.source if industry else None, f"rows={len(packet.get('industries', []))}", missing_key="industries")
    add("sector_theme", "题材数据", _section_status(packet.get("themes", []), concept, 50), concept.source if concept else None, f"rows={len(packet.get('themes', []))}", missing_key="themes")
    announcements = packet.get("announcements", {})
    ann_records, ann_meta = _section_records_meta(announcements)
    ann_dataset = datasets.get("official_announcements")
    ann_status = ann_meta.get("quality") or (ann_dataset.quality if ann_dataset else "FAIL")
    add("announcements", "公告", ann_status, _source(datasets, "official_announcements"), f"coverage={ann_meta.get('coverage_rate')} records={len(ann_records)}", missing_key="announcements")
    policies = packet.get("policies", {})
    policy_records, policy_meta = _section_records_meta(policies)
    policy_dataset = datasets.get("official_policies")
    policy_status = policy_meta.get("quality") or (policy_dataset.quality if policy_dataset else "FAIL")
    add("policies", "政策", policy_status, _source(datasets, "official_policies"), f"records={len(policy_records)} rejected={policy_meta.get('rejected_count', 0)}", missing_key="policies")

    capital = packet.get("capital_flow", {})
    northbound = capital.get("northbound", {})
    add("capital_flow", "北向资金", northbound.get("quality", "UNAVAILABLE"), northbound.get("source"), northbound.get("reason") or "关键金额字段校验", missing_key="northbound")
    margin = capital.get("margin", {})
    add("capital_flow", "两融", margin.get("quality", "FAIL"), margin.get("source"), "沪深两市覆盖检查", missing_key="margin")
    contamination = _contamination_items(packet)
    add("continuity_audit", "历史连续性", "INVALID" if contamination else "PASS", "packet_as_of_guard", ",".join(contamination) if contamination else "no cross-date/current-only pollution")
    conflicts = detect_conflicts(packet)
    severe = [item for item in conflicts if item.get("severity") == "critical" and not item.get("resolution")]
    add("continuity_audit", "多源冲突", "FAIL" if severe else "PASS", "conflict_detector", f"conflicts={len(conflicts)} severe_unresolved={len(severe)}")

    domains = _domain_scores(checks)
    score = round(sum(domains[name]["score"] * weight for name, weight in DOMAIN_WEIGHTS.items()) / 100)
    hard_fail = any(item["hard_gate"] and item["status"] not in {"PASS", "EMPTY_VALID"} for item in checks)
    if hard_fail:
        score = min(score, 69)
    invalid_items = [item["item"] for item in checks if item["status"] == "INVALID"]
    if contamination or invalid_items:
        status, score = "INVALID", 0
    elif hard_fail:
        status = "FAIL"
    elif score >= 85:
        status = "PASS"
    elif score >= 60:
        status = "PARTIAL"
    else:
        status = "FAIL"

    packet["missing_data"] = sorted(missing)
    packet["data_quality"] = {
        "status": status, "score": score, "checks": checks,
        "sources": [_source_meta(item) for item in datasets.values()], "conflicts": conflicts, "domains": domains,
        "invalid_items": sorted(set(invalid_items + contamination)),
        "stale_items": [item["item"] for item in checks if item["status"] == "STALE"],
        "unavailable_items": [item["item"] for item in checks if item["status"] == "UNAVAILABLE"],
        "conflict_count": len(conflicts),
    }
    return packet


def detect_conflicts(packet: dict[str, Any]) -> list[dict[str, Any]]:
    conflicts: list[dict[str, Any]] = []
    announcement_records, _ = _section_records_meta(packet.get("announcements", {}))
    policy_records, _ = _section_records_meta(packet.get("policies", {}))
    _duplicate_conflicts(conflicts, announcement_records, "announcement", ("stock_code", "normalized_title"), "published_at")
    _duplicate_conflicts(conflicts, policy_records, "policy", ("normalized_title",), "published_at")
    return conflicts


def _duplicate_conflicts(target: list[dict[str, Any]], rows: list[dict[str, Any]], field: str, key_fields: tuple[str, ...], value_field: str) -> None:
    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[tuple(row.get(key) for key in key_fields)].append(row)
    for key, items in grouped.items():
        values = {str(item.get(value_field)) for item in items}
        if len(values) <= 1:
            continue
        a = items[0]
        b = next(item for item in items[1:] if str(item.get(value_field)) != str(a.get(value_field)))
        target.append({"field": f"{field}.{value_field}", "entity_key": "|".join(str(x) for x in key), "source_a": a.get("source") or a.get("agency"), "value_a": a.get(value_field), "source_b": b.get("source") or b.get("agency"), "value_b": b.get(value_field), "difference": "value_mismatch", "severity": "critical", "resolution": None, "selected_source": None})


def _contamination_items(packet: dict[str, Any]) -> list[str]:
    result: list[str] = []
    policies = packet.get("policies", {})
    policy_meta = policies.get("metadata", {}) if isinstance(policies, dict) else {}
    if policy_meta.get("invalid_reasons"):
        result.append("policy_pollution")
    announcements = packet.get("announcements", {})
    announcement_records = announcements.get("records", []) if isinstance(announcements, dict) else announcements
    if any(item.get("pollution_status") == "future" for item in announcement_records):
        result.append("announcement_future_pollution")
    if packet.get("capital_flow", {}).get("historical_current_only_pollution"):
        result.append("current_only_history_pollution")
    return result


def _section_records_meta(value: Any) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if isinstance(value, dict):
        return value.get("records", []), value.get("metadata", {})
    if isinstance(value, list):
        return value, {}
    return [], {}


def _section_status(rows: list[dict[str, Any]], dataset: CollectedDataset | None, threshold: int) -> str:
    if dataset and dataset.quality in {"FAIL", "INVALID", "STALE", "UNAVAILABLE"}:
        return dataset.quality
    complete = len(rows) >= threshold and any(item.get("change_pct") is not None for item in rows)
    return "PASS" if complete else "PARTIAL" if rows else "FAIL"


def _domain_scores(checks: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for domain, weight in DOMAIN_WEIGHTS.items():
        statuses = [item["status"] for item in checks if item["domain"] == domain]
        score = round(sum(QUALITY_VALUES.get(status, 0) for status in statuses) / len(statuses)) if statuses else 0
        result[domain] = {"score": score, "weight": weight, "status": _domain_status(statuses, score)}
    return result


def _domain_status(statuses: list[str], score: int) -> str:
    if "INVALID" in statuses:
        return "INVALID"
    if statuses and all(status == "EMPTY_VALID" for status in statuses):
        return "EMPTY_VALID"
    if statuses and all(status == "UNAVAILABLE" for status in statuses):
        return "UNAVAILABLE"
    if "FAIL" in statuses or score < 60:
        return "FAIL"
    return "PASS" if score >= 85 else "PARTIAL"


def _source(datasets: dict[str, CollectedDataset], name: str) -> str | None:
    item = datasets.get(name)
    return item.source if item else None


def _source_meta(item: CollectedDataset) -> dict[str, Any]:
    return {"source": item.source, "dataset": item.name, "retrieved_at": item.retrieved_at.isoformat(), "data_date": item.data_date.isoformat() if item.data_date else None, "freshness": item.freshness, "quality": item.quality, "is_cached": item.is_cached, "path": item.path, "error": item.error, "record_count": len(item.rows), "cache_created_at": item.cache_created_at.isoformat() if item.cache_created_at else None, "last_attempt_at": item.last_attempt_at.isoformat() if item.last_attempt_at else None, "error_type": item.error_type, "retry_after": item.retry_after.isoformat() if item.retry_after else None}
