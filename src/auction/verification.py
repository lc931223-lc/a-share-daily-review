from __future__ import annotations

import statistics
from collections import defaultdict
from typing import Any


def build_sector_breadth(
    watchlist: dict[str, Any],
    summaries: list[dict[str, Any]],
    previous_context: dict[str, Any],
) -> list[dict[str, Any]]:
    watch = {str(row.get("ts_code")): row for row in watchlist.get("stocks") or []}
    prior = {str(row.get("ts_code")): row for row in previous_context.get("stocks") or []}
    prior_themes = {
        str(row.get("mainline_name")): row for row in previous_context.get("mainlines") or []
    }
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for summary in summaries:
        stock = watch.get(str(summary.get("ts_code")), {})
        themes = stock.get("themes") or (
            [prior.get(str(summary.get("ts_code")), {}).get("theme")]
            if prior.get(str(summary.get("ts_code")), {}).get("theme")
            else []
        )
        for theme in themes:
            buckets[str(theme)].append(summary)
    rows = []
    for name, items in buckets.items():
        gaps = [
            float(row["auction_gap_pct"]) for row in items if row.get("auction_gap_pct") is not None
        ]
        post_changes = [
            float(row["price_change_0920_0925_pct"])
            for row in items
            if row.get("price_change_0920_0925_pct") is not None
        ]
        order_changes = [
            float(row["post_0920_order_growth"])
            for row in items
            if row.get("post_0920_order_growth") is not None
        ]
        roles = defaultdict(list)
        for row in items:
            role = str(prior.get(str(row.get("ts_code")), {}).get("role") or "").lower()
            roles[_role(role)].append(_stock_strength(row))
        result = {
            "name": name,
            "previous_mainline_score": (prior_themes.get(name) or {}).get("mainline_score"),
            "previous_lifecycle": (prior_themes.get(name) or {}).get("lifecycle"),
            "watchlist_count": len(items),
            "valid_count": len(gaps),
            "high_open_count": sum(value > 0 for value in gaps),
            "low_open_count": sum(value < 0 for value in gaps),
            "above_3pct_count": sum(value >= 3 for value in gaps),
            "above_5pct_count": sum(value >= 5 for value in gaps),
            "near_limit_up_count": sum(value >= 8.5 for value in gaps),
            "positive_gap_ratio": sum(value > 0 for value in gaps) / len(gaps) if gaps else None,
            "post_0920_positive_ratio": sum(value >= 0 for value in post_changes)
            / len(post_changes)
            if post_changes
            else None,
            "leader_strength": _mean(roles["leader"]),
            "capacity_strength": _mean(roles["capacity"]),
            "zhongjun_strength": _mean(roles["capacity"]),
            "catch_up_strength": _mean(roles["catch_up"]),
            "trend_core_strength": _mean(roles["trend_core"]),
            "auction_amount": sum(
                float(row["auction_amount"])
                for row in items
                if row.get("auction_amount") is not None
            ),
            "auction_amount_change": _mean([row.get("auction_amount_ratio_20d") for row in items]),
            "post_0920_order_growth": _mean(order_changes),
            "post_0920_order_status": (
                "UNMATCHED_MAGNITUDE_INCREASING_DIRECTION_UNAVAILABLE"
                if order_changes and statistics.fmean(order_changes) > 0.05
                else "UNMATCHED_MAGNITUDE_DECAYING_DIRECTION_UNAVAILABLE"
                if order_changes and statistics.fmean(order_changes) < -0.05
                else "STABLE"
                if order_changes
                else "UNAVAILABLE"
            ),
        }
        result["structure_status"] = _structure_status(result)
        rows.append(result)
    rows.sort(
        key=lambda row: (
            -(row.get("positive_gap_ratio") or -1),
            -(row.get("auction_amount") or 0),
            row["name"],
        )
    )
    for rank, row in enumerate(rows, 1):
        row["rank"] = rank
    return rows


