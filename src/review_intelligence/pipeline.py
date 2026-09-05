from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
from jsonschema import Draft202012Validator

from src.inflection.history import DailyHistoryRepository
from src.review_intelligence.helpers import mean, number, stock_code
from src.review_intelligence.market import compute_cycle_features, compute_market_operability
from src.review_intelligence.roles import build_chip_candidates, build_role_candidates, compute_money_effects, detect_catalyst_fatigue
from src.review_intelligence.storage import persist_review_intelligence
from src.review_intelligence.styles import compute_style_rankings
from src.review_intelligence.themes import compute_concentration, score_themes, theme_change_counts
from src.storage.fact_store import FactStore


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class ReviewIntelligencePipeline:
    def __init__(self, root: Path = PROJECT_ROOT, *, history_repository: DailyHistoryRepository | None = None):
        self.root = root
        self.fact_store = FactStore(root / "data" / "facts")
        self.history = history_repository or DailyHistoryRepository(root, fact_store=self.fact_store)
        self.database_path = root / "data" / "a_share_review.db"

    def run(self, target: date) -> dict[str, Any]:
        history = _latest_rows(self.history.query(target - timedelta(days=45), target))
        history = history[history["trade_date"].astype(str).str[:10] <= target.isoformat()].copy()
        current = history[history["trade_date"].astype(str).str[:10] == target.isoformat()].copy()
        if current.empty:
            raise RuntimeError(f"daily facts unavailable for {target.isoformat()}")
        metadata = self.history.stock_metadata(target)
        market, market_source = self._load_market_packet(target, history, metadata)
        inflections = self._load_inflections(target)
        auction = self._load_auction(target)
        previous = self._previous_states(target)
        raw_themes = market.get("themes") or _industry_themes(current, metadata)
        announcement_counts = _announcement_counts(raw_themes, market)
        official_scores = _official_theme_scores(market)
        theme_rows = score_themes(
            raw_themes, inflections, announcement_counts, official_scores,
            previous["theme_1d"], previous["theme_5d"], previous["theme_20d"],
        )
        changes = theme_change_counts(theme_rows, previous["theme_1d"])
        concentration = compute_concentration(theme_rows)
        sector_concentration = compute_concentration(market.get("industries") or [])
        overview = dict(market.get("market_overview") or {})
        overview.update({key: value for key, value in (market.get("limit_up_down") or {}).items() if key not in overview})
        operability = compute_market_operability(
            overview, market.get("indices") or [], concentration.get("theme_concentration_score"),
            sector_concentration.get("theme_concentration_score"),
        )
        cycle = compute_cycle_features(overview, market.get("stocks") or [], changes)
        stock_lookup = _stock_lookup(current, metadata, market.get("stocks") or [])
        styles = compute_style_rankings(
            current, history, metadata, market.get("stocks") or [], inflections,
            previous["style_1d"], previous["style_5d"], previous["style_20d"],
        )
        roles = build_role_candidates(
            theme_rows, stock_lookup, inflections, auction,
            previous["role_1d"], previous["role_5d"], previous["role_20d"],
        )
        money = compute_money_effects(roles, theme_rows)
        chips = build_chip_candidates(
            inflections, roles, previous["chip_1d"], previous["chip_5d"], previous["chip_20d"]
        )
        fatigue_events, fatigue_coverage = self._catalyst_responses(target, history)
        fatigue = detect_catalyst_fatigue(fatigue_events)
        next_day = _next_day_plan(roles, chips, theme_rows)
        checks = _quality_checks(current, market_source, market, inflections, auction, theme_rows, roles, previous, fatigue_coverage)
        quality_status = "PASS" if all(row["passed"] for row in checks) else "PARTIAL"
        packet = {
            "meta": {
                "schema_version": "review_intelligence_packet.1", "trade_date": target.isoformat(),
                "as_of": f"{target.isoformat()}T15:05:00+08:00", "data_role": "OBJECTIVE_DATA",
                "final_judgement_owner": "chatgpt",
            },
            "market_operability": operability,
            "cycle_feature_vector": cycle["cycle_feature_vector"],
            "cycle_candidates": cycle["cycle_candidates"],
            "style_strength_ranking": styles,
            "theme_concentration": concentration,
            "theme_features": theme_rows,
            "role_candidates": roles,
            "money_effect_features": money,
            "trend_chip_candidates": chips,
            "positive_catalyst_fatigue": fatigue,
            "next_day_plan_candidates": next_day,
            "objective_factor_features": _factor_features(market),
            "previous_hypothesis_validation": _previous_hypothesis_context(self.root, target, market),
            "risk_and_falsification_candidates": _risk_candidates(market, inflections),
            "historical_changes": {
                "cycle_feature_change_1d": _dict_change(cycle["cycle_feature_vector"], previous["cycle_1d"]),
                "cycle_feature_change_5d": _dict_change(cycle["cycle_feature_vector"], previous["cycle_5d"]),
                "cycle_feature_change_20d": _dict_change(cycle["cycle_feature_vector"], previous["cycle_20d"]),
                "market_operability_change_1d": _difference(operability.get("market_operability_score"), previous["operability_1d"]),
                "market_operability_change_5d": _difference(operability.get("market_operability_score"), previous["operability_5d"]),
                "market_operability_change_20d": _difference(operability.get("market_operability_score"), previous["operability_20d"]),
            },
            "data_quality": {
                "status": quality_status, "checks": checks,
                "known_gaps": [
                    "historical theme snapshots are unavailable before Market Packet archives; industry aggregation is used as a labeled proxy",
                    "full-market market-cap and turnover-rate coverage is incomplete",
                    "catalyst fatigue remains unavailable until two comparable positive events have complete forward response windows",
                ],
            },
        }
        persist_review_intelligence(target, packet, fact_store=self.fact_store, database_path=self.database_path)
        compact = _compact(packet)
        output = self.root / "data" / "review_intelligence"
        output.mkdir(parents=True, exist_ok=True)
        full_path = output / f"{target.isoformat()}.json"
        compact_path = output / f"{target.isoformat()}_compact.json"
        full_path.write_text(json.dumps(packet, ensure_ascii=False, indent=2), encoding="utf-8")
        compact_path.write_text(json.dumps(compact, ensure_ascii=False, indent=2), encoding="utf-8")
        Draft202012Validator(_schema(self.root, "review_intelligence_packet.schema.json")).validate(packet)
        Draft202012Validator(_schema(self.root, "review_intelligence_compact.schema.json")).validate(compact)
        return {"packet": packet, "compact": compact, "paths": {"full": str(full_path), "compact": str(compact_path)}}

    def _load_market_packet(self, target, history, metadata):
        path = self.root / "data" / "market_packets" / f"{target.isoformat()}.json"
        if path.is_file():
            packet = _read(path)
            if str(packet.get("meta", {}).get("trade_date")) != target.isoformat():
                raise ValueError("market packet date mismatch")
            return packet, "MARKET_PACKET"
        return _fallback_market_packet(target, history, metadata), "INDUSTRY_PROXY"

    def _load_inflections(self, target):
        rows = self.fact_store.read_dataset("inflection_daily", target)
        if not rows:
            path = self.root / "data" / "inflection" / f"{target.isoformat()}.json"
            rows = _read(path).get("candidates", []) if path.is_file() else []
        return {str(row.get("ts_code")): row for row in rows if row.get("ts_code")}

    def _load_auction(self, target):
        path = self.root / "data" / "auction_packets" / f"{target.isoformat()}_compact.json"
        rows = _read(path).get("stock_auction_ranking", []) if path.is_file() else []
        return {str(row.get("ts_code")): row for row in rows if row.get("ts_code")}

    def _previous_states(self, target):
        folder = self.root / "data" / "review_intelligence"
        dates = sorted(path.stem for path in folder.glob("????-??-??.json") if path.stem < target.isoformat())
        def load(offset):
            return _read(folder / f"{dates[-offset]}.json") if len(dates) >= offset else {}
        one, five, twenty = load(1), load(5), load(20)
        return {
            "theme_1d": {row["theme_name"]: row.get("theme_inflection_score") for row in one.get("theme_features", [])},
            "theme_5d": {row["theme_name"]: row.get("theme_inflection_score") for row in five.get("theme_features", [])},
            "theme_20d": {row["theme_name"]: row.get("theme_inflection_score") for row in twenty.get("theme_features", [])},
            "style_1d": {row["style"]: row.get("style_strength_score") for row in one.get("style_strength_ranking", [])},
            "style_5d": {row["style"]: row.get("style_strength_score") for row in five.get("style_strength_ranking", [])},
            "style_20d": {row["style"]: row.get("style_strength_score") for row in twenty.get("style_strength_ranking", [])},
            "role_1d": {f"{row['theme']}:{row['ts_code']}": row.get("role_scores", {}) for row in one.get("role_candidates", [])},
            "role_5d": {f"{row['theme']}:{row['ts_code']}": row.get("role_scores", {}) for row in five.get("role_candidates", [])},
            "role_20d": {f"{row['theme']}:{row['ts_code']}": row.get("role_scores", {}) for row in twenty.get("role_candidates", [])},
            "chip_1d": {row["ts_code"]: row.get("chip_health_feature_score") for row in one.get("trend_chip_candidates", [])},
            "chip_5d": {row["ts_code"]: row.get("chip_health_feature_score") for row in five.get("trend_chip_candidates", [])},
            "chip_20d": {row["ts_code"]: row.get("chip_health_feature_score") for row in twenty.get("trend_chip_candidates", [])},
            "cycle_1d": one.get("cycle_feature_vector", {}),
            "cycle_5d": five.get("cycle_feature_vector", {}),
            "cycle_20d": twenty.get("cycle_feature_vector", {}),
            "operability_1d": one.get("market_operability", {}).get("market_operability_score"),
            "operability_5d": five.get("market_operability", {}).get("market_operability_score"),
            "operability_20d": twenty.get("market_operability", {}).get("market_operability_score"),
        }

    def _catalyst_responses(self, target, history):
        # Phase 1 only consumes already computed response facts; it never infers missing forward returns.
        path = self.root / "data" / "facts" / "dataset=catalyst_price_response" / f"trade_date={target.isoformat()}"
        parts = sorted(path.glob("*.parquet"))
        if not parts:
            return [], "UNAVAILABLE"
        rows = pd.read_parquet(parts[-1]).to_dict("records")
        return rows, "AVAILABLE"


