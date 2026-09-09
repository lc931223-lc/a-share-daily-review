"""Allowlisted projection of existing packets into ChatGPT's objective inputs."""

import copy
import hashlib
import json
from datetime import date
from pathlib import Path
from statistics import median

from jsonschema import Draft202012Validator

from src.auction.production import read, write
from src.formal_review.objective_evidence import (
    available_at,
    evidence_nodes,
    factor_evidence,
    number,
    realization_facts,
)
from src.formal_review.objective_validation import previous_results
from src.formal_review.persistence import previous_day
from src.market_packet.trading_calendar import load_trading_calendar

SCHEMA_ROOT = Path(__file__).resolve().parents[2] / "schemas"
MARKET_FIELDS = "total_amount amount_change_vs_previous rise_count fall_count median_return limit_up_count limit_down_count failed_limit_count failed_limit_rate highest_board promotion_rate new_limit_up_count theme_limit_down_count large_cap_return small_cap_return growth_return value_return high_beta_return dividend_return".split()
THEME_FIELDS = "return breadth limit_up_count failed_limit_count amount amount_change leader_strength capacity_strength persistence_1d persistence_3d persistence_5d evidence_count_tier1 evidence_count_tier2 evidence_count_total price_factor_count policy_factor_count earnings_factor_count order_factor_count risk_factor_count".split()
ROLE_FIELDS = "leader_candidate_score capacity_candidate_score trend_candidate_score elasticity_score catch_up_score follower_score amount market_cap relative_strength board_height persistence announcement_support earnings_support".split()
VECTOR_FIELDS = "active_days strength_change_1d strength_change_3d breadth_change amount_change leader_persistence capacity_persistence new_subtheme_count catch_up_count failed_leader_count theme_limit_down_count catalyst_age".split()
DIMENSIONS = "base_logic_inputs realization_inputs expectation_gap_inputs continuity_inputs market_confirmation_inputs risk_inputs".split()


def numeric(row, fields):
    return {key: number(row.get(key)) for key in fields}


def diff(a, b):
    a, b = number(a), number(b)
    return a - b if a is not None and b is not None else None


def code(row):
    return str(row.get("ts_code") or row.get("stock_code") or "").split(".")[0]


def _load(root, folder, day, manifest, gaps, required=False):
    path = root / "data" / folder / f"{day}.json"
    nonfinite = []

    def missing_constant(value):
        nonfinite.append(value)
        return None

    payload = (
        json.loads(path.read_text(encoding="utf-8"), parse_constant=missing_constant)
        if path.exists()
        else {}
    )
    if nonfinite:
        gaps.append(dict(field=folder, reason="NONFINITE_SOURCE_VALUES_AS_NULL"))
    actual = (payload.get("meta") or {}).get("trade_date")
    if not payload or actual != str(day):
        if required:
            raise ValueError(f"same-date {folder} required")
        gaps.append(dict(field=folder, reason="MISSING_OR_WRONG_DATE"))
        manifest[folder] = dict(
            path=path.relative_to(root).as_posix(),
            source_date=None,
            sha256=None,
            status="UNAVAILABLE",
        )
        return {}
    manifest[folder] = dict(
        path=path.relative_to(root).as_posix(),
        source_date=str(day),
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        canonical_sha256=hashlib.sha256(
            json.dumps(
                payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
            ).encode("utf-8")
        ).hexdigest(),
        status=(payload.get("data_quality") or {}).get("status", "UNKNOWN"),
    )

    def future_dependency(value):
        if isinstance(value, dict):
            return any(
                not available_at(value[k], day)
                for k in ("source_date", "source_data_date", "data_date", "as_of")
                if value.get(k)
            ) or any(future_dependency(v) for v in value.values())
        if isinstance(value, list):
            return any(future_dependency(v) for v in value)
        return False

    if future_dependency(payload.get("source_manifest", {})):
        if required:
            raise ValueError(f"future dependency in {folder}")
        manifest[folder]["status"] = "AS_OF_REJECTED"
        gaps.append(dict(field=folder, reason="FUTURE_DEPENDENCY_EXCLUDED"))
        return {}

    # A same-date envelope cannot legitimize a future or current-only child row.
    def guard(value, location):
        if isinstance(value, dict):
            dates = [
                value[k]
                for k in (
                    "published_at",
                    "source_date",
                    "source_data_date",
                    "data_date",
                    "trade_date",
                    "as_of",
                )
                if value.get(k)
            ]
            bad = any(not available_at(d, day) for d in dates)
            bad |= value.get("freshness") == "current_only" and str(value.get("data_date"))[
                :10
            ] != str(day)
            if bad:
                gaps.append(dict(field=location, reason="AS_OF_EXCLUDED"))
                return None
            return {k: guard(v, f"{location}.{k}") for k, v in value.items()}
        if isinstance(value, list):
            return [filtered for v in value if (filtered := guard(v, location)) is not None]
        return value

    return guard(payload, folder) or {}


