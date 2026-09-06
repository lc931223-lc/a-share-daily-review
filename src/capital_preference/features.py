from __future__ import annotations

from bisect import bisect_right
from collections import defaultdict
from typing import Any

import numpy as np
import pandas as pd

from src.review_intelligence.helpers import clamp, mean, number, percentile_rank, stock_code
from src.review_intelligence.styles import CONSUMER, CYCLICAL, FINANCIAL, TECH

THEME_WEIGHTS = {
    "fundamental_fit": 20,
    "position_advantage": 20,
    "capital_capacity": 20,
    "crowding_advantage": 15,
    "style_match": 15,
    "consensus_proxy": 10,
}
STOCK_WEIGHTS = {
    "position": 30,
    "capacity": 25,
    "crowding": 20,
    "style_match": 15,
    "theme_role": 10,
}
ROLE_LABELS = {
    "LEADER_CANDIDATE": "leader",
    "CAPACITY_CANDIDATE": "capacity",
    "TREND_LEADER_CANDIDATE": "trend_leader",
    "ELASTICITY_CANDIDATE": "elasticity",
    "CATCH_UP_CANDIDATE": "catch_up",
}


def build_features(
    *,
    target: str,
    daily: pd.DataFrame,
    metadata: dict[str, dict[str, Any]],
    market: dict[str, Any],
    intelligence: dict[str, Any],
    inflection: dict[str, Any],
    auction: dict[str, Any],
    theme_activity: dict[str, dict[str, Any]],
    stock_statistics: tuple[set[str], dict[str, dict[str, Any]]] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    theme_sources = [
        source
        for source in intelligence.get("theme_features") or []
        if str(source.get("theme_name") or "").strip()
    ]
    theme_names = {str(source.get("theme_name")).strip() for source in theme_sources}
    relevant_codes = {
        code for code, item in metadata.items() if str(item.get("industry") or "") in theme_names
    }
    for source in theme_sources:
        relevant_codes.update(_theme_candidate_codes(source))
    relevant_codes.update(
        code
        for row in intelligence.get("role_candidates") or []
        if (code := stock_code(row.get("ts_code")))
    )
    if stock_statistics is None:
        daily_codes = daily["ts_code"].astype(str)
        current, stats = _stock_statistics(
            daily[daily_codes.isin(relevant_codes)], target, metadata
        )
    else:
        current, stats = stock_statistics
    market_stocks = {
        stock_code(row.get("stock_code") or row.get("ts_code")): row
        for row in market.get("stocks") or []
        if stock_code(row.get("stock_code") or row.get("ts_code"))
    }
    inflections = {
        stock_code(row.get("ts_code")): row
        for row in inflection.get("candidates") or []
        if stock_code(row.get("ts_code"))
    }
    auctions = {
        stock_code(row.get("ts_code")): row
        for row in auction.get("stock_auction_summary") or []
        if stock_code(row.get("ts_code"))
    }
    roles_by_theme: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in intelligence.get("role_candidates") or []:
        roles_by_theme[str(row.get("theme") or "")].append(row)
    themes = []
    theme_members: dict[str, set[str]] = {}
    for source in theme_sources:
        name = str(source.get("theme_name") or "").strip()
        if not name:
            continue
        members = {
            code
            for code, item in metadata.items()
            if str(item.get("industry") or "") == name and code in current
        }
        members.update(_theme_candidate_codes(source))
        members.update(
            code for row in roles_by_theme.get(name, []) if (code := stock_code(row.get("ts_code")))
        )
        members = {code for code in members if code in stats}
        theme_members[name] = members
        themes.append(_theme_raw(name, source, members, stats, market_stocks, inflections))
    _add_theme_percentiles(themes)

    styles = {
        str(row.get("style")): number(row.get("style_strength_score"))
        for row in intelligence.get("style_strength_ranking") or []
    }
    announcements_available = _quality_available(market, "公告")
    policies_available = _quality_available(market, "政策")
    announcements = (market.get("announcements") or {}).get("records") or []
    policies = (market.get("policies") or {}).get("records") or []
    theme_rows = []
    for raw in themes:
        name = raw["theme"]
        members = theme_members[name]
        fundamental = _fundamental_component(
            name,
            members,
            announcements,
            policies,
            announcements_available,
            policies_available,
        )
        position = _position_component(raw)
        capacity = _capacity_component(raw)
        crowding = _crowding_component(raw)
        style = _style_component(name, members, styles, inflections)
        consensus = _consensus_component(theme_activity.get(name) or {})
        components = {
            "fundamental_fit": fundamental,
            "position_advantage": position,
            "capital_capacity": capacity,
            "crowding_advantage": crowding,
            "style_match": style,
            "consensus_proxy": consensus,
        }
        total = _total_score(components)
        theme_rows.append(
            {
                "theme": name,
                "capital_preference_score": total["score"],
                "available_max_score": total["available_points"],
                "component_coverage": total["coverage"],
                **components,
                "crowding_status": crowding["status"],
                "why_capital_selected": _theme_reasons(components),
                "member_count": len(members),
                "source_theme_strength": number(raw.get("source_theme_strength")),
                "candidate_only": True,
            }
        )

    stock_codes = set().union(*theme_members.values()) if theme_members else set()
    role_map = _role_map(roles_by_theme)
    stock_rows = _stock_scores(
        stock_codes,
        stats,
        metadata,
        market_stocks,
        inflections,
        auctions,
        role_map,
        theme_members,
        styles,
    )
    stock_map = {row["ts_code"]: row for row in stock_rows}
    for row in theme_rows:
        structure = _capital_structure(row["theme"], roles_by_theme, stock_map)
        row["capacity_structure"] = structure
        row["capital_structure_score"] = structure["capital_structure_score"]
    theme_rows.sort(key=lambda row: (-(row.get("capital_preference_score") or -1), row["theme"]))
    stock_rows.sort(
        key=lambda row: (-(row.get("stock_capital_preference_score") or -1), row["ts_code"])
    )
    return theme_rows, stock_rows


def _stock_statistics(daily, target, metadata):
    return build_stock_statistics_for_dates(daily, [target], metadata)[target]


def build_stock_statistics_for_dates(daily, targets, metadata):
    frame = daily.copy()
    frame["trade_date"] = frame["trade_date"].astype(str).str[:10]
    frame["ts_code"] = frame["ts_code"].astype(str)
    for column in ("close", "amount", "pct_chg"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    target_set = {str(target)[:10] for target in targets}
    target_values = np.array(sorted(target_set), dtype=object)
    latest = max(target_set)
    frame = frame[frame["trade_date"] <= latest].sort_values(["ts_code", "trade_date"])
    results = {target: (set(), {}) for target in target_set}
    for code, stock in frame.groupby("ts_code", sort=False):
        dates = stock["trade_date"].to_numpy()
        closes = stock["close"].to_numpy(dtype=float)
        amounts = stock["amount"].to_numpy(dtype=float)
        changes = stock["pct_chg"].to_numpy(dtype=float)
        candidate_indices = np.searchsorted(dates, target_values)
        for target, index in zip(target_values, candidate_indices, strict=True):
            if index >= len(dates) or dates[index] != target:
                continue
            close = number(closes[index])
            if close is None:
                continue
            current, stats = results[target]
            current.add(code)
            returns = {}
            for horizon in (20, 60, 120, 250):
                prior = number(closes[index - horizon]) if index >= horizon else None
                returns[horizon] = close / prior - 1 if prior not in (None, 0) else None
            close_window = closes[max(0, index - 249) : index + 1]
            amount_window = amounts[max(0, index - 59) : index + 1]
            change_window = changes[max(0, index - 19) : index + 1]
            stats[code] = {
                "ts_code": code,
                "stock_name": (metadata.get(code) or {}).get("stock_name"),
                "industry": (metadata.get(code) or {}).get("industry"),
                "return_20d": returns[20],
                "return_60d": returns[60],
                "return_120d": returns[120],
                "return_250d": returns[250],
                "historical_position_percentile": _array_percentile(close_window, close),
                "amount": number(amounts[index]),
                "average_amount_20d": _array_mean(amounts[max(0, index - 19) : index + 1]),
                "amount_percentile_60d": _array_percentile(amount_window, amounts[index]),
                "volatility_20d": _array_std(change_window),
                "change_pct": number(changes[index]),
            }
    return results


def _array_percentile(values, target):
    target = number(target)
    valid = values[np.isfinite(values)]
    if target is None or valid.size == 0:
        return None
    return float(100.0 * np.count_nonzero(valid <= target) / valid.size)


def _array_mean(values):
    valid = values[np.isfinite(values)]
    return float(valid.mean()) if valid.size else None


def _array_std(values):
    valid = values[np.isfinite(values)]
    return float(valid.std(ddof=1)) if valid.size > 1 else None


def _theme_raw(name, source, members, stats, market_stocks, inflections):
    rows = [stats[code] for code in members]
    core_codes = _theme_candidate_codes(source) | {code for code in members if code in inflections}
    core = [stats[code] for code in core_codes if code in stats]
    caps = [number(market_stocks.get(code, {}).get("market_cap")) for code in core_codes]
    caps = [value for value in caps if value is not None]
    return {
        "theme": name,
        "return_20d": mean([row["return_20d"] for row in rows]),
        "return_60d": mean([row["return_60d"] for row in rows]),
        "return_120d": mean([row["return_120d"] for row in rows]),
        "return_250d": mean([row["return_250d"] for row in rows]),
        "historical_position_percentile": mean(
            [row["historical_position_percentile"] for row in rows]
        ),
        "theme_amount": number(source.get("theme_amount") or source.get("amount"))
        or sum(number(row["amount"]) or 0 for row in rows),
        "core_market_cap": mean(caps),
        "core_average_amount": mean([row["average_amount_20d"] for row in core]),
        "capacity_stock_count": len(source.get("capacity_candidates") or []),
        "change_pct": number(source.get("theme_return") or source.get("change_pct")),
        "volatility": mean([row["volatility_20d"] for row in rows]),
        "turnover_history_percentile": mean(
            [number(inflections.get(code, {}).get("turnover_percentile_120d")) for code in members]
        ),
        "source_theme_strength": number(source.get("theme_inflection_score")),
    }


def _add_theme_percentiles(rows):
    fields = (
        "return_20d",
        "return_60d",
        "return_120d",
        "return_250d",
        "theme_amount",
        "core_market_cap",
        "core_average_amount",
        "capacity_stock_count",
        "change_pct",
        "volatility",
    )
    for field in fields:
        values = [row.get(field) for row in rows]
        for row in rows:
            row[f"{field}_rank"] = (
                0.0
                if field == "capacity_stock_count" and row.get(field) == 0
                else percentile_rank(values, row.get(field))
            )


def _fundamental_component(name, members, announcements, policies, announcement_ok, policy_ok):
    matched = [row for row in announcements if _event_matches(row, name, members)]
    matched_policies = [row for row in policies if _policy_matches(row, name)]
    evidence_a = sum(str(row.get("evidence_level")) == "A" for row in matched)
    earnings = sum(str(row.get("category")) == "earnings" for row in matched)
    price_change = sum(
        str(row.get("category")) in {"price_increase", "product"}
        or any(word in str(row.get("title") or "") for word in ("涨价", "提价", "价格调整"))
        for row in matched
    )
    features = {
        "official_evidence": (min(evidence_a / 3, 1), 8) if announcement_ok else (None, 8),
        "earnings": (min(earnings / 2, 1), 4) if announcement_ok else (None, 4),
        "price_change": (min(price_change, 1), 3) if announcement_ok else (None, 3),
        "policy": (min(len(matched_policies) / 2, 1), 3) if policy_ok else (None, 3),
        "cycle_data": (None, 2),
    }
    return _component(
        features,
        20,
        {
            "announcement_count": len(matched) if announcement_ok else None,
            "evidence_A_count": evidence_a if announcement_ok else None,
            "earnings_count": earnings if announcement_ok else None,
            "price_change_count": price_change if announcement_ok else None,
            "policy_count": len(matched_policies) if policy_ok else None,
            "cycle_data": None,
        },
    )


def _position_component(row):
    features = {
        "return_20d": (_pct(row.get("return_20d_rank")), 4),
        "return_60d": (_pct(row.get("return_60d_rank")), 4),
        "return_120d": (_pct(row.get("return_120d_rank")), 4),
        "return_250d": (_pct(row.get("return_250d_rank")), 4),
        "historical_position": (_pct(row.get("historical_position_percentile")), 4),
    }
    return _component(
        features,
        20,
        {
            key: row.get(key)
            for key in (
                "return_20d",
                "return_60d",
                "return_120d",
                "return_250d",
                "historical_position_percentile",
            )
        },
    )


def _capacity_component(row):
    features = {
        "theme_amount": (_pct(row.get("theme_amount_rank")), 6),
        "core_market_cap": (_pct(row.get("core_market_cap_rank")), 5),
        "core_average_amount": (_pct(row.get("core_average_amount_rank")), 5),
        "capacity_stock_count": (_pct(row.get("capacity_stock_count_rank")), 4),
    }
    return _component(
        features,
        20,
        {
            key: row.get(key)
            for key in (
                "theme_amount",
                "core_market_cap",
                "core_average_amount",
                "capacity_stock_count",
            )
        },
    )


def _crowding_component(row):
    indicators = {
        "change": _pct(row.get("change_pct_rank")),
        "amount": _pct(row.get("theme_amount_rank")),
        "volatility": _pct(row.get("volatility_rank")),
        "turnover": _pct(row.get("turnover_history_percentile")),
    }
    intensity = mean(list(indicators.values()))
    advantage = (
        clamp(1 - abs((intensity or 0.6) - 0.6) / 0.6, 0, 1) if intensity is not None else None
    )
    features = {
        key: (value, points) for (key, value), points in zip(indicators.items(), (4, 4, 4, 3))
    }
    component = _component(
        features,
        15,
        {
            "change_pct": row.get("change_pct"),
            "amount_percentile": row.get("theme_amount_rank"),
            "volatility": row.get("volatility"),
            "volatility_percentile": row.get("volatility_rank"),
            "turnover_history_percentile": row.get("turnover_history_percentile"),
            "crowding_intensity": None if intensity is None else round(intensity * 100, 2),
        },
        override=advantage,
    )
    component["status"] = _crowding_status(intensity)
    return component


def _style_component(name, members, styles, inflections):
    labels = _theme_styles(name, members, inflections)
    values = [styles.get(label) for label in labels if styles.get(label) is not None]
    match = max(values) / 100 if values else None
    return _component(
        {"matched_style_strength": (match, 15)},
        15,
        {
            "matched_styles": labels,
            "matched_style_scores": {label: styles.get(label) for label in labels},
        },
    )


def _consensus_component(activity):
    ratio = number(activity.get("active_ratio"))
    return _component(
        {
            "historical_activity": (ratio, 6),
            "news_count": (None, 2),
            "institution_coverage": (None, 2),
        },
        10,
        {
            "active_days": activity.get("active_days"),
            "observation_days": activity.get("observation_days"),
            "historical_activity_ratio": ratio,
            "news_count": None,
            "institution_coverage": None,
        },
    )


def _stock_scores(
    codes,
    stats,
    metadata,
    market_stocks,
    inflections,
    auctions,
    role_map,
    theme_members,
    styles,
):
    rows = []
    codes = sorted(codes)
    return_ranks = {
        horizon: _rank_map(codes, lambda code, h=horizon: stats[code][f"return_{h}d"])
        for horizon in (20, 60, 120, 250)
    }
    amount_ranks = _rank_map(codes, lambda code: stats[code]["amount"])
    average_amount_ranks = _rank_map(codes, lambda code: stats[code]["average_amount_20d"])
    cap_ranks = _rank_map(codes, lambda code: market_stocks.get(code, {}).get("market_cap"))
    volatility_ranks = _rank_map(codes, lambda code: stats[code]["volatility_20d"])
    change_ranks = _rank_map(codes, lambda code: stats[code]["change_pct"])
    for code in codes:
        item = stats[code]
        stock_roles = role_map.get(code, [])
        themes = [name for name, members in theme_members.items() if code in members]
        position = _component(
            {
                **{f"return_{h}d": (return_ranks[h][code], 6) for h in (20, 60, 120, 250)},
                "historical_position": (_pct(item["historical_position_percentile"]), 6),
            },
            30,
            {
                key: item.get(key)
                for key in (
                    "return_20d",
                    "return_60d",
                    "return_120d",
                    "return_250d",
                    "historical_position_percentile",
                )
            },
        )
        capacity = _component(
            {
                "amount": (amount_ranks[code], 9),
                "average_amount_20d": (average_amount_ranks[code], 8),
                "market_cap": (cap_ranks[code], 8),
            },
            25,
            {
                "amount": item["amount"],
                "average_amount_20d": item["average_amount_20d"],
                "market_cap": number(market_stocks.get(code, {}).get("market_cap")),
            },
        )
        crowd_values = [
            change_ranks[code],
            _pct(item["amount_percentile_60d"]),
            volatility_ranks[code],
            _pct(inflections.get(code, {}).get("turnover_percentile_120d")),
        ]
        intensity = mean(crowd_values)
        advantage = (
            clamp(1 - abs((intensity or 0.6) - 0.6) / 0.6, 0, 1) if intensity is not None else None
        )
        crowding = _component(
            {f"indicator_{index}": (value, 5) for index, value in enumerate(crowd_values)},
            20,
            {
                "change_pct": item["change_pct"],
                "amount_percentile_60d": item["amount_percentile_60d"],
                "volatility_20d": item["volatility_20d"],
                "turnover_history_percentile": number(
                    inflections.get(code, {}).get("turnover_percentile_120d")
                ),
                "crowding_intensity": None if intensity is None else round(intensity * 100, 2),
            },
            override=advantage,
        )
        crowding["status"] = _crowding_status(intensity)
        matched_style_scores = []
        for theme in themes:
            matched_style_scores.extend(
                styles.get(label)
                for label in _theme_styles(theme, {code}, inflections)
                if styles.get(label) is not None
            )
        style = _component(
            {
                "style_strength": (
                    max(matched_style_scores) / 100 if matched_style_scores else None,
                    15,
                )
            },
            15,
            {"matched_style_score": max(matched_style_scores) if matched_style_scores else None},
        )
        role_score = max(
            (number(row.get("role_candidate_score")) or 0 for row in stock_roles), default=None
        )
        theme_role = _component(
            {"role_candidate_score": (role_score / 100 if role_score is not None else None, 10)},
            10,
            {
                "roles": sorted(
                    {
                        label
                        for row in stock_roles
                        for label in row.get("all_role_candidates") or [row.get("role_candidate")]
                        if label
                    }
                ),
                "role_candidate_score": role_score,
            },
        )
        components = {
            "position": position,
            "capacity": capacity,
            "crowding": crowding,
            "style_match": style,
            "theme_role": theme_role,
        }
        total = _total_score(components)
        labels = {
            label
            for row in stock_roles
            for label in row.get("all_role_candidates") or [row.get("role_candidate")]
        }
        rows.append(
            {
                "ts_code": code,
                "stock_name": item.get("stock_name"),
                "industry": item.get("industry"),
                "themes": themes,
                "stock_capital_preference_score": total["score"],
                "available_max_score": total["available_points"],
                "component_coverage": total["coverage"],
                **components,
                "crowding_status": crowding["status"],
                "leader_candidate": "LEADER_CANDIDATE" in labels,
                "capacity_candidate": "CAPACITY_CANDIDATE" in labels,
                "auction_volume_anomaly_score": number(
                    auctions.get(code, {}).get("auction_volume_anomaly_score")
                ),
                "inflection_status": inflections.get(code, {}).get("status"),
                "candidate_only": True,
            }
        )
    return rows


def _capital_structure(theme, roles_by_theme, stock_map):
    output = {value: None for value in ROLE_LABELS.values()}
    for row in roles_by_theme.get(theme, []):
        code = stock_code(row.get("ts_code"))
        for label in row.get("all_role_candidates") or [row.get("role_candidate")]:
            key = ROLE_LABELS.get(label)
            if not key or code not in stock_map:
                continue
            candidate = {
                "ts_code": code,
                "stock_name": row.get("stock_name"),
                "stock_capital_preference_score": stock_map[code]["stock_capital_preference_score"],
                "role_candidate_score": number(row.get("role_candidate_score")),
            }
            current = output[key]
            if current is None or (candidate["role_candidate_score"] or 0) > (
                current["role_candidate_score"] or 0
            ):
                output[key] = candidate
    score = sum(
        (row["stock_capital_preference_score"] or 0) / 100 * 20 for row in output.values() if row
    )
    return {
        **output,
        "capital_structure_score": round(score, 2),
        "role_coverage": sum(row is not None for row in output.values()) / 5,
    }


def _component(features, intended_points, inputs, override=None):
    available = sum(points for value, points in features.values() if value is not None)
    earned = sum(
        clamp(value, 0, 1) * points for value, points in features.values() if value is not None
    )
    if override is not None and available:
        earned = override * available
    return {
        "score": round(earned, 2) if available else None,
        "available_points": available,
        "normalized_score": round(earned / available * 100, 2) if available else None,
        "coverage": round(available / intended_points, 4),
        "inputs": inputs,
        "missing_inputs": [key for key, (value, _) in features.items() if value is None],
    }


def _total_score(components):
    earned = sum(number(row.get("score")) or 0 for row in components.values())
    available = sum(number(row.get("available_points")) or 0 for row in components.values())
    return {
        "score": round(earned / available * 100, 2) if available else None,
        "available_points": round(available, 2),
        "coverage": round(available / 100, 4),
    }


def _theme_styles(name, members, inflections):
    labels = []
    if any(code.startswith(("300", "688")) for code in members):
        labels.append("growth")
    if any(not code.startswith(("300", "688")) for code in members):
        labels.append("value")
    for label, words in (
        ("technology", TECH),
        ("cyclical", CYCLICAL),
        ("consumer", CONSUMER),
        ("financial", FINANCIAL),
    ):
        if any(word in name for word in words):
            labels.append(label)
    if any(
        code in inflections
        and inflections[code].get("status") not in (None, "NO_SIGNAL", "TREND_BROKEN")
        for code in members
    ):
        labels.append("trend_style")
    return sorted(set(labels))


def _role_map(grouped):
    result = defaultdict(list)
    for rows in grouped.values():
        for row in rows:
            if code := stock_code(row.get("ts_code")):
                result[code].append(row)
    return result


def _theme_candidate_codes(theme):
    result = set()
    for field in (
        "top_gainers",
        "leader_candidates",
        "capacity_candidates",
        "catch_up_candidates",
        "trend_candidates",
    ):
        result.update(
            code
            for row in theme.get(field) or []
            if (code := stock_code(row.get("stock_code") or row.get("ts_code")))
        )
    return result


def _event_matches(row, theme, members):
    code = stock_code(row.get("stock_code") or row.get("ts_code"))
    text = " ".join(str(row.get(key) or "") for key in ("title", "summary", "confirmed_fact"))
    return code in members or theme in text


def _policy_matches(row, theme):
    return (
        theme in (row.get("related_themes") or [])
        or theme in (row.get("related_industries") or [])
        or theme in str(row.get("title") or "")
    )


def _quality_available(market, item):
    statuses = [
        row.get("status")
        for row in (market.get("data_quality") or {}).get("checks") or []
        if row.get("item") == item
    ]
    return bool(statuses and statuses[0] == "PASS")


def _rank_map(codes, getter):
    values = {code: number(getter(code)) for code in codes}
    ordered = sorted(value for value in values.values() if value is not None)
    if not ordered:
        return {code: None for code in codes}
    return {
        code: None if value is None else bisect_right(ordered, value) / len(ordered)
        for code, value in values.items()
    }


def _pct(value):
    parsed = number(value)
    return parsed / 100 if parsed is not None else None


def _crowding_status(value):
    return (
        None
        if value is None
        else "LOW"
        if value < 0.35
        else "BALANCED"
        if value < 0.7
        else "ELEVATED"
        if value < 0.85
        else "EXTREME"
    )


def _theme_reasons(components):
    labels = {
        "fundamental_fit": "official fundamental evidence",
        "position_advantage": "multi-horizon position",
        "capital_capacity": "capital capacity",
        "crowding_advantage": "crowding balance",
        "style_match": "current style match",
        "consensus_proxy": "historical activity",
    }
    return [
        {"factor": key, "evidence": labels[key], "normalized_score": row.get("normalized_score")}
        for key, row in components.items()
        if (row.get("normalized_score") or 0) >= 60
    ]