def _compact(packet):
    return {
        "meta": packet["meta"] | {"schema_version": "review_intelligence_compact.1"},
        "market_operability": packet["market_operability"],
        "cycle_candidates": packet["cycle_candidates"],
        "cycle_feature_vector": packet["cycle_feature_vector"],
        "style_strength_ranking": packet["style_strength_ranking"][:16],
        "theme_concentration": packet["theme_concentration"],
        "top_theme_features": [_compact_theme(row) for row in packet["theme_features"][:15]],
        "role_candidates": packet["role_candidates"][:40],
        "money_effect_features": packet["money_effect_features"],
        "trend_chip_candidates": packet["trend_chip_candidates"][:20],
        "positive_catalyst_fatigue": packet["positive_catalyst_fatigue"][:20],
        "next_day_plan_candidates": packet["next_day_plan_candidates"],
        "objective_factor_features": packet["objective_factor_features"],
        "previous_hypothesis_validation": packet["previous_hypothesis_validation"],
        "risk_and_falsification_candidates": packet["risk_and_falsification_candidates"][:20],
        "historical_changes": packet["historical_changes"],
        "data_quality": packet["data_quality"],
    }


def _compact_theme(row):
    fields = ("theme_name", "theme_return", "top_stock_return", "theme_breadth", "theme_amount", "theme_amount_change", "limit_up_count", "failed_limit_count", "leader_strength", "capacity_strength", "trend_leader_strength", "catch_up_strength", "theme_volume_anomaly", "theme_inflection_score", "official_catalyst_count", "evidence_A_count", "evidence_B_count", "previous_review_score", "score_change", "score_change_1d", "score_change_5d", "score_change_20d", "quality_status")
    return {field: row.get(field) for field in fields}