def _snapshot(market, ri, prior, gaps):
    overview, limits = market.get("market_overview", {}), market.get("limit_up_down", {})
    out = {k: None for k in MARKET_FIELDS}
    for key in (
        "rise_count",
        "fall_count",
        "limit_up_count",
        "limit_down_count",
        "failed_limit_count",
        "highest_board",
    ):
        out[key] = number(overview.get(key))
    for key in ("failed_limit_rate", "promotion_rate"):
        out[key] = number(limits.get(key))
    out["total_amount"] = number(overview.get("total_market_turnover"))
    # Recompute against the exact previous date, not an upstream cached comparison.
    out["amount_change_vs_previous"] = diff(
        out["total_amount"], prior.get("market_overview", {}).get("total_market_turnover")
    )
    counts = {
        str(k): number(limits.get(name))
        for k, name in (
            (2, "second_board_count"),
            (3, "third_board_count"),
            (4, "fourth_board_count"),
            ("5+", "five_plus_board_count"),
        )
    }
    if out["limit_up_count"] is not None and all(v is not None for v in counts.values()):
        counts["1"] = out["limit_up_count"] - sum(counts.values())
        if counts["1"] < 0:
            counts["1"] = None
    else:
        counts["1"] = None
    out["new_limit_up_count"] = counts["1"]
    out["board_distribution"] = counts
    styles = [
        s for s in ri.get("style_strength_ranking", []) if number(s.get("return")) is not None
    ]
    out["strongest_style"] = max(styles, key=lambda s: s["return"])["style"] if styles else None
    out["weakest_style"] = min(styles, key=lambda s: s["return"])["style"] if styles else None
    out["style_observations"] = []
    for s in styles:
        out["style_observations"].append(
            dict(
                style=s["style"],
                return_pct=number(s.get("return")),
                sample_count=number(s.get("sample_count")),
                coverage_status=s.get("coverage_status"),
                source_coverage=number(s.get("source_coverage")),
                methodology=s.get("methodology"),
            )
        )
        if s["style"] + "_return" in out:
            out[s["style"] + "_return"] = number(s["return"])
    out["style_selection_method"] = "observed_sample_return_max_min; not full-market inference"
    for key in MARKET_FIELDS:
        if out[key] is None:
            gaps.append(dict(field="market_snapshot." + key, reason="METRIC_UNAVAILABLE"))
    return out


def _roles(ri, capital, market, nodes):
    role_map = {code(r): r for r in ri.get("role_candidates", [])}
    capital_map = {code(r): r for r in capital.get("stock_capital_preference", [])}
    stocks = {code(r): r for r in market.get("stocks", [])}
    out = []
    for stock_code in sorted(set(role_map) | set(capital_map) | set(stocks)):
        role, cap, stock = (
            role_map.get(stock_code, {}),
            capital_map.get(stock_code, {}),
            stocks.get(stock_code, {}),
        )
        row = {k: None for k in ROLE_FIELDS}
        row.update(
            stock_code=stock_code,
            stock_name=stock.get("stock_name") or cap.get("stock_name") or role.get("stock_name"),
        )
        scores = role.get("role_scores") or {}
        for dest, source in zip(
            ROLE_FIELDS[:6],
            ("leader", "capacity", "trend_leader", "elasticity", "catch_up", "follower"),
        ):
            row[dest] = number(scores.get(source))
        capacity = (cap.get("capacity") or {}).get("inputs") or {}
        row.update(
            amount=number(capacity.get("amount", stock.get("amount"))),
            market_cap=number(capacity.get("market_cap", stock.get("market_cap"))),
            relative_strength=number(role.get("relative_strength")),
            board_height=number(role.get("board_height", stock.get("board_count"))),
            persistence=number(role.get("continuity")),
            theme_linkage=sorted(
                set(
                    cap.get("themes")
                    or stock.get("themes")
                    or ([role["theme"]] if role.get("theme") else [])
                )
            ),
        )
        linked = [n for n in nodes if n["related_company"] == stock_code]
        row["announcement_support"] = len(linked)
        row["earnings_support"] = sum(
            n["fact_type"] in {"earnings_disclosure", "revenue_growth", "profit_growth"}
            for n in linked
        )
        row["risk_flags"] = sorted({f for n in linked for f in n["risk_flags"]})
        out.append(row)
    return out


