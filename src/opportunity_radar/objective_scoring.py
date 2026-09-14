"""Versioned mechanical evidence scores, never final opportunity rankings."""
from collections import defaultdict
from datetime import timedelta

from src.opportunity_radar.contracts import number, stamp, visible
from src.opportunity_radar.company_evidence import valid_relation

WEIGHTS = {"fundamental_change": 20, "expectation_revision": 20, "industry_strength": 15, "technology": 10,
           "supply_demand": 10, "valuation_headroom": 10, "price_confirmation": 5, "catalyst": 5, "evidence_quality": 5}
MAX_AGE = {"COMMODITY_PRICE": 7, "SUPPLY_DEMAND": 45, "MACRO_LIQUIDITY_FX_RATES": 45,
           "CAPACITY_AND_UTILIZATION": 120, "OVERSEAS_LEAD": 45, "MARKET_STRUCTURE_AND_FLOW": 4,
           "VALUATION_FUNDAMENTAL_DIVERGENCE": 4, "EXPECTATION_REVISION": 90}


def freshness(row, cutoff):
    age = max(0, (cutoff.date()-stamp(row["source_date"]).date()).days)
    limit = MAX_AGE.get(row["signal_type"], 180)
    return {"age_calendar_days": age, "max_age_days": limit, "status": "STALE" if age > limit else "WITHIN_WINDOW"}


def objective_score(components, crowding=None, downside=None):
    components = {key: number(components.get(key)) for key in WEIGHTS}
    if any(v is not None and not 0 <= v <= 100 for v in components.values()):
        raise ValueError("COMPONENT_OUT_OF_RANGE")
    coverage = sum(WEIGHTS[key] for key, value in components.items() if value is not None)
    contributions = {key: round(value*WEIGHTS[key]/100, 4) if value is not None else None for key, value in components.items()}
    deductions = {"crowding_risk": None if crowding is None else round(crowding*.1, 4),
                  "downside_risk": None if downside is None else round(downside*.1, 4)}
    # Missing components are not rescaled to 100; thin evidence cannot score 100.
    enough = coverage >= 40 and any(components[k] is not None for k in ("fundamental_change", "expectation_revision", "supply_demand"))
    score = max(0, min(100, sum(v for v in contributions.values() if v is not None)-sum(v for v in deductions.values() if v is not None))) if enough else None
    return {"objective_opportunity_score": round(score, 2) if score is not None else None,
        **{key+"_score": value for key, value in components.items()}, "crowding_risk_score": crowding, "downside_risk_score": downside,
        "score_version": "objective_evidence.1", "score_weights": WEIGHTS, "weighted_contributions": contributions,
        "risk_deductions": deductions, "score_coverage_pct": coverage, "missing_components": [k for k, v in components.items() if v is None],
        "confidence": "HIGH" if coverage >= 85 and crowding is not None and downside is not None else "MEDIUM" if coverage >= 60 else "LOW",
        "score_status": "PARTIAL" if enough else "INSUFFICIENT_EVIDENCE",
        "score_semantics": "FIXED_WEIGHT_EVIDENCE_POINTS_NOT_INVESTMENT_RANKING; UNKNOWN_RISK_NOT_ASSUMED_ABSENT"}


def anchor(row, company=True):
    direction = "DECREASE" if row.get("facts", {}).get("revision_direction") == "DOWN" or row.get("facts", {}).get("risk_flag") else "INCREASE"
    return {"entity": row["entity"], "theme": row["theme"], "stock_code": row["stock_code"] if company else None,
        "candidate_type": "COMPANY_SPECIFIC_CANDIDATE" if company else "THEME_LEVEL_CANDIDATE",
        "signal_type": row["signal_type"], "observation_id": row["observation_id"], "source_date": row["source_date"],
        "signal_first_seen_date": stamp(row["first_seen_at"]).date().isoformat(), "first_seen_at": row["first_seen_at"],
        "direction": direction, "changes": row.get("changes", {}), "source_tier": row["source_tier"]}


