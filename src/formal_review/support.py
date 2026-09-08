from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from src.domain.constants import DRIVER_TYPES
from src.market_packet.trading_calendar import load_trading_calendar
from src.formal_review.persistence import load_previous_formal
from src.formal_review.evidence_domains import identity, market_evidence, score_components, evidence_domain, number

LIFECYCLE_STATES = (
    "MENG_LONG",
    "GERMINATION",
    "VALIDATION",
    "MAIN_UP",
    "DIFFUSION",
    "REALIZATION",
    "FALSIFIED",
    "HIGH_VOLATILITY",
    "SECONDARY_MAIN_UP",
    "REPAIR",
)
ROLE_MAP = {
    "LEADER_CANDIDATE": "LEADER",
    "CAPACITY_CANDIDATE": "CAPACITY",
    "TREND_LEADER_CANDIDATE": "TREND_LEADER",
    "ELASTICITY_CANDIDATE": "ELASTICITY",
    "CATCH_UP_CANDIDATE": "CATCH_UP",
    "FOLLOWER_CANDIDATE": "FOLLOWER",
}
FACTOR_BY_CATEGORY = {
    "order": 19,
    "contract": 19,
    "customer": 31,
    "earnings": 23,
    "restructuring": 27,
    "buyback": 30,
    "increase_holding": 30,
    "product": 13,
    "capacity": 22,
}