def _next_day_plan(roles, chips, themes):
    theme_rank = {row["theme_name"]: index for index, row in enumerate(themes)}
    chip_map = {row["ts_code"]: row for row in chips}
    priority = {"LEADER_CANDIDATE": 0, "CAPACITY_CANDIDATE": 1, "TREND_LEADER_CANDIDATE": 2, "ELASTICITY_CANDIDATE": 3, "CATCH_UP_CANDIDATE": 4, "FOLLOWER_CANDIDATE": 5}
    eligible = [row for row in roles if theme_rank.get(row["theme"], 99) < 15]
    ranked = sorted(eligible or roles, key=lambda row: (priority.get(row["role_candidate"], 9), theme_rank.get(row["theme"], 99), -row["role_candidate_score"]))
    output, seen = [], set()
    for row in ranked:
        if row["ts_code"] in seen:
            continue
        seen.add(row["ts_code"])
        checks = ["主题成交额排名是否进入或保持前3", "个股表现是否继续强于所属主题"]
        if row["role_candidate"] == "CAPACITY_CANDIDATE":
            checks.append("容量候选是否与主题高弹性股票同步走强")
        if row.get("auction_confirmation") is not None:
            checks.append("竞价成交额异常分是否继续高于历史基线")
        output.append({
            "ts_code": row["ts_code"], "stock_name": row.get("stock_name"), "theme": row["theme"],
            "role_candidate": row["role_candidate"],
            "why_watch": [f"主题客观排名第{theme_rank.get(row['theme'], 99) + 1}", f"角色候选分{row['role_candidate_score']:.2f}"] + ([f"筹码健康特征分{chip_map[row['ts_code']]['chip_health_feature_score']}"] if row["ts_code"] in chip_map and chip_map[row["ts_code"]].get("chip_health_feature_score") is not None else []),
            "next_day_objective_checks": checks, "candidate_only": True,
        })
        if len(output) == 20:
            break
    return output


