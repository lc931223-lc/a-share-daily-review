"""Objective domains and fixed, availability-aware scoring inputs."""
import math

ALIASES = {"农化": "农化制品", "农药化肥": "农化制品", "汽车零部": "汽车零部件", "农产品加": "农产品加工"}
PARENTS = {"草甘膦": "农化制品", "农化制品": "化学制品", "生物育种": "种植业", "生态农业": "农业"}


def evidence_domain(factor_id):
    if factor_id in {5, 6, 7, 8, 9, 10, 12}:
        return "OFFICIAL_POLICY"
    if factor_id in {14, 15, 16, 17, 18, 21, 22, 32}:
        return "INDUSTRY_PRICE_AND_CYCLE"
    if factor_id == 33:
        return "VALUATION_BASELINE"
    if factor_id >= 34:
        return "MARKET_STRUCTURE"
    return "COMPANY_DISCLOSURE"


def identity(name):
    canonical = ALIASES.get(name, name)
    return {"canonical_name": canonical, "parent": PARENTS.get(canonical), "mapping_version": "theme_identity.1"}


def number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (ValueError, TypeError):
        return None


def market_evidence(theme, context, market, target):
    name = theme["theme"]
    board = next((r for r in market.get("themes", []) + market.get("industries", []) if identity(r.get("theme_name") or r.get("industry_name") or r.get("name"))["canonical_name"] == identity(name)["canonical_name"]), {})
    enriched = {**theme, "change_pct": theme.get("change_pct") if theme.get("change_pct") is not None else board.get("change_pct"), "limit_up_count": theme.get("limit_up_count") if theme.get("limit_up_count") is not None else board.get("limit_up_count")}
    capital = next((r for r in context.get("capital_preference", {}).get("theme_capital_preference", []) if identity(r.get("theme"))["canonical_name"] == identity(name)["canonical_name"]), {})
    crowding = (capital.get("crowding_advantage") or {}).get("inputs") or {}
    enriched["crowding_intensity"] = crowding.get("crowding_intensity")
    enriched["volatility_percentile"] = crowding.get("volatility_percentile")
    output = []
    def emit(factor, inputs, status="CONFIRMED"):
        output.append({"factor_id": factor, "kind": "market_structure", "domain": "MARKET_STRUCTURE", "source": "MarketPacket/ReviewIntelligence", "source_type": "objective_calculation", "source_date": str(target), "tier": 3, "confidence": "MEDIUM", "related_themes": [name], "inputs": inputs, "evaluation_status": status})
    for row in context.get("inflection_candidates", []):
        if name in (row.get("themes") or []) and row.get("breakout"):
            breakout = row["breakout"]
            if isinstance(breakout, dict) and breakout.get("hold_status") == "BREAKOUT_HELD" and breakout.get("volume_confirmation") == "HIGH_VOLUME_CONFIRMED" and breakout.get("failure") is False:
                emit(36, {"ts_code": row.get("ts_code"), "breakout": breakout})
    breadth = number(theme.get("breadth"))
    if theme.get("leader_candidates") and breadth is not None and breadth >= 60 and (number(board.get("change_pct")) or 0) > 0:
        emit(37, {"breadth": breadth, "leader_candidates": theme["leader_candidates"], "return": board["change_pct"]}, "PARTIAL")
    # A style change is evidence only when a measured previous-day change exists.
    for style in context.get("market_cycle_and_style", {}).get("style_strength", []):
        delta = number(style.get("style_change_1d"))
        if delta is not None and delta >= 10 and (number(style.get("breadth")) or 0) >= 60:
            emit(38, {"style": style.get("style"), "change_1d": delta, "breadth": style.get("breadth")}, "PARTIAL")
    return enriched, output


def component(maximum, items, reason):
    available = [row for row in items if row["raw_score"] is not None]
    return {"max_score": maximum, "raw_score": round(sum(row["raw_score"] for row in available), 4) if available else None, "available_score": sum(row["max_score"] for row in available), "subcomponents": items, "evidence": [{"field": row["name"], "value": row["value"]} for row in available], "reason": reason}


def score_components(theme, factors):
    def item(name, value, maximum, fraction):
        value = number(value)
        return {"name": name, "value": value, "max_score": maximum, "raw_score": maximum * min(1, max(0, fraction(value))) if value is not None else None}
    confirmed = sum(f["status"] == "CONFIRMED" and f["factor_id"] < 34 for f in factors)
    fundamental_available = any(f["factor_id"] < 34 and f["status"] in {"CONFIRMED", "PARTIAL"} for f in factors)
    realization_ids = {19, 22, 24, 25, 26}
    realization_available = any(f["factor_id"] in realization_ids and f["status"] in {"CONFIRMED", "PARTIAL"} for f in factors)
    scores = {
        "base_logic": component(40, [item("confirmed_fundamental_factors", confirmed if fundamental_available else None, 40, lambda v: v / 5)], "qualified domain evidence only" if fundamental_available else "NO_QUALIFYING_FUNDAMENTAL_EVIDENCE"),
        "realization": component(25, [item("confirmed_realization_factors", sum(f["status"] == "CONFIRMED" and f["factor_id"] in realization_ids for f in factors) if realization_available else None, 25, lambda v: v / 3)], "disclosed realization evidence; price strength is not earnings realization" if realization_available else "NO_QUALIFYING_REALIZATION_EVIDENCE"),
        "expectation_gap": component(15, [], "NO_EXPECTATION_BASELINE"),
    }
    windows = [(n, number(theme.get(f"strength_change_{n}d"))) for n in (5, 3, 2, 1)]
    window, change = next(((n, v) for n, v in windows if v is not None), (0, None))
    scores["continuity"] = component(10, [item("strength_change", change, window * 2, lambda v: .5 + v / 20)], "observed short window; unobserved days receive no available points") | {"window_available": window}
    scores["market_confirmation"] = component(10, [item("theme_return", theme.get("change_pct"), 3, lambda v: .5 + v / 10), item("breadth", theme.get("breadth"), 3, lambda v: v / 100), item("limit_up_count", theme.get("limit_up_count"), 2, lambda v: v / 3), item("amount", theme.get("amount"), 2, lambda v: 1 if v > 0 else 0)], "fixed return/breadth/limit structure/liquidity rubric")
    scores["risk_deduction"] = component(20, [item("crowding", theme.get("crowding_intensity"), 4, lambda v: (v - 70) / 30), item("leader_dependency", theme.get("leader_dependency"), 3, lambda v: (v - .5) * 2), item("breadth_decline", theme.get("breadth_change_1d"), 2, lambda v: -v / 20), item("price_volume_divergence", theme.get("price_volume_divergence"), 2, lambda v: v), item("disclosed_risk_count", len(theme.get("risk") or []) if "risk" in theme else None, 3, lambda v: v / 3), item("earnings_unsupported", theme.get("earnings_unsupported"), 2, lambda v: v), item("catalyst_falsified", theme.get("catalyst_falsified"), 2, lambda v: v), item("high_volatility", theme.get("volatility_percentile"), 1, lambda v: (v - 80) / 20), item("consecutive_climax", theme.get("consecutive_climax"), 1, lambda v: v / 3)], "explicit observations only; absent risks remain unavailable, not zero")
    return {"components": scores, "gross_raw_score": sum(row["raw_score"] or 0 for key, row in scores.items() if key != "risk_deduction"), "gross_available_score": sum(row["available_score"] for key, row in scores.items() if key != "risk_deduction"), "risk_deduction": scores["risk_deduction"]["raw_score"], "final_score_owner": "chatgpt"}