def build_formal_review_support(root: Path, target: date) -> dict[str, Any]:
    context_path = root / "data" / "review_context" / f"{target.isoformat()}.json"
    market_path = root / "data" / "market_packets" / f"{target.isoformat()}.json"
    if not context_path.is_file() or not market_path.is_file():
        raise FileNotFoundError("same-date review_context and market_packet are required")
    context = _read(context_path)
    market = _read(market_path)
    _require_date(context, target, "review_context")
    _require_date(market, target, "market_packet")
    previous = _previous_support(root, target)
    previous_themes = {
        identity(row["theme_name"])["canonical_name"]: row for row in (previous or {}).get("theme_support") or []
    }
    evidence = _evidence(market, target)
    theme_support = []
    for rank, theme in enumerate(context.get("next_day_theme_candidates") or [], 1):
        name = str(theme.get("theme") or "")
        theme, structure_evidence = market_evidence(theme, context, market, target)
        prior_theme = previous_themes.get(identity(name)["canonical_name"]) or {}
        strength = number(theme.get("strength"))
        prior_strength = number(prior_theme.get("objective_strength"))
        if theme.get("strength_change_1d") is None and strength is not None and prior_strength is not None:
            theme["strength_change_1d"] = strength - prior_strength
        theme_evidence = [row for row in evidence if name in row.get("related_themes", [])]
        factors = _factor_evaluation(theme_evidence + structure_evidence)
        previous_state = (previous_themes.get(identity(name)["canonical_name"]) or {}).get("lifecycle", {}).get(
            "current_state"
        )
        lifecycle = _lifecycle(theme, previous_state)
        roles = _roles(context, name)
        theme_support.append(
            {
                "theme_name": name,
                "theme_rank": rank,
                "objective_strength": strength,
                "theme_identity": identity(name),
                "related_parent_history": previous_themes.get(identity(name)["parent"]),
                "41_factors": factors,
                "score_support": score_components(theme, factors),
                "lifecycle": lifecycle,
                "core_stocks": roles,
                "next_day_validation": _validation_points(context, name),
                "uncertainties": _uncertainties(factors, roles),
                "candidate_only": True,
            }
        )
    formal, formal_manifest = load_previous_formal(root, target)
    prior_validation = validate_formal_hypotheses(formal, formal_manifest, market)
    upstream = {name: (value.get("data_quality") or {}).get("status", "UNAVAILABLE") for name, value in (("market_packet", market), ("review_context", context))}
    support_quality = "PARTIAL_WITH_UPSTREAM_FAILURE" if any(value in {"FAIL", "INVALID"} for value in upstream.values()) else "PASS" if all(value in {"PASS", "EMPTY_VALID"} for value in upstream.values()) else "PARTIAL"
    packet = {
        "meta": {
            "schema_version": "formal_review_support.1",
            "trade_date": target.isoformat(),
            "data_role": "OBJECTIVE_SUPPORT_ONLY",
            "final_judgement_owner": "chatgpt",
        },
        "source_manifest": {
            "review_context": _manifest(context_path, context),
            "market_packet": _manifest(market_path, market),
            "previous_support_date": (previous or {}).get("meta", {}).get("trade_date"),
            "previous_formal_review": formal_manifest,
        },
        "theme_support": theme_support,
        "previous_day_validation": prior_validation,
        "data_quality": {"status": support_quality, "upstream": upstream},
        "objective_support_hypotheses": {"kind": "OBJECTIVE_SUPPORT_HYPOTHESIS", "formal_hit_rate_eligible": False, "records": [check for theme in (previous or {}).get("theme_support", []) for check in theme.get("next_day_validation", [])]},
        "factor_catalog": [
            {"factor_id": factor_id, "factor_name": name}
            for factor_id, name in DRIVER_TYPES.items()
        ],
        "constraints": {
            "no_reason_from_price_only": True,
            "tier4_cannot_confirm": True,
            "support_is_not_formal_review": True,
        },
    }
    schema = _read(root / "schemas" / "formal_review_support.schema.json")
    Draft202012Validator(schema).validate(packet)
    output = root / "data" / "formal_review_support"
    output.mkdir(parents=True, exist_ok=True)
    path = output / f"{target.isoformat()}.json"
    path.write_text(json.dumps(packet, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"packet": packet, "path": str(path)}


def validate_formal_review_record(
    payload: dict[str, Any], *, schema_root: Path | None = None
) -> None:
    if schema_root is not None:
        schema = _read(schema_root / "schemas" / "formal_review_record.schema.json")
        Draft202012Validator(schema).validate(payload)
    review_date = str(payload.get("date") or "")[:10]
    for theme in payload.get("main_themes") or []:
        scores = theme.get("scores") or {}
        aliases = {
            "base_logic_score": "base_logic",
            "realization_score": "realization",
            "expectation_gap_score": "expectation_gap",
            "continuity_score": "continuity",
            "market_confirmation_score": "market_confirmation",
            "risk_deduction": "risk_deduction",
        }
        for alias, component in aliases.items():
            if alias in theme and theme.get(alias) != (scores.get(component) or {}).get("raw_score"):
                raise ValueError(f"{alias} must equal scores.{component}.raw_score")
        if "total_score" in theme and theme.get("total_score") != scores.get("total_score"):
            raise ValueError("total_score must equal scores.total_score")
        if "rating" in theme and theme.get("rating") != scores.get("rating"):
            raise ValueError("rating must equal scores.rating")
        lifecycle = theme.get("lifecycle") or {}
        if "previous_lifecycle" in theme and theme.get("previous_lifecycle") != lifecycle.get(
            "previous_state"
        ):
            raise ValueError("previous_lifecycle must equal lifecycle.previous_state")
        factors = theme.get("41_factors") or []
        ids = [row.get("factor_id") for row in factors]
        if ids != list(range(1, 42)):
            raise ValueError("each formal theme must contain ordered factor_id 1..41 exactly once")
        for row in factors:
            if DRIVER_TYPES[row["factor_id"]] != row.get("factor_name"):
                raise ValueError("factor_id and factor_name mismatch")
            if row.get("status") == "CONFIRMED" and not row.get("evidence"):
                raise ValueError("CONFIRMED factor requires evidence")
            evidence = row.get("evidence") or []
            if row.get("status") == "CONFIRMED" and not any(
                item.get("tier", 4) <= 3 for item in evidence
            ):
                raise ValueError("Tier 4 evidence alone cannot confirm a factor")
            if any(str(item.get("source_date") or "")[:10] > review_date for item in evidence):
                raise ValueError("formal review evidence cannot be future-dated")


def _factor_evaluation(evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_factor: dict[int, list[dict[str, Any]]] = {}
    for row in evidence:
        factor_id = row.get("factor_id") or FACTOR_BY_CATEGORY.get(str(row.get("category") or ""))
        if factor_id:
            by_factor.setdefault(factor_id, []).append(row)
        if row.get("kind") == "policy":
            by_factor.setdefault(5, []).append(row)
    output = []
    for factor_id, name in DRIVER_TYPES.items():
        rows = by_factor.get(factor_id, [])
        eligible = [row for row in rows if row.get("tier", 4) <= 3]
        output.append(
            {
                "factor_id": factor_id,
                "factor_name": name,
                "evidence_domain": evidence_domain(factor_id),
                "status": "CONFIRMED" if any(row.get("evaluation_status", "CONFIRMED") == "CONFIRMED" for row in eligible) else "PARTIAL" if eligible else "UNCONFIRMED",
                "evidence": eligible,
                "confidence": "HIGH"
                if any(row.get("tier") == 1 for row in eligible)
                else "MEDIUM"
                if eligible
                else "NONE",
                "reason": "same-date theme-linked evidence available"
                if eligible
                else "no same-date qualifying theme-linked evidence",
            }
        )
    return output


def _evidence(market: dict[str, Any], target: date) -> list[dict[str, Any]]:
    output = []
    for kind, section in (("announcement", "announcements"), ("policy", "policies")):
        for row in (market.get(section) or {}).get("records") or []:
            source_date = str(row.get("published_at") or "")[:10]
            if source_date != target.isoformat():
                continue
            level = str(row.get("evidence_level") or "D")
            output.append(
                {
                    "kind": kind,
                    "category": row.get("category"),
                    "source": row.get("source") or row.get("agency"),
                    "source_type": row.get("source_type") or "official",
                    "source_date": source_date,
                    "url": row.get("url"),
                    "tier": {"A": 1, "B": 2, "C": 3, "D": 4}.get(level, 4),
                    "confidence": "HIGH" if level == "A" else "MEDIUM" if level in {"B", "C"} else "LOW",
                    "related_themes": row.get("related_themes") or [],
                    "title": row.get("title"),
                    "evaluation_status": "PARTIAL",
                }
            )
    return output


def _score_support(theme, factors):
    return score_components(theme, factors)


def _rubric(max_score, raw_score, subcomponents, reason):
    return {
        "raw_score": round(raw_score, 4) if raw_score is not None else None,
        "available_score": max_score if raw_score is not None else 0,
        "max_score": max_score,
        "subcomponents": subcomponents,
        "evidence": [],
        "reason": reason,
    }


def _lifecycle(theme: dict[str, Any], previous: str | None) -> dict[str, Any]:
    strength = _number(theme.get("strength")) or 0
    change = _number(theme.get("strength_change_1d"))
    if previous is None:
        current = "VALIDATION" if strength >= 60 else "GERMINATION" if strength >= 45 else "MENG_LONG"
    elif previous in {"MENG_LONG", "GERMINATION"} and strength >= 60 and (change or 0) >= 0:
        current = "VALIDATION"
    elif previous == "VALIDATION" and strength >= 75 and (change or 0) >= 5:
        current = "MAIN_UP"
    elif previous == "MAIN_UP" and change is not None and change <= -10:
        current = "HIGH_VOLATILITY"
    elif previous == "DIFFUSION" and strength >= 75 and (change or 0) >= 5:
        current = "SECONDARY_MAIN_UP"
    elif previous == "REALIZATION" and change is not None and change >= 8:
        current = "REPAIR"
    elif strength < 30:
        current = "FALSIFIED"
    else:
        current = previous
    return {
        "previous_state": previous,
        "current_state": current,
        "transition_reason": f"strength={strength}, change_1d={change}",
        "positive_evidence": ["objective theme strength"] if strength >= 60 else [],
        "negative_evidence": ["objective theme strength below 30"] if strength < 30 else [],
        "confidence": "MEDIUM" if change is not None else "LOW",
    }


def _roles(context: dict[str, Any], theme: str) -> list[dict[str, Any]]:
    row = next((item for item in context.get("core_theme_roles") or [] if item.get("theme") == theme), {})
    capital_rows = (context.get("capital_preference") or {}).get(
        "stock_capital_preference"
    ) or []
    capital_by_code = {
        item.get("ts_code"): item
        for item in capital_rows
        if theme in (item.get("themes") or [])
    }
    output = []
    for key, role in (
        ("leader_candidate", "LEADER"),
        ("capacity_candidate", "CAPACITY"),
        ("trend_leader", "TREND_LEADER"),
        ("elasticity", "ELASTICITY"),
        ("catch_up", "CATCH_UP"),
    ):
        candidate = row.get(key)
        if not candidate:
            continue
        capital = capital_by_code.get(candidate.get("ts_code")) or {}
        output.append(
            {
                "code": candidate.get("ts_code"),
                "name": candidate.get("stock_name"),
                "role": role,
                "role_score": candidate.get("role_candidate_score"),
                "capital_preference_score": capital.get(
                    "stock_capital_preference_score"
                ),
                "role_confidence": "MEDIUM",
                "reason": candidate.get("why_watch") or candidate.get("all_role_candidates") or [],
                "confirmed_evidence": [],
                "unconfirmed_claims": ["objective role candidate; formal role not assigned"],
            }
        )
    return output


def _validation_points(context: dict[str, Any], theme: str) -> list[dict[str, Any]]:
    rows = [row for row in context.get("next_day_plan") or [] if row.get("theme") == theme]
    return [
        {
            "validation_point": str(condition),
            "strengthening_condition": str(condition),
            "weakening_condition": "objective condition is not met",
            "falsification_condition": "theme and core stock evidence both fail",
        }
        for row in rows
        for condition in row.get("observation_conditions") or []
    ]


def _previous_day_validation(root, target, market, previous):
    return validate_formal_hypotheses(previous or {}, {}, market)


def validate_formal_hypotheses(formal, manifest, market=None):
    records = []
    for theme in formal.get("main_themes", []):
        for check in theme.get("next_day_validation", []):
            record = {"hypothesis": check.get("validation_point"), "expected_condition": check.get("strengthening_condition"), "actual_result": None, "result": "NOT_EVALUABLE", "evidence": [], "reason": "No machine-readable predicate; free-text conditions require explicit evaluation", "hypothesis_kind": "FORMAL_REVIEW_HYPOTHESIS"}
            predicate = check.get("predicate") or {}
            if predicate and market:
                allowed = {"change_pct", "amount", "rise_count", "fall_count", "limit_up_count", "limit_down_count"}
                key = predicate.get("field")
                rows = market.get("themes", []) + market.get("industries", [])
                row = next((r for r in rows if (r.get("theme_name") or r.get("industry_name") or r.get("name")) == theme["theme_name"]), {})
                actual, threshold = _number(row.get(key)), _number(predicate.get("threshold"))
                if key in allowed and actual is not None and threshold is not None and predicate.get("operator") in {"gte", "lte"}:
                    passed = actual >= threshold if predicate["operator"] == "gte" else actual <= threshold
                    record.update(actual_result=actual, result="CONFIRMED" if passed else "FAILED", evidence=[{"source": "MarketPacket", "source_date": (market.get("meta") or {}).get("trade_date"), "field": key, "value": actual}], reason="evaluated exact formal predicate")
            records.append(record)
    return _validation_summary(records) | {"status": "FORMAL_REVIEW_HYPOTHESES_LOADED" if formal else "PREVIOUS_FORMAL_REVIEW_UNAVAILABLE", "source": manifest, "hypothesis_kind": "FORMAL_REVIEW_HYPOTHESIS"}


def _validation_summary(rows):
    counts = {status: sum(row.get("result") == status for row in rows) for status in ("CONFIRMED", "PARTIAL", "FAILED", "NOT_EVALUABLE")}
    evaluable = counts["CONFIRMED"] + counts["PARTIAL"] + counts["FAILED"]
    return {
        "records": rows,
        "prediction_count": len(rows),
        "confirmed_count": counts["CONFIRMED"],
        "partial_count": counts["PARTIAL"],
        "failed_count": counts["FAILED"],
        "not_evaluable_count": counts["NOT_EVALUABLE"],
        "hit_rate": counts["CONFIRMED"] / evaluable if evaluable else None,
        "weighted_hit_rate": (counts["CONFIRMED"] + counts["PARTIAL"] * 0.5) / evaluable if evaluable else None,
    }


def _uncertainties(factors, roles):
    output = []
    if not any(row["status"] == "CONFIRMED" for row in factors):
        output.append("no theme-linked qualifying fundamental factor confirmed")
    if not roles:
        output.append("no objective core-stock role candidate")
    return output


def _previous_support(root: Path, target: date):
    paths = sorted((root / "data" / "formal_review_support").glob("????-??-??.json"))
    paths = [path for path in paths if path.stem < target.isoformat()]
    if not paths:
        return None
    days = load_trading_calendar(target, cache_root=root / "data" / "reference")
    previous = sorted(row.cal_date for row in days if row.is_open and row.cal_date < target)
    if not previous:
        return None
    path = root / "data" / "formal_review_support" / f"{previous[-1].isoformat()}.json"
    return _read(path) if path.is_file() else None


def _manifest(path, payload):
    return {
        "path": path.relative_to(path.parents[2]).as_posix(),
        "source_date": str((payload.get("meta") or {}).get("trade_date") or "")[:10],
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def _require_date(payload, target, name):
    actual = str((payload.get("meta") or {}).get("trade_date") or "")[:10]
    if actual != target.isoformat():
        raise ValueError(f"{name} date mismatch: expected {target.isoformat()}, got {actual}")


def _number(value):
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _read(path):
    return json.loads(path.read_text(encoding="utf-8"))