def _quality_checks(current, market_source, market, inflections, auction, themes, roles, previous, fatigue):
    theme_return_coverage = sum(row.get("theme_return") is not None for row in themes) / len(themes) if themes else 0
    market_cap_coverage = sum(number(row.get("market_cap")) is not None for row in market.get("stocks") or [])
    turnover_coverage = sum(number(row.get("turnover_rate")) is not None for row in market.get("stocks") or [])
    checks = [
        {"name": "daily_market_coverage", "actual": len(current), "threshold": 5000, "passed": len(current) >= 5000},
        {"name": "market_packet_source", "actual": market_source, "threshold": "MARKET_PACKET", "passed": market_source == "MARKET_PACKET", "reason": "industry proxy used for historical replay" if market_source != "MARKET_PACKET" else ""},
        {"name": "theme_feature_count", "actual": len(themes), "threshold": 10, "passed": len(themes) >= 10},
        {"name": "role_candidate_count", "actual": len(roles), "threshold": 1, "passed": bool(roles)},
        {"name": "theme_return_coverage", "actual": theme_return_coverage, "threshold": .9, "passed": theme_return_coverage >= .9, "reason": "whole-theme returns are absent; top-stock returns are not substituted" if theme_return_coverage < .9 else ""},
        {"name": "market_cap_sample_count", "actual": market_cap_coverage, "threshold": 100, "passed": market_cap_coverage >= 100},
        {"name": "turnover_sample_count", "actual": turnover_coverage, "threshold": 100, "passed": turnover_coverage >= 100},
        {"name": "inflection_link", "actual": len(inflections), "threshold": 1, "passed": bool(inflections), "reason": "inflection facts unavailable" if not inflections else ""},
        {"name": "auction_link", "actual": len(auction), "threshold": 1, "passed": bool(auction), "reason": "auction facts are optional outside their available date" if not auction else ""},
        {"name": "history_1d", "actual": previous["operability_1d"] is not None, "threshold": True, "passed": previous["operability_1d"] is not None},
        {"name": "history_5d", "actual": previous["operability_5d"] is not None, "threshold": True, "passed": previous["operability_5d"] is not None},
        {"name": "history_20d", "actual": previous["operability_20d"] is not None, "threshold": True, "passed": previous["operability_20d"] is not None},
        {"name": "catalyst_response_history", "actual": fatigue, "threshold": "AVAILABLE", "passed": fatigue == "AVAILABLE", "reason": "two comparable catalyst response windows are not available" if fatigue != "AVAILABLE" else ""},
    ]
    return checks


