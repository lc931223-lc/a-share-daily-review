"""Fixed observable subcomponents; evidence reliability is not materiality."""

from datetime import datetime

MATERIALITY = {
    "ORDER_MAJOR": 5,
    "EARNINGS_BEAT": 5,
    "MERGER": 5,
    "POLICY_NATIONAL": 5,
    "PRICE_UP": 4,
    "CAPACITY_EXPANSION": 3,
    "BUYBACK": 2,
    "SHAREHOLDER_INCREASE": 2,
    "REGULATORY_RISK": 0,
    "CLARIFICATION": 0,
    "REDUCTION": 0,
    "UNLOCK": 0,
    "ROUTINE": 0,
}
RISK_RULES = {
    "EARNINGS_RISK": (
        3,
        (
            "业绩预减",
            "业绩下滑",
            "亏损",
            "扭盈为亏",
            "不及预期",
            "下修",
            "营收下降",
            "净利润下降",
            "净利润同比下降",
        ),
    ),
    "REGULATORY": (4, ("监管处罚", "行政处罚", "立案调查", "监管函", "纪律处分")),
    "DECREASE_HOLDING": (4, ("减持计划", "拟减持", "减持公告")),
    "UNLOCK": (3, ("限售股解禁", "解除限售", "限售股上市流通")),
    "CLARIFICATION": (3, ("澄清公告", "未形成订单", "尚未形成收入", "业务占比低")),
}


def component(maximum, parts, reason):
    available = {k: v for k, v in parts.items() if v[0] is not None}
    return dict(
        score=round(sum(max(0, min(v[1], v[0])) for v in available.values()), 4)
        if available
        else None,
        max_score=maximum,
        available_max_score=sum(v[1] for v in available.values()),
        reason=reason,
        input_fields=list(available),
        confidence="MEDIUM" if available else "NONE",
        subcomponents={
            k: dict(score=v[0], max_score=v[1], status="N/A" if v[0] is None else "AVAILABLE")
            for k, v in parts.items()
        }
        or None,
    )


def market_sample(summaries, previous, watchlist):
    rows = [r for r in summaries if r.get("auction_gap_pct") is not None]
    roles = {s.get("ts_code"): s.get("role") for s in previous.get("stocks", [])}
    core = [
        r for r in rows if roles.get(r.get("ts_code")) in {"leader", "capacity", "sentiment_core"}
    ]
    return dict(
        sample_scope="FOCUSED_WATCH_UNIVERSE_NOT_FULL_MARKET",
        sample_size=len(rows),
        expected_size=len(watchlist),
        positive_gap_ratio=sum(r["auction_gap_pct"] > 0 for r in rows) / len(rows)
        if rows
        else None,
        negative_gap_ratio=sum(r["auction_gap_pct"] < 0 for r in rows) / len(rows)
        if rows
        else None,
        high_open_ratio=sum(r["auction_gap_pct"] > 3 for r in rows) / len(rows) if rows else None,
        low_open_ratio=sum(r["auction_gap_pct"] < -3 for r in rows) / len(rows) if rows else None,
        market_auction_amount=sum(
            r["auction_amount"] for r in rows if r.get("auction_amount") is not None
        )
        if rows
        else None,
        core_positive_ratio=sum(r["auction_gap_pct"] > 0 for r in core) / len(core)
        if core
        else None,
    )


def market_component(previous):
    sample = previous.get("auction_market", {})
    operability = previous.get("market", {}).get("operability")
    coverage = min(1, sample.get("sample_size", 0) / 100)
    breadth = sample.get("positive_gap_ratio")
    core = sample.get("core_positive_ratio")
    return component(
        10,
        dict(
            previous_operability=(
                float(operability) * 0.03 if operability is not None else None,
                3,
            ),
            watch_universe_breadth=(
                breadth * 4 * coverage if breadth is not None else None,
                4 * coverage,
            ),
            high_position_capacity_feedback=(core * 3 if core is not None else None, 3),
        ),
        "global focused universe, never per-sector breadth",
    )


def mainline_component(theme, sector):
    theme, sector = theme or {}, sector or {}
    score, breadth = theme.get("mainline_score"), sector.get("positive_gap_ratio")
    leader, capacity = sector.get("leader_strength"), sector.get("capacity_strength")
    checked = sector.get("tomorrow_check_ratio")
    return (
        component(
            15,
            dict(
                previous_quality=(score * 0.04 if score is not None else None, 4),
                sector_breadth=(breadth * 4 if breadth is not None else None, 4),
                leader_capacity_resonance=(
                    min(leader, capacity) * 0.04
                    if leader is not None and capacity is not None
                    else None,
                    4,
                ),
                tomorrow_check=(checked * 3 if checked is not None else None, 3),
            ),
            "4+4+4+3; missing exact formal theme is unavailable",
        )
        if theme
        else component(15, {}, "exact previous formal mainline missing")
    )


def catalyst_component(stock, theme, records):
    evidence = records + ((stock or {}).get("factors") or (theme or {}).get("factors") or [])
    candidates = []
    for e in evidence:
        level = e.get("evidence_level")
        if level not in {"A", "B", "C", "D"}:
            continue
        reliability = {"A": 6, "B": 4, "C": 2, "D": 0}[level]
        materiality = MATERIALITY.get(e.get("event_type"))
        fresh = None
        try:
            published, cutoff = (
                datetime.fromisoformat(e["published_at"]),
                datetime.fromisoformat(e["as_of"]),
            )
            hours = (cutoff - published).total_seconds() / 3600
            if hours < 0:
                continue
            fresh = 2 if hours <= 12 else 1 if hours <= 24 else 0
        except (KeyError, TypeError, ValueError):
            pass
        relevance = (
            2 if e.get("stock_code") or e.get("ts_code") else 1 if e.get("related_themes") else None
        )
        parts = dict(
            source_reliability=(reliability, 6),
            materiality=(materiality, 5),
            freshness=(fresh, 2),
            direct_relevance=(relevance, 2),
        )
        if level == "D":
            parts = {k: (0 if v[0] is not None else None, v[1]) for k, v in parts.items()}
        candidates.append(
            component(
                15,
                parts,
                "explicit event_type rules; unclassified materiality is N/A; same evidence item only",
            )
        )
    return (
        max(candidates, key=lambda r: r["score"] or 0)
        if candidates
        else component(15, {}, "no time-qualified catalyst evidence")
    )
