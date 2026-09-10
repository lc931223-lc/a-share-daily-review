from __future__ import annotations

import hashlib
import json
import math
from urllib.parse import urlparse
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from src.domain.constants import DRIVER_TYPES

SHANGHAI = ZoneInfo("Asia/Shanghai")
VERSION = "opportunity_radar_objective.2"
CATEGORIES = dict(zip((
    "COMMODITY_PRICE", "SUPPLY_DEMAND", "CAPACITY_AND_UTILIZATION", "POLICY_AND_FISCAL",
    "TECHNOLOGY_BREAKTHROUGH", "PRODUCT_COMMERCIALIZATION", "CUSTOMER_AND_ORDER",
    "REVENUE_PROFIT_MARGIN", "EXPECTATION_REVISION", "INDUSTRY_COMPETITION",
    "M&A_AND_CAPITAL_OPERATION", "SHAREHOLDER_MANAGEMENT_ACTION", "OVERSEAS_LEAD",
    "MACRO_LIQUIDITY_FX_RATES", "VALUATION_FUNDAMENTAL_DIVERGENCE", "MARKET_STRUCTURE_AND_FLOW",
), (
    "commodity_observations", "supply_demand_observations", "capacity_utilization_observations",
    "policy_observations", "technology_breakthrough_observations", "product_commercialization_observations",
    "customer_order_observations", "fundamental_change_observations", "expectation_revision_observations",
    "industry_competition_observations", "capital_operation_observations", "shareholder_management_observations",
    "overseas_lead_observations", "macro_observations", "valuation_fundamental_divergence_candidates",
    "market_structure_observations",
)))
FORBIDDEN = set("opportunity_rank opportunity_score final_opportunity buy_priority sell_priority recommendation conviction expected_return target_price final_mainline mainline_prediction final_lifecycle final_stock_role final_rating final_six_dimension_score causal_conclusion valuation_conclusion market_regime_conclusion investment_conclusion final_judgement market_priced_pct fully_priced underpriced overpriced".split())
FORBIDDEN.update("beneficiary_priority undervalued overvalued".split())
FINAL_STATES = set("DISCOVERED EARLY WATCH PRE_HEAT CONFIRMED CROWDED INVALIDATED".split())
STAGES = {
    "CAPACITY_AND_UTILIZATION": "ANNOUNCED_CAPACITY UNDER_CONSTRUCTION COMMISSIONING PRODUCTION_STARTED EFFECTIVE_OUTPUT".split(),
    "POLICY_AND_FISCAL": "GUIDANCE PLAN FUNDING IMPLEMENTATION PROJECT TENDER PROCUREMENT TAX_INCENTIVE SUBSIDY REGULATORY_RELAXATION REGULATORY_TIGHTENING".split(),
    "TECHNOLOGY_BREAKTHROUGH": "LAB ENGINEERING_SAMPLE PRODUCT_VALIDATION CUSTOMER_VALIDATION SMALL_BATCH MASS_PRODUCTION".split(),
    "PRODUCT_COMMERCIALIZATION": "RESEARCH LAB_VALIDATION ENGINEERING_SAMPLE PRODUCT_VALIDATION CUSTOMER_VALIDATION SMALL_BATCH MASS_PRODUCTION COMMERCIAL_REVENUE SCALE_REVENUE".split(),
    "CUSTOMER_AND_ORDER": "CUSTOMER_VALIDATION CUSTOMER_ENTRY FRAMEWORK_AGREEMENT TENDER_WIN ORDER_CONFIRMED SHIPMENT_CONFIRMED REVENUE_CONFIRMED ORDER_CANCELLED CUSTOMER_LOSS CUSTOMER_EXPANSION".split(),
    "M&A_AND_CAPITAL_OPERATION": "INTENTION PLAN BOARD_APPROVED REGULATORY_ACCEPTED APPROVED CLOSED".split(),
}
HARD_STAGES = set("ORDER_CONFIRMED CUSTOMER_CONFIRMED MASS_PRODUCTION REVENUE_CONFIRMED PROFIT_CONFIRMED PRODUCTION_STARTED EFFECTIVE_OUTPUT COMMERCIAL_REVENUE SCALE_REVENUE".split())
FACTOR_MAP = dict(zip(CATEGORIES, (
    [15, 16, 18], [17], [22], [5, 6, 8, 12], [1, 3], [2, 13], [19, 31],
    [24, 25, 26], [23], [9, 32], [27, 28], [29, 30], [4], [7, 11], [33], [34, 35, 36, 38],
)))
FIELDS = {
    "COMMODITY_PRICE": "instrument category latest_value unit currency change_1d change_3d change_5d change_10d change_20d percentile_20d percentile_60d percentile_250d new_high_20d new_high_60d new_low_20d slope_3d slope_10d slope_20d acceleration_3d_vs_20d historical_volatility",
    "SUPPLY_DEMAND": "metric industry current_value previous_value change_abs change_pct percentile zscore trend_5d trend_20d",
    "CAPACITY_AND_UTILIZATION": "industry company metric current previous delta historical_percentile event_type announced_capacity effective_capacity",
    "POLICY_AND_FISCAL": "title publisher affected_industries affected_regions policy_stage fiscal_amount project_amount implementation_date",
    "TECHNOLOGY_BREAKTHROUGH": "technology institution company milestone_type previous_stage current_stage quantitative_improvement",
    "PRODUCT_COMMERCIALIZATION": "stock_code product previous_stage current_stage transition_date evidence",
    "CUSTOMER_AND_ORDER": "stock_code stock_name customer event_type contract_amount currency ratio_vs_last_year_revenue duration certainty",
    "REVENUE_PROFIT_MARGIN": "revenue_yoy revenue_qoq revenue_acceleration profit_yoy profit_qoq profit_acceleration gross_margin gross_margin_change net_margin cash_flow ROE backlog segment_growth monthly_operation_data",
    "EXPECTATION_REVISION": "consensus_eps_current consensus_eps_previous consensus_profit_current consensus_profit_previous revision_7d revision_30d number_of_upgrades number_of_downgrades company_guidance_change broker_estimate_change",
    "INDUSTRY_COMPETITION": "industry metric current previous event",
    "M&A_AND_CAPITAL_OPERATION": "value target consideration approval_required uncertainty_flags",
    "SHAREHOLDER_MANAGEMENT_ACTION": "actor action amount shares percentage price_range",
    "OVERSEAS_LEAD": "market instrument related_theme move_1d move_3d move_5d event_type",
    "MACRO_LIQUIDITY_FX_RATES": "metric current previous surprise_vs_expectation trend",
    "VALUATION_FUNDAMENTAL_DIVERGENCE": "revenue profit margin order price supply_demand expectation_revision return_1d return_5d return_20d PE PB PS valuation_percentile sector_relative_valuation",
    "MARKET_STRUCTURE_AND_FLOW": "return_1d return_3d return_5d return_10d return_20d relative_return_5d relative_return_20d breadth amount amount_change limit_up_count failed_limit_count turnover historical_percentile relative_strength",
}