def _fallback_market_packet(target, history, metadata):
    current = history[history["trade_date"].astype(str).str[:10] == target.isoformat()].copy()
    dates = sorted(history["trade_date"].astype(str).str[:10].unique())
    previous = history[history["trade_date"].astype(str).str[:10] == dates[-2]] if len(dates) >= 2 else pd.DataFrame()
    current_amount, previous_amount = current["amount"].sum(), previous["amount"].sum() if not previous.empty else None
    current["limit_up"] = current.apply(lambda row: _is_limit_up(row["ts_code"], row["pct_chg"]), axis=1)
    current["limit_down"] = current.apply(lambda row: _is_limit_down(row["ts_code"], row["pct_chg"]), axis=1)
    overview = {
        "trade_date": target.isoformat(), "total_market_turnover": number(current_amount),
        "previous_turnover": number(previous_amount),
        "turnover_delta_pct": (current_amount / previous_amount - 1) * 100 if previous_amount else None,
        "rise_count": int((current["pct_chg"] > 0).sum()), "fall_count": int((current["pct_chg"] < 0).sum()),
        "limit_up_count": int(current["limit_up"].sum()), "limit_down_count": int(current["limit_down"].sum()),
        "failed_limit_count": None, "seal_rate": None, "highest_board": _highest_board(history, target),
        "previous_limit_up_avg_change_pct": None, "large_loss_count": int((current["pct_chg"] <= -7).sum()),
    }
    top = current.sort_values(["limit_up", "amount"], ascending=False).head(250)
    stocks = []
    for row in top.to_dict("records"):
        meta = metadata.get(str(row["ts_code"]), {})
        stocks.append({
            "stock_code": str(row["ts_code"]).split(".")[0], "stock_name": meta.get("stock_name"),
            "industry": meta.get("industry"), "themes": [meta.get("industry")] if meta.get("industry") else [],
            "change_pct": number(row.get("pct_chg")), "amount": number(row.get("amount")),
            "close": number(row.get("close")), "limit_up": bool(row.get("limit_up")),
            "limit_down": bool(row.get("limit_down")), "board_count": 1 if row.get("limit_up") else 0,
            "market_cap": None, "turnover_rate": number(row.get("turnover_rate")),
        })
    return {"meta": {"trade_date": target.isoformat()}, "market_overview": overview, "limit_up_down": {}, "indices": [], "stocks": stocks, "themes": _industry_themes(current, metadata), "announcements": {"records": []}, "previous_review": {"themes": []}, "data_quality": {"status": "PARTIAL"}}


def _industry_themes(current, metadata):
    frame = current.copy()
    frame["industry"] = frame["ts_code"].map(lambda code: metadata.get(str(code), {}).get("industry"))
    rows = []
    for name, group in frame.dropna(subset=["industry"]).groupby("industry"):
        top = group.sort_values("pct_chg", ascending=False).head(10)
        gainers = [{"stock_code": row.ts_code, "stock_name": metadata.get(str(row.ts_code), {}).get("stock_name"), "change_pct": number(row.pct_chg), "amount": number(row.amount), "board_count": 1 if _is_limit_up(row.ts_code, row.pct_chg) else 0} for row in top.itertuples()]
        rows.append({
            "theme_name": str(name), "normalized_name": str(name), "code": None,
            "change_pct": mean(group["pct_chg"].tolist()), "rise_count": int((group["pct_chg"] > 0).sum()),
            "fall_count": int((group["pct_chg"] < 0).sum()), "limit_up_count": sum(_is_limit_up(row.ts_code, row.pct_chg) for row in group.itertuples()),
            "limit_down_count": sum(_is_limit_down(row.ts_code, row.pct_chg) for row in group.itertuples()),
            "failed_limit_count": None, "amount": number(group["amount"].sum()), "amount_change": None,
            "top_gainers": gainers, "top_losers": [], "leader_candidates": [row for row in gainers if (number(row.get("board_count")) or 0) >= 2],
            "capacity_candidates": sorted(gainers, key=lambda row: -(number(row.get("amount")) or 0))[:1],
            "catch_up_candidates": gainers[1:4], "source": "tushare.daily industry proxy", "quality": "PARTIAL",
        })
    return sorted(rows, key=lambda row: (-(row["change_pct"] or -100), row["theme_name"]))


def _announcement_counts(themes, market):
    result = {str(row.get("theme_name") or row.get("name")): {"A": 0, "B": 0} for row in themes}
    for record in market.get("announcements", {}).get("records", []):
        text = " ".join(str(record.get(key) or "") for key in ("title", "summary", "confirmed_fact"))
        level = str(record.get("evidence_level") or "B")
        for name in result:
            if name and name in text:
                result[name][level if level in ("A", "B") else "B"] += 1
    return result


def _factor_features(market):
    categories: dict[str, int] = {}
    evidence: dict[str, int] = {}
    for row in market.get("announcements", {}).get("records", []):
        category = str(row.get("category") or "other")
        level = str(row.get("evidence_level") or "UNRATED")
        categories[category] = categories.get(category, 0) + 1
        evidence[level] = evidence.get(level, 0) + 1
    agencies: dict[str, int] = {}
    policy_levels: dict[str, int] = {}
    for row in market.get("policies", {}).get("records", []):
        agency = str(row.get("agency") or "UNKNOWN")
        level = str(row.get("policy_level") or "UNKNOWN")
        agencies[agency] = agencies.get(agency, 0) + 1
        policy_levels[level] = policy_levels.get(level, 0) + 1
    return {
        "announcement_category_counts": categories,
        "announcement_evidence_counts": evidence,
        "policy_agency_counts": agencies,
        "policy_level_counts": policy_levels,
        "objective_only": True,
    }


