from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ROLE_KEYS = {
    "LEADER_CANDIDATE": "leader_candidate",
    "CAPACITY_CANDIDATE": "capacity_candidate",
    "TREND_LEADER_CANDIDATE": "trend_leader",
    "ELASTICITY_CANDIDATE": "elasticity",
    "CATCH_UP_CANDIDATE": "catch_up",
}


class ReviewContextBuilder:
    def __init__(self, root: Path = PROJECT_ROOT):
        self.root = root

    def build(self, target: date) -> dict[str, Any]:
        market, market_path = self._required("market_packets", target)
        intelligence, intelligence_path = self._required("review_intelligence", target)
        inflection, inflection_path = self._required("inflection", target)
        auction, auction_path = self._required("auction_packets", target)
        inputs = {
            "market_packet": (market, market_path),
            "review_intelligence": (intelligence, intelligence_path),
            "inflection_scanner": (inflection, inflection_path),
            "auction_packet": (auction, auction_path),
        }
        for name, (payload, _) in inputs.items():
            actual = _trade_date(payload)
            if actual != target.isoformat():
                raise ValueError(f"{name} date mismatch: expected {target.isoformat()}, got {actual}")

        prior_review, prior_manifest = self._prior_official_review(target, market)
        roles = intelligence.get("role_candidates") or []
        risks = intelligence.get("risk_and_falsification_candidates") or []
        themes = intelligence.get("theme_features") or []
        chips = {row.get("ts_code"): row for row in intelligence.get("trend_chip_candidates") or []}
        packet = {
            "meta": {
                "schema_version": "review_context_packet.1", "trade_date": target.isoformat(),
                "as_of": f"{target.isoformat()}T15:05:00+08:00", "data_role": "OBJECTIVE_CONTEXT",
                "final_judgement_owner": "chatgpt",
            },
            "source_manifest": {
                **{name: _manifest(payload, path) for name, (payload, path) in inputs.items()},
                "prior_official_review": prior_manifest,
            },
            "market_environment": _market_environment(market, intelligence),
            "next_day_theme_candidates": _theme_candidates(themes, roles, risks),
            "medium_term_structure_candidates": _medium_term(themes, roles, risks, intelligence),
            "market_cycle_and_style": {
                "cycle_candidates": intelligence.get("cycle_candidates") or [],
                "cycle_feature_vector": intelligence.get("cycle_feature_vector") or {},
                "style_strength": intelligence.get("style_strength_ranking") or [],
                "style_change": _style_changes(intelligence.get("style_strength_ranking") or []),
                "historical_changes": intelligence.get("historical_changes") or {},
            },
            "core_theme_roles": _core_theme_roles(themes, roles),
            "inflection_candidates": _inflection_candidates(inflection, chips),
            "previous_hypothesis_validation": _previous_validation(market, intelligence, prior_review),
            "next_day_plan": _next_day_plan(intelligence, risks, inflection),
            "market_factors": intelligence.get("objective_factor_features") or {},
            "money_effect_structure": intelligence.get("money_effect_features") or {},
            "risk_and_falsification_candidates": risks,
            "auction_context": _auction_context(auction),
            "review_template_support": _template_support(),
        }
        packet["data_quality"] = _quality(inputs, prior_manifest, packet)
        compact = _compact(packet)
        _validate(self.root, "review_context_packet.schema.json", packet)
        _validate(self.root, "review_context_compact.schema.json", compact)
        output = self.root / "data" / "review_context"
        output.mkdir(parents=True, exist_ok=True)
        full_path = output / f"{target.isoformat()}.json"
        compact_path = output / f"{target.isoformat()}_compact.json"
        full_path.write_text(json.dumps(packet, ensure_ascii=False, indent=2), encoding="utf-8")
        compact_path.write_text(json.dumps(compact, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"packet": packet, "compact": compact, "paths": {"full": str(full_path), "compact": str(compact_path)}}

    def _required(self, folder: str, target: date) -> tuple[dict[str, Any], Path]:
        path = self.root / "data" / folder / f"{target.isoformat()}.json"
        if not path.is_file():
            raise FileNotFoundError(f"required {folder} input is unavailable: {path}")
        return _read(path), path

    def _prior_official_review(self, target: date, market: dict[str, Any]):
        folder = self.root / "data" / "official_reviews"
        paths = sorted(path for path in folder.glob("????-??-??.json") if path.stem < target.isoformat())
        if paths:
            payload = _read(paths[-1])
            actual = str(payload.get("date") or "")[:10]
            if actual >= target.isoformat():
                raise ValueError("prior official_review is not strictly historical")
            return payload, _manifest(payload, paths[-1]) | {"status": "AVAILABLE"}
        embedded = market.get("previous_review") or {}
        embedded_date = str(embedded.get("date") or "")[:10]
        if embedded_date and embedded_date < target.isoformat():
            return embedded, {
                "status": "FALLBACK_EMBEDDED_HISTORY", "data_date": embedded_date,
                "source": "market_packet.previous_review", "path": embedded.get("source_path"),
                "sha256": _digest(embedded),
            }
        return {}, {"status": "UNAVAILABLE", "data_date": None, "source": "official_reviews", "path": None, "sha256": None}


def _market_environment(market, intelligence):
    overview = market.get("market_overview") or {}
    limits = market.get("limit_up_down") or {}
    operability = intelligence.get("market_operability") or {}
    return {
        "total_turnover": overview.get("total_market_turnover"),
        "turnover_change_pct": overview.get("turnover_delta_pct"),
        "rise_count": overview.get("rise_count"), "fall_count": overview.get("fall_count"),
        "flat_count": overview.get("flat_count"), "limit_up_count": overview.get("limit_up_count"),
        "limit_down_count": overview.get("limit_down_count"),
        "failed_limit_count": overview.get("failed_limit_count"), "seal_rate": overview.get("seal_rate"),
        "highest_board": overview.get("highest_board"),
        "previous_limit_avg_return": overview.get("previous_limit_up_avg_change_pct"),
        "continuous_board_feedback": overview.get("previous_continuous_board_performance"),
        "promotion_rate": limits.get("promotion_rate"),
        "large_loss_count": limits.get("large_loss_count"),
        "high_level_loss_count": operability.get("high_level_loss_count"),
        "market_operability_score": operability.get("market_operability_score"),
        "market_operability_available_max": operability.get("available_max_score"),
        "operability_components": operability.get("feature_components") or {},
    }


def _theme_candidates(themes, roles, risks):
    role_groups = _roles_by_theme(roles)
    output = []
    for theme in themes[:15]:
        name = theme.get("theme_name")
        grouped = role_groups.get(name, {})
        output.append({
            "theme": name, "strength": theme.get("theme_inflection_score"),
            "strength_change_1d": theme.get("score_change_1d"),
            "strength_change_5d": theme.get("score_change_5d"),
            "breadth": theme.get("theme_breadth"), "amount": theme.get("theme_amount"),
            "amount_change": theme.get("theme_amount_change"),
            "leader_candidates": grouped.get("leader_candidate", []),
            "capacity_candidates": grouped.get("capacity_candidate", []),
            "risk": _theme_risks(name, grouped, risks), "candidate_only": True,
        })
    return output


def _medium_term(themes, roles, risks, intelligence):
    strong = [_theme_summary(row) for row in themes if (row.get("theme_inflection_score") or 0) >= 60][:15]
    trend = [row for row in roles if row.get("role_candidate") == "TREND_LEADER_CANDIDATE"][:20]
    repair = [_theme_summary(row) for row in themes if (row.get("score_change_1d") or 0) >= 8][:15]
    risk_names = {row.get("theme_name") for row in themes if (row.get("score_change_1d") or 0) <= -8}
    return {
        "strong_themes": strong, "trend_candidates": trend,
        "repair_candidates": repair,
        "risk_themes": [{"theme": name, "risk_facts": _theme_risks(name, {}, risks)} for name in sorted(value for value in risk_names if value)],
        "cycle_candidate_context": intelligence.get("cycle_candidates") or [],
        "candidate_only": True,
    }


def _core_theme_roles(themes, roles):
    grouped = _roles_by_theme(roles)
    output = []
    for theme in themes[:15]:
        name = theme.get("theme_name")
        item = {"theme": name, "theme_strength": theme.get("theme_inflection_score"), "candidate_only": True}
        for key in ROLE_KEYS.values():
            candidates = grouped.get(name, {}).get(key, [])
            item[key] = candidates[0] if candidates else None
        output.append(item)
    return output


def _inflection_candidates(inflection, chips):
    rows = sorted(
        inflection.get("candidates") or [],
        key=lambda row: (-(row.get("trend_inflection_score") or 0), -(row.get("score_change_1d") or 0)),
    )
    return [{
        "ts_code": row.get("ts_code"), "stock_name": row.get("stock_name"),
        "industry": row.get("industry"), "themes": row.get("themes") or [],
        "status_candidate": row.get("status"), "trend_score": row.get("trend_inflection_score"),
        "score_change_1d": row.get("score_change_1d"), "score_change_5d": row.get("score_change_5d"),
        "chip_health": chips.get(row.get("ts_code")),
        "breakout": {
            "type": row.get("breakout_type"), "volume_confirmation": row.get("breakout_volume_confirmation"),
            "hold_days": row.get("breakout_hold_days"), "hold_status": row.get("breakout_hold_status"),
            "failure": row.get("breakout_failure"),
        },
        "weekly_structure": {
            "breakout_type": row.get("weekly_breakout_type"), "wma5": row.get("wma5"),
            "wma10": row.get("wma10"), "wma20": row.get("wma20"),
            "slope_wma20": row.get("slope_wma20"),
        },
        "risk_flags": row.get("risk_flags") or [], "objective_reasons": row.get("why_selected") or [],
        "candidate_only": True,
    } for row in rows[:20]]


def _previous_validation(market, intelligence, prior_review):
    context = market.get("tomorrow_check_context") or {}
    changes = context.get("changes_vs_previous_day") or {}
    return {
        "review_date": prior_review.get("date"),
        "confirmed": _unique((changes.get("strengthened") or []) + (changes.get("expanded") or []) + (changes.get("realized") or [])),
        "weakened": _unique(changes.get("weakened") or []),
        "invalidated": _unique(changes.get("invalidated") or []),
        "new": _unique(changes.get("new") or []),
        "unevaluated_checks": context.get("checks") or [],
        "auction_validation": (intelligence.get("previous_hypothesis_validation") or {}).get("auction_previous_mainline_validation"),
        "source": "market_packet.tomorrow_check_context",
    }


def _next_day_plan(intelligence, risks, inflection):
    risk_by_code: dict[str, list[Any]] = {}
    for risk in risks:
        code = str(risk.get("entity") or "")
        risk_by_code.setdefault(code, []).append(risk)
    inflection_map = {row.get("ts_code"): row for row in inflection.get("candidates") or []}
    output = []
    for row in (intelligence.get("next_day_plan_candidates") or [])[:20]:
        code = row.get("ts_code")
        short_code = str(code or "").split(".")[0]
        inflection_row = inflection_map.get(code, {})
        conditions = row.get("next_day_objective_checks") or []
        risk_conditions = ["若所属主题客观强度明显下降，记录为观察条件未满足"]
        if inflection_row.get("breakout_type"):
            risk_conditions.append("若收盘重新跌破突破平台，记录突破失效")
        if risk_by_code.get(code) or risk_by_code.get(short_code):
            risk_conditions.append("核验正式风险公告中的限制条件是否继续成立")
        output.append({
            "ts_code": code, "stock_name": row.get("stock_name"), "theme": row.get("theme"),
            "role": row.get("role_candidate"), "role_candidate_score": row.get("role_candidate_score"),
            "observation_conditions": conditions, "risk_conditions": risk_conditions,
            "why_in_pool": row.get("why_watch") or [], "candidate_only": True,
        })
    return output


def _auction_context(auction):
    summary = auction.get("market_auction_summary") or {}
    return {
        "status": auction.get("data_quality", {}).get("status"),
        "watchlist_count": summary.get("watchlist_count"),
        "valid_auction_count": summary.get("valid_auction_count"),
        "checkpoint_coverage": summary.get("checkpoint_coverage"),
        "formal_opening_match_success_rate": summary.get("formal_opening_match_success_rate"),
        "volume_anomaly_candidates": (auction.get("volume_anomaly_candidates") or [])[:20],
        "conflicts": auction.get("conflicts") or [],
    }


def _template_support():
    return {
        "一、先给结论": ["market_environment", "market_cycle_and_style", "data_quality"],
        "二、市场环境": ["market_environment"],
        "三、下一交易日观察板块": ["next_day_theme_candidates"],
        "四、未来1-2周结构": ["medium_term_structure_candidates"],
        "五、市场周期与核心风格": ["market_cycle_and_style"],
        "六、核心主线与个股角色": ["core_theme_roles"],
        "七、趋势拐点与筹码": ["inflection_candidates"],
        "八、主线排名": ["next_day_theme_candidates"],
        "九、上涨因素": ["market_factors"],
        "十、昨日验证": ["previous_hypothesis_validation"],
        "十一、龙头/补涨/切换": ["core_theme_roles", "money_effect_structure"],
        "十二、风险": ["risk_and_falsification_candidates", "next_day_plan"],
        "十三、最终判断": ["source_manifest", "data_quality"],
    }


def _compact(packet):
    cycle = packet["market_cycle_and_style"]
    medium = packet["medium_term_structure_candidates"]
    return {
        "meta": packet["meta"] | {"schema_version": "review_context_compact.1"},
        "source_manifest": {key: {field: value.get(field) for field in ("status", "data_date", "quality_status", "sha256") if field in value} for key, value in packet["source_manifest"].items()},
        "market_environment": packet["market_environment"],
        "next_day_theme_candidates": [{
            **{key: row.get(key) for key in ("theme", "strength", "strength_change_1d", "strength_change_5d", "breadth", "amount", "amount_change", "risk", "candidate_only")},
            "leader_candidates": [_compact_role(item) for item in row.get("leader_candidates", [])[:3]],
            "capacity_candidates": [_compact_role(item) for item in row.get("capacity_candidates", [])[:3]],
        } for row in packet["next_day_theme_candidates"]],
        "medium_term_structure_candidates": {
            "strong_themes": medium["strong_themes"],
            "trend_candidates": [_compact_role(row) for row in medium["trend_candidates"][:15]],
            "repair_candidates": medium["repair_candidates"], "risk_themes": medium["risk_themes"],
            "cycle_candidate_context": medium["cycle_candidate_context"], "candidate_only": True,
        },
        "market_cycle_and_style": {
            "cycle_candidates": cycle["cycle_candidates"], "cycle_feature_vector": cycle["cycle_feature_vector"],
            "style_strength": [{key: row.get(key) for key in ("style", "return", "breadth", "amount_change", "limit_up_count", "style_strength_score", "style_change_1d", "style_change_5d", "style_change_20d", "coverage_status")} for row in cycle["style_strength"][:12]],
            "style_change": cycle["style_change"][:12], "historical_changes": cycle["historical_changes"],
        },
        "core_theme_roles": [{
            **{key: row.get(key) for key in ("theme", "theme_strength", "candidate_only")},
            **{key: _compact_role(row.get(key)) for key in ROLE_KEYS.values()},
        } for row in packet["core_theme_roles"]],
        "inflection_candidates": [_compact_inflection(row) for row in packet["inflection_candidates"][:15]],
        "previous_hypothesis_validation": packet["previous_hypothesis_validation"],
        "next_day_plan": packet["next_day_plan"], "market_factors": packet["market_factors"],
        "money_effect_structure": packet["money_effect_structure"],
        "risk_and_falsification_candidates": packet["risk_and_falsification_candidates"][:15],
        "auction_context": {
            **{key: packet["auction_context"].get(key) for key in ("status", "watchlist_count", "valid_auction_count", "checkpoint_coverage", "formal_opening_match_success_rate", "conflicts")},
            "volume_anomaly_candidates": packet["auction_context"].get("volume_anomaly_candidates", [])[:10],
        },
        "review_template_support": packet["review_template_support"], "data_quality": packet["data_quality"],
    }


def _quality(inputs, prior_manifest, packet):
    checks = []
    for name, (payload, _) in inputs.items():
        status = payload.get("data_quality", {}).get("status")
        checks.append({"name": f"{name}_quality", "actual": status, "threshold": "PASS", "passed": status == "PASS"})
    checks.extend([
        {"name": "historical_review_is_prior", "actual": prior_manifest.get("data_date"), "threshold": f"<{packet['meta']['trade_date']}", "passed": not prior_manifest.get("data_date") or prior_manifest["data_date"] < packet["meta"]["trade_date"]},
        {"name": "next_day_plan_limit", "actual": len(packet["next_day_plan"]), "threshold": 20, "passed": len(packet["next_day_plan"]) <= 20},
        {"name": "required_context_sections", "actual": len(packet["review_template_support"]), "threshold": 13, "passed": len(packet["review_template_support"]) == 13},
    ])
    return {
        "status": "PASS" if all(row["passed"] for row in checks) else "PARTIAL",
        "checks": checks,
        "known_gaps": [
            "Upstream PARTIAL statuses are preserved and never upgraded by context assembly.",
            "A prior official_review may fall back to Market Packet embedded history when no strictly earlier official file exists.",
        ],
    }


def _roles_by_theme(roles):
    output: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for row in roles:
        labels = row.get("all_role_candidates") or [row.get("role_candidate")]
        for label in labels:
            key = ROLE_KEYS.get(label)
            if key:
                output.setdefault(row.get("theme"), {}).setdefault(key, []).append(row)
    return output


def _compact_role(row):
    if not row:
        return None
    return {key: row.get(key) for key in (
        "ts_code", "stock_name", "theme", "role_candidate", "role_candidate_score",
        "role_score_change_1d", "role_score_change_5d", "auction_confirmation", "candidate_only",
    )}


def _compact_inflection(row):
    chip = row.get("chip_health") or {}
    return {
        **{key: row.get(key) for key in ("ts_code", "stock_name", "industry", "themes", "status_candidate", "trend_score", "score_change_1d", "score_change_5d", "breakout", "weekly_structure", "risk_flags", "objective_reasons", "candidate_only")},
        "chip_health": {key: chip.get(key) for key in ("chip_health_feature_score", "chip_health_change_1d", "pullback_volume_ratio", "amount_percentile", "turnover_percentile", "volatility_percentile", "breakout_hold", "risk_flags")},
    }


def _theme_risks(name, grouped, risks):
    codes = {row.get("ts_code") for rows in grouped.values() for row in rows} if grouped else set()
    short_codes = {str(code).split(".")[0] for code in codes if code}
    return [row for row in risks if row.get("entity") in codes or str(row.get("entity")) in short_codes or row.get("theme") == name][:10]


def _style_changes(styles):
    return [{
        "style": row.get("style"), "change_1d": row.get("style_change_1d"),
        "change_5d": row.get("style_change_5d"), "change_20d": row.get("style_change_20d"),
    } for row in styles]


def _theme_summary(row):
    return {
        "theme": row.get("theme_name"), "strength": row.get("theme_inflection_score"),
        "change_1d": row.get("score_change_1d"), "change_5d": row.get("score_change_5d"),
        "breadth": row.get("theme_breadth"), "amount": row.get("theme_amount"),
        "candidate_only": True,
    }


def _manifest(payload, path):
    return {
        "status": "AVAILABLE", "data_date": _trade_date(payload), "path": str(path),
        "quality_status": payload.get("data_quality", {}).get("status"), "sha256": _digest(payload),
    }


def _trade_date(payload):
    return str(payload.get("meta", {}).get("trade_date") or payload.get("trade_date") or payload.get("date") or "")[:10]


def _digest(payload):
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _unique(values):
    return list(dict.fromkeys(str(value) for value in values if value))


def _read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _validate(root, schema_name, payload):
    path = root / "schemas" / schema_name
    if not path.is_file():
        path = PROJECT_ROOT / "schemas" / schema_name
    Draft202012Validator(_read(path)).validate(payload)