def enrich_candidates(selected, edges, cutoff, old_companies, old_themes):
    groups = defaultdict(list)
    for row in selected:
        if row.get("stock_code"):
            groups[row["stock_code"]].append(row)
    companies = []
    for code, all_rows in groups.items():
        rows = [r for r in all_rows if freshness(r, cutoff)["status"] != "STALE"]
        if not rows:
            continue
        informative = [r for r in rows if r["signal_type"] in {"TECHNOLOGY_BREAKTHROUGH", "EXPECTATION_REVISION", "VALUATION_FUNDAMENTAL_DIVERGENCE"}
                       or r["facts"].get("fundamental_change_pct") is not None]
        old = next((r for r in old_companies if r["stock_code"] == code), None)
        if not informative and not old:
            continue
        revisions = sorted((r for r in rows if r["signal_type"] == "EXPECTATION_REVISION"), key=lambda r: r["published_at"])
        price = max((r for r in rows if r["signal_type"] == "VALUATION_FUNDAMENTAL_DIVERGENCE"), key=lambda r: r["source_date"], default={}).get("facts", {})
        fundamental = max((r for r in rows if r["facts"].get("fundamental_change_pct") is not None), key=lambda r: (r["published_at"], r["metric"] == "reported_earnings"), default={})
        delta = fundamental.get("facts", {}).get("fundamental_change_pct")
        tech = [r for r in rows if r["signal_type"] == "TECHNOLOGY_BREAKTHROUGH"]
        stage_values = {"RESEARCH": 10, "LAB": 10, "ENGINEERING_SAMPLE": 25, "CUSTOMER_VALIDATION": 40,
                        "PRODUCT_VALIDATION": 35, "SMALL_SCALE_PRODUCTION": 60, "SMALL_BATCH": 60, "MASS_PRODUCTION": 80, "RAPID_PENETRATION": 100}
        stages = [stage_values[r["facts"]["current_stage"]] for r in tech if r["facts"].get("current_stage") in stage_values]
        rev = revisions[-1]["facts"].get("revision_pct") if revisions else None
        relations = [e for e in edges if e.get("stock_code") == code and visible(e, cutoff) and valid_relation(e)]
        catalysts = [r for r in rows if r["facts"].get("event_type") in {"ORDER_CONFIRMED", "SHIPMENT_CONFIRMED", "TENDER_WIN"}
                     and r["source_date"] >= (cutoff.date()-timedelta(days=30)).isoformat()]
        ret = price.get("stock_return_20d")
        components = {"fundamental_change": min(100, max(0, 50+delta/2)) if delta is not None else price.get("fundamental_change_score"),
            "expectation_revision": min(100, max(0, 50+rev)) if rev is not None else None,
            "industry_strength": None, "technology": max(stages) if stages else None, "supply_demand": None,
            "valuation_headroom": None, "price_confirmation": min(100, max(0, 50+ret)) if ret is not None else None,
            "catalyst": 80 if catalysts else None, "evidence_quality": sum({1: 100, 2: 80, 3: 40, 4: 10}[r["source_tier"]] for r in rows)/len(rows)}
        crowding = max(0, min(100, (ret-10)*2)) if ret is not None else None
        downside = min(100, -delta) if delta is not None and delta < 0 else None
        scores = objective_score(components, crowding, downside)
        main = revisions[-1] if revisions else fundamental or max(informative or rows, key=lambda r: (r["source_date"], r["observation_id"]))
        risks = sorted({g for r in all_rows for g in r.get("data_gaps", [])})
        if len(rows) < len(all_rows):
            risks.append("STALE_OBSERVATIONS_EXCLUDED_FROM_SCORE")
        if not revisions:
            risks.append("PRIOR_EXPECTATION_UNAVAILABLE")
        if not relations:
            risks.append("VERIFIED_ECONOMIC_RELATION_UNAVAILABLE")
        if price.get("valuation_percentile") is None:
            risks.append("VALUATION_VINTAGES_UNAVAILABLE")
        risks.append("ECONOMIC_EXPOSURE_MAGNITUDE_UNKNOWN")
        candidate = {**anchor(main), **scores, "stock_name": main.get("stock_name"), "signal_types": sorted({r["signal_type"] for r in rows}),
            "main_driver": {"signal_type": main["signal_type"], "metric": main["metric"], "observation_id": main["observation_id"]},
            "verified_relations": [{k: e.get(k) for k in ("product", "relationship_type", "revenue_exposure", "profit_exposure", "customer_exposure", "capacity_exposure", "evidence", "evidence_date", "source", "url", "source_path", "provenance", "confidence", "relation_status")} for e in relations[:12]],
            "expectation_revision": [r["facts"] for r in revisions[-3:]], "fundamental_change": fundamental.get("facts") or None,
            "valuation_fundamental_divergence": price.get("divergence_candidate"), "price_confirmation": price or None,
            "catalyst": [r["observation_id"] for r in catalysts], "risks": risks,
            "evidence": [{"observation_id": r["observation_id"], "url": r["url"], "source_path": r["source_path"], "provenance": r["provenance"],
                          "published_at": r["published_at"], "first_seen_at": r["first_seen_at"], "observation_mode": r["facts"].get("observation_mode")} for r in sorted(rows, key=lambda r: r["published_at"], reverse=True)[:12]],
            "candidate_scope": "EVIDENCE_SCREEN_NOT_OVERNIGHT_EVENT_OR_STOCK_RECOMMENDATION"}
        companies.append(candidate)
    companies.sort(key=lambda r: (r["objective_opportunity_score"] is None, -(r["objective_opportunity_score"] or 0), -r["score_coverage_pct"], r["stock_code"]))
    themes = defaultdict(list)
    for row in selected:
        if row.get("theme") and freshness(row, cutoff)["status"] != "STALE":
            themes[row["theme"]].append(row)
    theme_rows = []
    for theme, rows in themes.items():
        supporting = [r for r in rows if r["signal_type"] in {"TECHNOLOGY_BREAKTHROUGH", "EXPECTATION_REVISION"} or (r.get("changes", {}).get("delta") or 0) > 0]
        contradicting = [r for r in rows if r["facts"].get("risk_flag") or r["facts"].get("revision_direction") == "DOWN" or (r.get("changes", {}).get("delta") or 0) < 0]
        if not supporting and not contradicting:
            continue
        main = max(supporting or contradicting, key=lambda r: r["source_date"])
        theme_rows.append({**anchor(main, False), "entity": theme, "theme": theme,
            "signal_direction": "MIXED" if supporting and contradicting else "POSITIVE_EVIDENCE" if supporting else "NEGATIVE_EVIDENCE",
            "signal_strength": {"support_count": len(supporting), "contradiction_count": len(contradicting), "semantics": "EVIDENCE_COUNTS_NOT_RETURN_FORECAST"},
            "main_drivers": sorted({r["signal_type"] for r in rows}), "supporting_observations": [r["observation_id"] for r in supporting],
            "contradicting_observations": [r["observation_id"] for r in contradicting], "sustainability": None,
            "confidence": "LOW", "quality_gaps": ["PERSISTENCE_AND_CAUSALITY_NOT_ESTABLISHED"]})
    theme_rows.sort(key=lambda r: (-r["signal_strength"]["support_count"], r["theme"]))
    return companies, theme_rows or old_themes