def _previous_hypothesis_context(root, target, market):
    auction_path = root / "data" / "auction_packets" / f"{target.isoformat()}_compact.json"
    auction = _read(auction_path) if auction_path.is_file() else {}
    review_folder = root / "data" / "official_reviews"
    review_paths = sorted(path for path in review_folder.glob("????-??-??.json") if path.stem < target.isoformat())
    prior_review = _read(review_paths[-1]) if review_paths else None
    return {
        "market_packet_context": market.get("tomorrow_check_context") or {},
        "prior_official_review": {
            "status": "AVAILABLE" if prior_review else "UNAVAILABLE",
            "date": prior_review.get("date") if prior_review else None,
            "main_themes": prior_review.get("main_themes", []) if prior_review else [],
            "stocks": prior_review.get("stocks", []) if prior_review else [],
            "tomorrow_checks": prior_review.get("tomorrow_checks", []) if prior_review else [],
        },
        "auction_previous_mainline_validation": auction.get("previous_mainline_validation"),
        "auction_transition_status": auction.get("transition_status"),
    }


def _risk_candidates(market, inflections):
    rows = []
    for item in market.get("announcements", {}).get("risk_announcements", [])[:10]:
        rows.append({
            "entity": item.get("stock_code"), "type": "OFFICIAL_RISK_ANNOUNCEMENT",
            "fact": item.get("confirmed_fact") or item.get("summary") or item.get("title"),
            "evidence_level": item.get("evidence_level"), "candidate_only": True,
        })
    for code, item in inflections.items():
        if item.get("status") in {"DISTRIBUTION_WARNING", "TREND_BROKEN"}:
            rows.append({
                "entity": code, "type": item.get("status"), "fact": item.get("why_selected") or [],
                "evidence_level": "OBJECTIVE_MARKET_DATA", "candidate_only": True,
            })
        if len(rows) >= 30:
            break
    return rows


def _official_theme_scores(market):
    return {str(row.get("name")): number(row.get("score")) for row in market.get("previous_review", {}).get("themes", []) if row.get("name")}


def _stock_lookup(current, metadata, packet_stocks):
    result = {}
    for row in current.to_dict("records"):
        code = str(row["ts_code"])
        result[code] = dict(row) | metadata.get(code, {})
    for row in packet_stocks:
        code = stock_code(row.get("stock_code") or row.get("ts_code"))
        if code:
            result.setdefault(code, {}).update(row)
    return result


def _latest_rows(frame):
    if frame.empty:
        return frame
    output = frame.copy()
    output["trade_date"] = output["trade_date"].astype(str).str[:10]
    return output.drop_duplicates(["trade_date", "ts_code"], keep="last")


def _highest_board(history, target):
    dates = sorted(value for value in history["trade_date"].astype(str).str[:10].unique() if value <= target.isoformat())
    best = 0
    for _, group in history.groupby("ts_code"):
        changes = {str(row.trade_date)[:10]: number(row.pct_chg) for row in group.itertuples()}
        run = 0
        for day in reversed(dates):
            if _is_limit_up(str(group.iloc[0]["ts_code"]), changes.get(day)):
                run += 1
            else:
                break
        best = max(best, run)
    return best


def _is_limit_up(code, change):
    value = number(change)
    threshold = 29.5 if str(code).endswith(".BJ") else 19.5 if str(code).startswith(("300", "688")) else 9.5
    return value is not None and value >= threshold


def _is_limit_down(code, change):
    value = number(change)
    threshold = -29.5 if str(code).endswith(".BJ") else -19.5 if str(code).startswith(("300", "688")) else -9.5
    return value is not None and value <= threshold


def _difference(current, previous):
    left, right = number(current), number(previous)
    return left - right if left is not None and right is not None else None


def _dict_change(current, previous):
    return {key: _difference(value, previous.get(key)) for key, value in current.items()}


def _read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _schema(root, name):
    path = root / "schemas" / name
    return _read(path if path.is_file() else PROJECT_ROOT / "schemas" / name)