def _themes(ri, market, nodes):
    raw = ri.get("theme_features") or market.get("themes") or []
    output = []
    for theme in raw:
        name = theme.get("theme_name") or theme.get("name")
        if not name:
            continue
        row = numeric(theme, THEME_FIELDS)
        row.update(
            theme_name=name,
            source=theme.get("source"),
            coverage_status=theme.get("quality") or "UNKNOWN",
        )
        row["return"] = number(theme.get("change_pct"))
        row["breadth"] = number(theme.get("theme_breadth"))
        if row["breadth"] is None:
            rise, fall = number(theme.get("rise_count")), number(theme.get("fall_count"))
            if rise is not None and fall is not None and rise + fall > 0:
                row["breadth"] = rise / (rise + fall) * 100
        # THS raw amount has no unit metadata in archived packets. Do not mix it with CNY.
        if str(theme.get("source", "")).startswith("ths."):
            row["amount"] = None
        linked = [n for n in nodes if name in n["related_theme"]]
        row.update(
            evidence_count_tier1=sum(n["tier"] == 1 for n in linked),
            evidence_count_tier2=sum(n["tier"] == 2 for n in linked),
            evidence_count_total=len(linked),
        )
        for key, kinds in {
            "price_factor_count": {"price_change"},
            "policy_factor_count": {"policy_release"},
            "earnings_factor_count": {"earnings_disclosure", "revenue_growth", "profit_growth"},
            "order_factor_count": {"order_confirmation"},
        }.items():
            row[key] = sum(n["fact_type"] in kinds for n in linked)
        row["risk_factor_count"] = sum(bool(n["risk_flags"]) for n in linked)
        output.append(row)
    return sorted(output, key=lambda r: r["theme_name"])


def _vectors(themes, history, nodes, realizations):
    output = []
    for t in themes:
        name = t["theme_name"]
        row = dict(theme_name=name, first_seen_date=None, **{k: None for k in VECTOR_FIELDS})
        samples = []
        for day, packet in history:
            match = next(
                (x for x in packet.get("theme_features", []) if x.get("theme_name") == name), None
            )
            samples.append((day, match))
        # A missing day breaks the observation window; never label sparse history as 3d/5d.
        present = [(day, x) for day, x in samples if x is not None]
        if present:
            row["first_seen_date"] = present[0][0]
            row["active_days"] = len(present)
        for window in (1, 3, 5):
            if len(samples) >= window + 1 and all(x for _, x in samples[-window - 1 :]):
                values = [number(x.get("change_pct")) for _, x in samples[-window:]]
                if all(v is not None for v in values):
                    t[f"persistence_{window}d"] = sum(v > 0 for v in values) / window
                if window in (1, 3):
                    row[f"strength_change_{window}d"] = diff(
                        t["return"], samples[-window - 1][1].get("change_pct")
                    )
        if len(samples) > 1 and samples[-2][1]:
            prior = samples[-2][1]
            row["breadth_change"] = diff(t["breadth"], prior.get("theme_breadth"))
            row["amount_change"] = diff(t["amount"], prior.get("amount"))
        linked = [n for n in nodes if name in n["related_theme"]]
        row["realization_level"] = sorted(
            {r["fact_level"] for r in realizations if name in r["related_theme"]}
        ) or ["UNKNOWN"]
        if linked and samples:
            row["catalyst_age"] = min(
                (date.fromisoformat(samples[-1][0]) - date.fromisoformat(n["date"][:10])).days
                for n in linked
            )
        output.append(row)
    return output


