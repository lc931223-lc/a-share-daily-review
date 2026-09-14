"""Audit real frozen evidence packets, including missing sessions, without rewriting them."""
import argparse
from datetime import date, datetime
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.auction.production import write
from src.opportunity_radar.contracts import CATEGORIES, SHANGHAI, stamp
from src.opportunity_radar.coverage import coverage_metrics
from src.opportunity_radar.pipeline import read_context
from src.opportunity_radar.storage import ObservationStore
from src.opportunity_radar.company_evidence import PRODUCTS, valid_relation


def audit(root, day, snapshot):
    context = read_context(root, day, snapshot)
    if context["status"] != "AVAILABLE":
        raise ValueError("REQUESTED_LIVE_SNAPSHOT_UNAVAILABLE")
    packet = context["packet"]
    cutoff = stamp(packet["meta"]["as_of"])
    metrics = coverage_metrics(ObservationStore(root).all(), cutoff)
    folder = root / "data/opportunity_radar"
    dates = sorted({p.name[:10] for p in folder.glob("????-??-??_*.json") if p.name[:10] <= str(day)})[-3:]
    sessions = []
    for prior in dates:
        for kind in ("MORNING", "EOD"):
            entry = read_context(root, date.fromisoformat(prior), kind)
            prefix = f"{prior}_{kind.lower()}"
            paths = [folder / f"{prefix}{suffix}.json" for suffix in ("", "_compact", "_receipt")]
            paths.append(folder / "coverage" / f"{prefix}.json")
            sessions.append({"trade_date": prior, "snapshot_type": kind, "status": entry["status"],
                "files": [{"path": p.relative_to(root).as_posix(), "exists": p.exists(),
                           "sha256": hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None} for p in paths]})
    technology = packet[CATEGORIES["TECHNOLOGY_BREAKTHROUGH"]]
    products = {r["facts"].get("technology_name") for r in technology}
    product_coverage = {theme: {p: "PARTIAL" if p in products else "UNAVAILABLE" for p in values} for theme, values in PRODUCTS.items()}
    baseline_path = folder / "coverage/2026-09-11_eod.json"
    baseline = json.loads(baseline_path.read_text("utf8")) if baseline_path.exists() else {}
    improvements = {key: {"baseline": baseline.get("signal_type_counts", {}).get(key, 0),
        "current_snapshot": len(packet[CATEGORIES[key]])} for key in ("TECHNOLOGY_BREAKTHROUGH", "EXPECTATION_REVISION", "INDUSTRY_COMPETITION", "VALUATION_FUNDAMENTAL_DIVERGENCE")}
    edges_path = root / "data/reference/opportunity_relations.json"
    edges = json.loads(edges_path.read_text("utf8")) if edges_path.exists() else []
    from src.opportunity_radar.contracts import visible
    verified = [e for e in edges if valid_relation(e) and visible(e, cutoff)]
    companies = packet["company_specific_candidates"]
    fields = "stock_code stock_name theme objective_opportunity_score score_coverage_pct score_status confidence main_driver expectation_revision verified_relations fundamental_change valuation_fundamental_divergence price_confirmation risks".split()
    return {"generated_at": datetime.now(SHANGHAI).isoformat(), "acceptance_status": "PARTIAL",
        "reason": "PRODUCTION_PIPELINE_VERIFIED_BUT_EVIDENCE_COVERAGE_INCOMPLETE",
        "trade_date": str(day), "snapshot": snapshot, "as_of": packet["meta"]["as_of"],
        "data_role": packet["meta"]["data_role"], "final_judgement_owner": "chatgpt", "schema_version": packet["meta"]["schema_version"],
        "coverage": metrics, "snapshot_counts": {key: len(packet[value]) for key, value in CATEGORIES.items()},
        "technology_product_coverage": product_coverage, "verified_relation_count": len(verified),
        "verified_relation_company_count": len({e.get("stock_code") for e in verified}),
        "company_alpha_count": len(companies), "scorable_company_count": sum(c.get("objective_opportunity_score") is not None for c in companies),
        "mechanical_order_not_final_opportunity_ranking": True,
        "top_theme_candidates": packet["theme_candidates"][:10],
        "top_company_candidates": [{k: c.get(k) for k in fields} for c in companies[:20]],
        "improvements": improvements, "recent_three_available_dates": sessions,
        "compact_bytes": (folder / f"{day}_{snapshot.lower()}_compact.json").stat().st_size,
        "remaining_gaps": ["LICENSED_CONSENSUS_AND_FORWARD_PE_UNAVAILABLE", "MOST_PRODUCT_CONTRACT_PRICES_AND_INVENTORY_UNAVAILABLE",
            "ECONOMIC_EXPOSURE_PERCENTAGES_MOSTLY_UNKNOWN", "COMPETITOR_AND_NAMED_CUSTOMER_EDGES_INCOMPLETE",
            "INDUSTRY_20D_PIT_AND_VALUATION_VINTAGES_INCOMPLETE", "MACRO_ORIGINAL_VINTAGES_AND_RATE_FX_CONTINUITY_INCOMPLETE",
            "NEW_TECHNOLOGY_SUBCATEGORIES_NOT_ALL_EVIDENCED", "BACKFILL_DOCUMENTS_NOT_OVERNIGHT_SIGNALS_OR_HISTORICAL_LEAD_PROOF",
            "SAME_DAY_EOD_EXTENSION_REQUIRES_REAL_CLOSE_CANNOT_REPLACE_FROZEN_EOD"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", required=True, type=date.fromisoformat)
    parser.add_argument("--snapshot", choices=["MORNING", "EOD"], default="MORNING")
    args = parser.parse_args()
    report = audit(ROOT, args.date, args.snapshot)
    path = ROOT / "reports/opportunity_radar_acceptance" / f"{args.date}_{args.snapshot.lower()}.json"
    write(path, report)
    print(json.dumps({"report": path.relative_to(ROOT).as_posix(), "status": report["acceptance_status"],
        "coverage_ratio": report["coverage"]["category_coverage_ratio"], "companies": report["company_alpha_count"],
        "scorable": report["scorable_company_count"], "verified_relations": report["verified_relation_count"]}))