def validate_tomorrow_checks(
    previous_context: dict[str, Any],
    summaries: list[dict[str, Any]],
    sectors: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_code = {str(row.get("ts_code")): row for row in summaries}
    by_name = {str(row.get("stock_name")): row for row in summaries}
    by_sector = {str(row.get("name")): row for row in sectors}
    results = []
    for check in previous_context.get("tomorrow_checks") or []:
        entity_type = str(check.get("entity_type") or "").lower()
        key = str(check.get("entity_key") or "")
        description = str(check.get("description") or "")
        evidence = None
        if entity_type == "theme":
            evidence = by_sector.get(key)
        elif entity_type == "stock":
            evidence = by_code.get(_with_suffix(key)) or by_name.get(key)
        status, reason = _check_status(entity_type, description, evidence)
        results.append(
            {
                "previous_judgement": description,
                "entity_type": entity_type,
                "entity_key": key,
                "today_auction_evidence": evidence,
                "validation_status": status,
                "reason": reason,
                "validation_scope": "MARKET_FUND_VALIDATION_ONLY",
            }
        )
    return results


def lifecycle_transitions(previous_context: dict[str, Any], sectors: list[dict[str, Any]]):
    by_name = {str(row.get("name")): row for row in sectors}
    rows = []
    for theme in previous_context.get("mainlines") or []:
        current = by_name.get(str(theme.get("mainline_name")))
        previous = theme.get("lifecycle")
        candidate = None
        if current:
            strong = (current.get("positive_gap_ratio") or 0) >= 0.67 and current.get(
                "structure_status"
            ) in {"LEADER_CAPACITY_RESONANCE", "FULL_SECTOR_RESONANCE", "LEADER_CATCH_UP"}
            weak = (current.get("positive_gap_ratio") or 1) <= 0.33 or current.get(
                "structure_status"
            ) == "HIGH_OPEN_REVERSAL_RISK"
            if strong and previous in {"启动", "朦胧期", "发酵", "发酵期"}:
                candidate = "发酵→加速候选"
            elif weak and previous in {"加速", "主升期", "扩散期"}:
                candidate = "加速→分歧候选"
            elif strong and previous in {"退潮", "兑现期"}:
                candidate = "退潮→修复候选"
        rows.append(
            {
                "theme": theme.get("mainline_name"),
                "previous_lifecycle": previous,
                "candidate_transition": candidate,
                "auction_evidence": current,
                "final_confirmation_owner": "close_review",
            }
        )
    return rows


def stock_state_machine(previous_context, summaries, sectors):
    prior = {str(row.get("ts_code")): row for row in previous_context.get("stocks") or []}
    sector_map = {str(row.get("name")): row for row in sectors}
    rows = []
    for summary in summaries:
        old = prior.get(str(summary.get("ts_code")), {})
        yesterday = old.get("yesterday_signals") or {}
        role = _role(str(old.get("role") or "").lower())
        sector = sector_map.get(str(old.get("theme") or ""), {})
        gap = summary.get("auction_gap_pct")
        order_growth = summary.get("post_0920_order_growth")
        directional_order_growth = (
            order_growth if summary.get("unmatched_direction") in {"buy", "sell"} else None
        )
        percentile = summary.get("auction_amount_percentile_20d") or summary.get(
            "auction_amount_percentile_60d"
        )
        sync = sector.get("positive_gap_ratio")
        strong = (
            gap is not None
            and gap >= 1
            and percentile is not None
            and percentile >= 60
            and (directional_order_growth is None or directional_order_growth >= 0)
            and (sync is None or sync >= 0.5)
        )
        weak = (
            gap is not None
            and gap < 0
            and (directional_order_growth is None or directional_order_growth < 0)
            and (sync is None or sync < 0.5)
        )
        prior_strong = role in {"leader", "capacity", "trend_core"} or yesterday.get(
            "limit_up"
        ) is True
        prior_weak = any(
            yesterday.get(key) is True
            for key in ("failed_limit_up", "intraday_pullback", "late_pullback", "big_bearish")
        )
        if prior_weak and role not in {"leader", "capacity", "trend_core"}:
            prior_strong = False
        state = (
            "strong_to_stronger"
            if prior_strong and strong
            else "strong_to_weak"
            if prior_strong and weak
            else "weak_to_strong"
            if not prior_strong and strong
            else "weak_to_weaker"
            if not prior_strong and weak
            else "neutral"
        )
        reason_codes = []
        if yesterday.get("limit_up") is True:
            reason_codes.append("PREVIOUS_LIMIT_UP")
        if yesterday.get("failed_limit_up") is True:
            reason_codes.append("PREVIOUS_FAILED_LIMIT_UP")
        if yesterday.get("intraday_pullback") is True:
            reason_codes.append("PREVIOUS_INTRADAY_PULLBACK")
        if yesterday.get("late_pullback") is True:
            reason_codes.append("PREVIOUS_LATE_PULLBACK")
        if yesterday.get("big_bearish") is True:
            reason_codes.append("PREVIOUS_BIG_BEARISH")
        if yesterday.get("volume_state"):
            reason_codes.append(f"PREVIOUS_VOLUME_{str(yesterday['volume_state']).upper()}")
        if gap is not None:
            reason_codes.append("GAP_POSITIVE" if gap > 0 else "GAP_NON_POSITIVE")
        if directional_order_growth is not None:
            reason_codes.append(
                "POST_920_ORDER_GROWTH"
                if directional_order_growth >= 0
                else "POST_920_ORDER_DECAY"
            )
        if percentile is not None:
            reason_codes.append(
                "AUCTION_VOLUME_ABOVE_60P" if percentile >= 60 else "AUCTION_VOLUME_BELOW_60P"
            )
        if sync is not None:
            reason_codes.append("SECTOR_SYNCHRONIZED" if sync >= 0.5 else "SECTOR_DIVERGED")
        rows.append(
            {
                "ts_code": summary.get("ts_code"),
                "stock_name": summary.get("stock_name"),
                "previous_role": old.get("role"),
                "state": state,
                "reason_codes": reason_codes,
            }
        )
    return rows


def build_report(packet: dict[str, Any]) -> dict[str, Any]:
    analysis = packet["objective_analysis"]
    scored = packet.get("scored_stock_ranking") or []
    checks = packet.get("tomorrow_check_validation") or []
    return {
        "1_data_quality": packet["data_quality"],
        "2_market_auction_environment": analysis["market_auction_environment"],
        "3_mainline_auction_ranking": packet.get("sector_breadth") or [],
        "4_previous_mainline_validation": checks,
        "5_stock_auction_top_ranking": [_report_stock_row(row) for row in scored[:30]],
        "6_above_expectation": {
            "relative_to": "exact previous-trading-day formal review role and mainline expectation",
            "stocks": [
                _report_stock_row(row)
                for row in scored
                if row.get("expectation_bucket") == "ABOVE_EXPECTATION"
            ][:20],
        },
        "7_in_line_with_expectation": {
            "relative_to": "exact previous-trading-day formal review role and mainline expectation",
            "stocks": [
                _report_stock_row(row)
                for row in scored
                if row.get("expectation_bucket") == "IN_LINE"
            ][:20],
        },
        "8_below_expectation": {
            "relative_to": "exact previous-trading-day formal review role and mainline expectation",
            "stocks": [
                _report_stock_row(row)
                for row in scored
                if row.get("expectation_bucket") == "BELOW_EXPECTATION"
            ][:20],
        },
        "9_auction_patterns_and_abnormal_orders": packet.get("stock_state_transitions") or [],
        "10_validation_checklist_0930_1000": analysis["validation_conditions_0930_1000"],
        "prohibited_actions": ["buy", "sell", "position_advice"],
    }


def expectation_bucket(score):
    available = score.get("available_max_score") or 0
    ratio = score.get("final_score", 0) / available if available else None
    return (
        "UNAVAILABLE"
        if ratio is None
        else "ABOVE_EXPECTATION"
        if ratio >= 0.72
        else "BELOW_EXPECTATION"
        if ratio < 0.42
        else "IN_LINE"
    )


def _report_stock_row(row):
    score = row.get("score") or {}
    return {
        "rank": row.get("rank"),
        "ts_code": row.get("ts_code"),
        "stock_name": row.get("stock_name"),
        "themes": row.get("themes") or [],
        "roles": row.get("roles") or [],
        "auction_gap_pct": row.get("auction_gap_pct"),
        "auction_amount": row.get("auction_amount"),
        "auction_amount_percentile_20d": row.get("auction_amount_percentile_20d"),
        "price_change_0920_0925_pct": row.get("price_change_0920_0925_pct"),
        "expectation_bucket": row.get("expectation_bucket"),
        "gross_score": score.get("gross_score"),
        "risk_deduction": score.get("risk_deduction"),
        "final_score": score.get("final_score"),
        "score_available": score.get("score_available"),
        "missing_score_components": score.get("missing_score_components") or [],
        "evidence_validation": score.get("evidence_validation") or {},
        "risks": score.get("risks") or [],
    }


def _check_status(entity_type, description, evidence):
    if not evidence:
        return "unverified", "matching auction evidence unavailable"
    if "指数" in description:
        return "unverified", "condition requires an index auction benchmark that is not available"
    if entity_type == "theme":
        ratio = evidence.get("positive_gap_ratio")
        post = evidence.get("post_0920_positive_ratio")
        if ratio is None:
            return "unverified", "theme breadth unavailable"
        if ratio >= 0.67 and (post is None or post >= 0.6):
            return (
                "confirmed",
                "broad participation and post-09:20 stability meet objective thresholds",
            )
        if ratio >= 0.4:
            return "partially_confirmed", "only part of the theme watchlist confirms"
        if ratio <= 0.2:
            return "invalidated", "theme confirmation breadth is at or below 20%"
        return "weakened", "theme confirmation breadth is below 40%"
    gap = evidence.get("auction_gap_pct")
    growth = (
        evidence.get("post_0920_order_growth")
        if evidence.get("unmatched_direction") in {"buy", "sell"}
        else None
    )
    percentile = evidence.get("auction_amount_percentile_20d") or evidence.get(
        "auction_amount_percentile_60d"
    )
    if gap is None or percentile is None:
        return "unverified", "stock price or self-history volume evidence unavailable"
    if gap >= 1 and percentile >= 60 and (growth is None or growth >= 0):
        return "confirmed", "price, self-history volume and available order evidence confirm"
    if gap >= 0 and percentile >= 40:
        return "partially_confirmed", "some but not all objective conditions confirm"
    if gap < -2 and (growth is None or growth < 0):
        return "invalidated", "negative gap and order weakness invalidate the check"
    return "weakened", "objective auction evidence is weaker than the prior condition"


def _structure_status(row):
    leader = row.get("leader_strength")
    capacity = row.get("capacity_strength")
    catch_up = row.get("catch_up_strength")
    breadth = row.get("positive_gap_ratio") or 0
    post = row.get("post_0920_positive_ratio")
    if breadth >= 0.75 and (post is None or post >= 0.65):
        return "FULL_SECTOR_RESONANCE"
    if leader is not None and leader >= 55 and capacity is not None and capacity >= 50:
        return "LEADER_CAPACITY_RESONANCE"
    if leader is not None and leader >= 55 and catch_up is not None and catch_up >= 50:
        return "LEADER_CATCH_UP"
    if leader is not None and leader >= 55 and breadth < 0.4:
        return "LEADER_ONLY"
    if breadth >= 0.6 and post is not None and post < 0.4:
        return "HIGH_OPEN_REVERSAL_RISK"
    return "MIXED"


def _stock_strength(row):
    gap = row.get("auction_gap_pct")
    percentile = row.get("auction_amount_percentile_20d") or row.get(
        "auction_amount_percentile_60d"
    )
    values = []
    if gap is not None:
        values.append(max(0, min(100, 50 + float(gap) * 10)))
    if percentile is not None:
        values.append(float(percentile))
    return statistics.fmean(values) if values else None


def _mean(values):
    valid = [float(value) for value in values if value is not None]
    return statistics.fmean(valid) if valid else None


def _role(value):
    return {
        "龙头": "leader",
        "leader": "leader",
        "中军": "capacity",
        "容量": "capacity",
        "capacity": "capacity",
        "补涨": "catch_up",
        "catch_up": "catch_up",
        "趋势核心": "trend_core",
        "trend_core": "trend_core",
    }.get(value, value or "other")


def _with_suffix(value):
    raw = str(value or "").upper()
    if "." in raw:
        return raw.replace(".SS", ".SH")
    code = raw.zfill(6)
    return f"{code}.{'SH' if code.startswith(('5', '6')) else 'BJ' if code.startswith(('8', '9')) else 'SZ'}"