def _dimensions(themes, nodes, capital):
    out = []
    for theme in themes:
        name = theme["theme_name"]
        linked = [n for n in nodes if name in n["related_theme"]]
        cap = next(
            (c for c in capital.get("theme_capital_preference", []) if c.get("theme") == name), {}
        )
        crowd = (cap.get("crowding_advantage") or {}).get("inputs") or {}
        out.append(
            dict(
                theme_name=name,
                base_logic_inputs=dict(
                    tier1_policy_count=sum(
                        n["tier"] == 1 and n["fact_type"] == "policy_release" for n in linked
                    ),
                    price_evidence=[
                        n["evidence_id"] for n in linked if n["fact_type"] == "price_change"
                    ],
                    industry_data=[
                        n["evidence_id"]
                        for n in linked
                        if n["fact_type"] in {"industry_inventory", "industry_utilization"}
                    ],
                    earnings_evidence=[
                        n["evidence_id"]
                        for n in linked
                        if n["fact_type"]
                        in {"earnings_disclosure", "revenue_growth", "profit_growth"}
                    ],
                ),
                realization_inputs=dict(
                    evidence=[n["evidence_id"] for n in linked if n["status"] == "OBSERVED"]
                ),
                expectation_gap_inputs=dict(
                    consensus_estimate=None, prior_guidance=None, actual_reported=None
                ),
                continuity_inputs={
                    k: theme[k] for k in ("persistence_1d", "persistence_3d", "persistence_5d")
                },
                market_confirmation_inputs={
                    k: theme[k]
                    for k in (
                        "amount",
                        "breadth",
                        "limit_up_count",
                        "leader_strength",
                        "capacity_strength",
                    )
                },
                risk_inputs=dict(
                    amount_percentile=number(crowd.get("amount_percentile")),
                    volatility=number(crowd.get("volatility")),
                    turnover_history_percentile=number(crowd.get("turnover_history_percentile")),
                    leader_dependency=None,
                    failed_limit_count=theme["failed_limit_count"],
                    valuation=None,
                    disclosure_flags=sorted({f for n in linked for f in n["risk_flags"]}),
                ),
            )
        )
    return out


def _divergences(snapshot, market):
    out = {}
    index = next((r for r in market.get("indices", []) if r.get("ts_code") == "000001.SH"), {})
    idx = number(index.get("change_pct"))
    a, b = snapshot["rise_count"], snapshot["fall_count"]
    if idx is not None and idx > 0 and a is not None and b is not None and a < b:
        out["index_up_but_breadth_weak"] = dict(
            metric_a=idx, metric_b=a - b, raw_difference=None, severity=None
        )
    delta = snapshot["amount_change_vs_previous"]
    if idx is not None and idx > 0 and delta is not None and delta < 0:
        out["volume_down_but_index_up"] = dict(
            metric_a=idx, metric_b=delta, raw_difference=None, severity=None
        )
    # Unlike-unit differences and severity require a declared model. Leave null.
    return out