def stamp(value):
    if not value:
        return None
    try:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        # Date-only publications are not assumed to have been known at midnight.
        if len(str(value)) == 10:
            result = datetime.combine(result.date(), time(23, 59, 59))
        return result.replace(tzinfo=SHANGHAI) if result.tzinfo is None else result.astimezone(SHANGHAI)
    except ValueError:
        return None


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False).encode()).hexdigest()


def number(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (ValueError, TypeError):
        return None


def objective_guard(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if key.lower() in FORBIDDEN:
                raise ValueError("FORBIDDEN_RESEARCH_FIELD: " + key)
            objective_guard(item)
    elif isinstance(value, list):
        for item in value:
            objective_guard(item)
    elif isinstance(value, str) and value in FINAL_STATES:
        raise ValueError("FORBIDDEN_FINAL_STATE")


def visible(row, cutoff):
    seen = stamp(row.get("first_seen_at"))
    published = stamp(row.get("published_at"))
    source_day = str(row.get("source_date") or "")[:10]
    try:
        date.fromisoformat(source_day)
    except ValueError:
        return False
    if row.get("published_at") and published is None:
        return False
    event = str(row.get("event_date") or "")[:10]
    if event and event > cutoff.date().isoformat():
        return False
    return bool(seen and seen <= cutoff and (not published or published <= cutoff)
                and source_day and source_day <= cutoff.date().isoformat())


def evidence_eligible(row):
    facts = row.get("facts") or {}
    if facts.get("body_parsed") and row.get("stock_code") and facts.get("parser_version") != "DISCLOSURE_BODY_V21_3":
        return False
    if row.get("source") == "NBS" and row.get("metric") == "reported_production":
        return False
    return True


def normalize(row):
    objective_guard(row)
    category = row["signal_type"]
    if category not in CATEGORIES:
        raise ValueError("UNKNOWN_SIGNAL_TYPE")
    source_tier = row.get("source_tier", 4)
    if source_tier not in (1, 2, 3, 4):
        raise ValueError("INVALID_SOURCE_TIER")
    if source_tier == 1:
        host = (urlparse(row.get("url") or "").hostname or "").lower()
        official = ("gov.cn", "cninfo.com.cn", "sse.com.cn", "szse.cn", "bse.cn", "pbc.gov.cn")
        if not any(host == d or host.endswith("." + d) for d in official):
            source_tier = 4
    facts = {key: None for key in FIELDS[category].split()}
    facts.update(row.get("facts") or {})
    stage = facts.get("current_stage") or facts.get("policy_stage") or facts.get("event_type")
    # A structured, sourced statement is necessary. A title is never such a statement.
    if stage in HARD_STAGES and (source_tier == 4 or not row.get("body_evidence")):
        raise ValueError("UNSUPPORTED_HARD_CONFIRMATION")
    negations = ("尚未", "尚处", "未形成", "未实现", "未量产", "仍在研发", "验证中", "客户验证", "未认证", "可用于", "拟", "预计", "有望", "可能", "不排除", "暂无", "未与", "不涉及", "框架协议", "战略协议", "战略合作", "合作意向", "海外同行上涨", "not yet", "no order", "no revenue")
    if stage in HARD_STAGES and any(word in str(row.get("body_evidence") or "").lower() for word in negations):
        raise ValueError("NEGATED_OR_PROSPECTIVE_HARD_CONFIRMATION")
    for key in ("current_stage", "previous_stage", "policy_stage"):
        if facts.get(key) and category in STAGES and facts[key] not in STAGES[category]:
            raise ValueError("INVALID_DISCLOSURE_STAGE")
    for key in ("current_stage", "previous_stage", "policy_stage", "event_type"):
        if facts.get(key) in STAGES.get(category, []) and not row.get("body_evidence"):
            raise ValueError("TITLE_IS_NOT_STAGE_EVIDENCE")
    required = ("source_date", "first_seen_at", "source", "provenance")
    missing = [key for key in required if not row.get(key)]
    if not row.get("url") and not row.get("source_path"):
        missing.append("source_reference")
    if not row.get("published_at"):
        missing.append("published_at")
    if number(row.get("value")) is None and not row.get("body_evidence"):
        missing.append("quantitative_or_body_evidence")
    factors = row.get("mapped_factor_ids", FACTOR_MAP[category])
    if any(fid not in DRIVER_TYPES for fid in factors):
        raise ValueError("UNKNOWN_FACTOR41_ID")
    out = {key: row.get(key) for key in (
        "entity", "theme", "stock_code", "stock_name", "metric", "unit", "currency",
        "event_date", "published_at", "first_seen_at", "effective_date", "source_date",
        "source", "source_path", "url", "provenance", "body_evidence", "title",
    )}
    out.update(signal_type=category, source_tier=source_tier, facts=facts,
               value=number(row.get("value")), data_quality="PARTIAL" if missing else "PASS",
               confidence="LOW" if missing or source_tier >= 3 else "HIGH",
               data_gaps=missing, as_of_valid=False, mapped_factor_ids=factors,
               mapping_confidence="LOW", mapping_method="CATEGORY_ASSOCIATION_NOT_CAUSAL",
               mapping_source="src/domain/constants.py:DRIVER_TYPES",
               observation_id=digest({k: v for k, v in row.items() if k not in {"observation_id", "first_seen_at", "provenance", "source_path"}}))
    return out
