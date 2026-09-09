"""Evaluate explicit formal predicates, never grade the research hypothesis."""

from src.formal_review.objective_evidence import number
from src.formal_review.persistence import load_previous_formal

CONDITIONS = (
    "validation_point",
    "strengthening_condition",
    "weakening_condition",
    "falsification_condition",
)
FIELDS = {"change_pct", "amount", "rise_count", "fall_count", "limit_up_count", "limit_down_count"}


def metric_results(formal, market):
    output = []
    rows = market.get("themes", []) + market.get("industries", [])
    for theme in formal.get("main_themes", []):
        name = theme["theme_name"]
        row = next((r for r in rows if (r.get("theme_name") or r.get("name")) == name), {})
        for index, check in enumerate(theme.get("next_day_validation", [])):
            for kind in CONDITIONS:
                condition = check.get(kind)
                # Legacy predicate applies to the validation point, not to all four
                # opposite conditions. Never infer predicates from prose.
                predicate = (
                    (check.get("predicates") or {}).get(kind)
                    or (check.get("predicate") if kind == "validation_point" else None)
                    or {}
                )
                field, op = predicate.get("field"), predicate.get("operator")
                actual = number(row.get(field)) if field in FIELDS else None
                threshold = number(predicate.get("threshold"))
                supported = (
                    actual is not None
                    and threshold is not None
                    and op in {"gte", "lte", "gt", "lt", "eq"}
                )
                met = None
                if supported:
                    met = {
                        "gte": actual >= threshold,
                        "lte": actual <= threshold,
                        "gt": actual > threshold,
                        "lt": actual < threshold,
                        "eq": actual == threshold,
                    }[op]
                output.append(
                    dict(
                        theme_name=name,
                        check_index=index,
                        condition_type=kind,
                        condition=condition if isinstance(condition, str) else None,
                        metric=field if field in FIELDS else None,
                        metric_name=field if field in FIELDS else None,
                        operator=op if supported else None,
                        actual_value=actual,
                        threshold=threshold,
                        condition_met=met,
                        metric_status="EVALUATED" if supported else "NOT_EVALUABLE",
                        evidence=[
                            dict(
                                source="market_packet",
                                source_date=market["meta"]["trade_date"],
                                field=field,
                                value=actual,
                            )
                        ]
                        if actual is not None
                        else [],
                    )
                )
    return output


def previous_results(root, target, market, calendar=None):
    formal, manifest = load_previous_formal(root, target, calendar)
    if manifest.get("path"):
        manifest["path"] = f"data/formal_reviews/{manifest['data_date']}.json"
    return dict(status=manifest["status"], source=manifest, records=metric_results(formal, market))