def build_inputs(root, target, calendar=None):
    root, target = Path(root), date.fromisoformat(str(target))
    calendar = (
        calendar
        if calendar is not None
        else load_trading_calendar(target, cache_root=root / "data/reference")
    )
    if not any(d.cal_date == target and d.is_open for d in calendar):
        raise ValueError("review input requires an exchange trading day")
    manifest, gaps = {}, []
    market = _load(root, "market_packets", target, manifest, gaps, required=True)
    ri = _load(root, "review_intelligence", target, manifest, gaps)
    capital = _load(root, "capital_preference", target, manifest, gaps)
    context = _load(root, "review_context", target, manifest, gaps)
    for folder in ("formal_review_support", "auction_packets"):
        _load(root, folder, target, manifest, gaps)
    previous = previous_day(root, target, calendar)
    prior_manifest = {}
    prior = _load(root, "market_packets", previous, prior_manifest, gaps)
    manifest["previous_market_packet"] = prior_manifest["market_packets"]
    history = []
    for day in sorted({d.cal_date for d in calendar if d.is_open and d.cal_date <= target})[-6:]:
        hmanifest = {}
        packet = ri if day == target else _load(root, "review_intelligence", day, hmanifest, gaps)
        if hmanifest:
            manifest[f"review_intelligence_{day}"] = hmanifest["review_intelligence"]
        history.append((str(day), packet))
    snapshot = _snapshot(market, ri, prior, gaps)
    # Read local FactStore only. No second database and no acquisition during replay.
    from src.storage.fact_store import FactStore

    facts = FactStore(root / "data/facts")
    daily = facts.read_dataset("stock_daily_ohlcv", target)
    returns = [
        number(r.get("pct_chg")) for r in daily if str(r.get("trade_date"))[:10] == str(target)
    ]
    returns = [v for v in returns if v is not None]
    expected = sum(
        number(market.get("market_overview", {}).get(k)) or 0
        for k in ("rise_count", "fall_count", "flat_count")
    )
    if returns and len(returns) == len(daily) == expected:
        snapshot["median_return"] = median(returns)
        gaps = [g for g in gaps if g["field"] != "market_snapshot.median_return"]
    fact_paths = sorted(
        (root / "data/facts/dataset=stock_daily_ohlcv" / f"trade_date={target}").glob("*.parquet")
    )
    for i, path in enumerate(fact_paths):
        manifest[f"daily_fact_partition_{i}"] = dict(
            path=path.relative_to(root).as_posix(),
            source_date=str(target),
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            status="AVAILABLE",
        )
    nodes = evidence_nodes(market, target, gaps)
    realization = realization_facts(nodes)
    themes = _themes(ri, market, nodes)
    roles = _roles(ri, capital, market, nodes)
    anomalies = [
        dict(
            candidate_type="very_high_turnover",
            stock_code=code(r),
            metric_a=number(r["turnover_rate"]),
            metric_b=30.0,
            source_date=str(target),
            evidence=[],
        )
        for r in market.get("stocks", [])
        if (number(r.get("turnover_rate")) or 0) >= 30
    ]
    cross = []
    for row in market.get("cross_market_facts", []):
        if (
            available_at(row.get("date"), target)
            and number(row.get("value")) is not None
            and row.get("source")
        ):
            from src.formal_review.objective_evidence import source_tier

            cross.append(
                dict(
                    market=str(row.get("market") or "UNKNOWN"),
                    instrument=str(row.get("instrument") or "UNKNOWN"),
                    date=row["date"],
                    value=number(row["value"]),
                    source=row["source"],
                    url=row.get("url"),
                    tier=source_tier(row),
                )
            )
    vectors = _vectors(themes, history, nodes, realization)
    validation = previous_results(root, target, market, calendar)
    # Raw trend/weekly/chip measurements, no inherited status or interpretation strings.
    trend = []
    for r in context.get("inflection_candidates", []):
        chip, weekly, breakout = (
            r.get("chip_health") or {},
            r.get("weekly_structure") or {},
            r.get("breakout") or {},
        )
        trend.append(
            dict(
                stock_code=code(r),
                trend_score=number(r.get("trend_score")),
                chip_inputs=numeric(
                    chip,
                    "pullback_volume_ratio amount_percentile turnover_percentile volatility_percentile upper_shadow_frequency large_negative_frequency".split(),
                ),
                weekly_inputs=numeric(weekly, "wma5 wma10 wma20 slope_wma20".split()),
                hold_days=number(breakout.get("hold_days")),
            )
        )
    gaps.extend(
        dict(field=k, reason=v)
        for k, v in {
            "factor41_evidence": "UNMAPPED_IS_UNAVAILABLE_NOT_ABSENCE; category links do not prove driver",
            "cross_market_facts": "NO_VERIFIED_TIMESTAMPED_CROSS_MARKET_DATA"
            if not cross
            else "AS_OF_OBSERVATIONS_ONLY",
            "abnormal_data_candidates": "TURNOVER_GE_30_PERCENT_ONLY; no comparable price/fundamental baseline",
            "theme_candidates.amount": "THS_RAW_AMOUNT_UNIT_UNVERIFIED",
            "lifecycle_vectors.first_seen_date": "FIRST_OBSERVED_IN_SIX_SESSION_ARCHIVE_NOT_INCEPTION",
            "stock_role_candidates": "SUPPORT_COUNTS_ARE_OBSERVED_NODE_COUNTS_NOT_FULL_COVERAGE",
            "source_manifest": "BYTE_SHA_IS_LOCAL_ARCHIVE; canonical_sha256 bridges JSON newline differences; local history/FactStore may not be versioned",
            "market_divergence_candidates": "ONLY_COMPUTABLE_PAIRS; NO_SEVERITY_MODEL",
        }.items()
    )
    for section, rows in (
        ("theme_candidates", themes),
        ("stock_role_candidates", roles),
        ("lifecycle_vectors", vectors),
    ):
        fields = sorted({k for row in rows for k, v in row.items() if v is None})
        gaps.extend(
            dict(field=f"{section}.{key}", reason="PARTIAL_OR_UNAVAILABLE_OBSERVATIONS")
            for key in fields
        )
    packet = dict(
        meta=dict(
            schema_version="chatgpt_review_inputs.1",
            trade_date=str(target),
            as_of=f"{target}T23:59:59+08:00",
            data_role="OBJECTIVE_RESEARCH_INPUT",
            final_judgement_owner="chatgpt",
        ),
        market_snapshot=snapshot,
        market_divergence_candidates=_divergences(snapshot, market),
        theme_candidates=themes,
        theme_evidence=nodes,
        factor41_evidence=factor_evidence(nodes),
        realization_facts=realization,
        stock_role_candidates=roles,
        lifecycle_vectors=vectors,
        six_dimension_inputs=_dimensions(themes, nodes, capital),
        previous_review_actual_results=validation,
        cross_market_facts=cross,
        abnormal_data_candidates=anomalies,
        inflection_observations=trend,
        data_gaps=sorted({(g["field"], g["reason"]) for g in gaps}),
        source_manifest=manifest,
    )
    packet["data_gaps"] = [dict(field=k, reason=v) for k, v in packet["data_gaps"]]
    compact = compact_inputs(packet)
    for value, name in (
        (packet, "chatgpt_review_inputs"),
        (compact, "chatgpt_review_inputs_compact"),
    ):
        schema = read(SCHEMA_ROOT / f"{name}.schema.json")
        Draft202012Validator(schema).validate(value)
    folder = root / "data/chatgpt_review_inputs"
    write(folder / f"{target}.json", packet)
    write(folder / f"{target}_compact.json", compact)
    return packet


