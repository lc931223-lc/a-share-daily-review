"""Measured coverage, not schema coverage or source registration counts."""
from collections import Counter

from src.opportunity_radar.contracts import CATEGORIES, stamp, visible, evidence_eligible


def coverage_matrix(rows, cutoff):
    result = []
    for category in CATEGORIES:
        group = [r for r in rows if r["signal_type"] == category and visible(r, cutoff) and evidence_eligible(r)]
        body = [r for r in group if r.get("body_evidence") or r.get("value") is not None]
        result.append({
            "signal_type": category, "schema_supported": True,
            "live_source_count": len({r["source"] for r in body if r.get("facts", {}).get("observation_mode") == "LIVE_OBSERVED"}),
            "historical_source_count": len({r["source"] for r in group if r.get("facts", {}).get("observation_mode") != "LIVE_OBSERVED"}),
            "point_in_time_available": bool(group),
            "point_in_time_scope": "SINCE_ACTUAL_FIRST_SEEN_ONLY",
            "source_tier": sorted({r["source_tier"] for r in group}),
            "production_status": "PARTIAL" if group else "UNAVAILABLE",
            "latest_observation_date": max((r["source_date"] for r in group), default=None),
            "observation_count": len(group), "evidence_observation_count": len(body),
            "major_gaps": sorted({g for r in group for g in r.get("data_gaps", [])}) or [
                "CONTINUOUS_COVERAGE_NOT_PROVEN" if group else "NO_PRODUCTION_OBSERVATIONS"],
        })
    return result


def coverage_metrics(rows, cutoff):
    admissible = [r for r in rows if visible(r, cutoff) and evidence_eligible(r)]
    matrix = coverage_matrix(rows, cutoff)
    return {"matrix": matrix,
            "category_coverage_ratio": sum(r["evidence_observation_count"] > 0 for r in matrix) / 16,
            "live_source_count": len({r["source"] for r in admissible if r.get("facts", {}).get("observation_mode") == "LIVE_OBSERVED"}),
            "tier1_observation_count": sum(r["source_tier"] == 1 for r in admissible),
            "company_body_parsed_count": len({r["url"] for r in admissible if r.get("stock_code") and r.get("facts", {}).get("body_parsed")}),
            "historical_point_in_time_days": len({stamp(r["first_seen_at"]).date() for r in admissible}),
            "technology_chain_coverage": {theme: {"observation_count": sum(r.get("theme") == theme for r in admissible),
                "scope": "DOCUMENT_OR_ISSUER_TOTAL_REVENUE_NOT_COMPLETE_PRODUCT_METRICS"} for theme in ("存储", "光通信", "PCB/CCL", "MLCC", "探针/测试", "先进封装")},
            "signal_type_counts": dict(Counter(r["signal_type"] for r in admissible))}


def validate_counterexample(record):
    """Completed real cases require independently sourced later outcomes."""
    for key in ("event", "objective_facts", "later_market_result", "why_not_counted_as_success", "source_evidence"):
        if not record.get(key):
            raise ValueError("INCOMPLETE_REAL_COUNTEREXAMPLE: " + key)
    if record.get("observation_mode") not in {"LIVE_OBSERVED", "ARCHIVED_POINT_IN_TIME"}:
        raise ValueError("COUNTEREXAMPLE_NOT_POINT_IN_TIME")
    if not all(e.get("url") and e.get("sha256") for e in record["source_evidence"]):
        raise ValueError("COUNTEREXAMPLE_EVIDENCE_MISSING")