def compact_inputs(packet):
    result = copy.deepcopy(packet)
    result["meta"]["schema_version"] = "chatgpt_review_inputs_compact.1"
    # Selection is reproducible liquidity ordering, not a formal mainline ranking.
    result["theme_candidates"] = sorted(
        result["theme_candidates"], key=lambda r: (-(r["amount"] or 0), r["theme_name"])
    )[:10]
    names = {r["theme_name"] for r in result["theme_candidates"]}
    result["stock_role_candidates"] = sorted(
        [r for r in result["stock_role_candidates"] if names.intersection(r["theme_linkage"])],
        key=lambda r: (-(r["amount"] or 0), r["stock_code"]),
    )[:20]
    for key in ("lifecycle_vectors", "six_dimension_inputs"):
        result[key] = [r for r in result[key] if r["theme_name"] in names]
    selected = [
        n
        for n in result["theme_evidence"]
        if n["risk_flags"] or names.intersection(n["related_theme"])
    ]
    result["theme_evidence"] = sorted(
        selected, key=lambda n: (not bool(n["risk_flags"]), n["tier"], n["evidence_id"])
    )[:30]
    ids = {n["evidence_id"] for n in result["theme_evidence"]}
    result["factor41_evidence"] = factor_evidence(result["theme_evidence"])
    result["realization_facts"] = [
        r for r in result["realization_facts"] if r["evidence_id"] in ids
    ]
    for row in result["six_dimension_inputs"]:
        for dim in DIMENSIONS:
            for key, value in row[dim].items():
                if key in {"price_evidence", "industry_data", "earnings_evidence", "evidence"}:
                    row[dim][key] = [v for v in value if v in ids]
    result["inflection_observations"] = result["inflection_observations"][:10]
    result["selection"] = dict(
        method="amount_desc_then_identity; evidence_risk_first_then_tier",
        theme_limit=10,
        stock_limit=20,
        evidence_limit=30,
        full_theme_count=len(packet["theme_candidates"]),
        full_evidence_count=len(packet["theme_evidence"]),
    )
    result["data_gaps"].append(
        dict(
            field="compact",
            reason="BOUNDED_SELECTION_NOT_ABSENCE; consult full packet for omitted evidence",
        )
    )
    return result
