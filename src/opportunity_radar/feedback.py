"""Fixed, censored descriptive feedback. Not a recommendation win rate."""
import statistics
import math
from collections import defaultdict

from src.opportunity_radar.contracts import CATEGORIES, visible, number

RULE = {"relative_return_5d_min": 3.0, "breadth_min": 0.60, "amount_ratio_20d_min": 1.20,
        "evaluation_window_trading_days": 20, "version": "radar-confirmation.1"}


def confirmation(metrics):
    keys = ("relative_return_5d", "breadth", "amount_ratio_20d")
    if any(metrics.get(k) is None for k in keys):
        return None
    return metrics[keys[0]] >= RULE["relative_return_5d_min"] and metrics[keys[1]] >= RULE["breadth_min"] and metrics[keys[2]] >= RULE["amount_ratio_20d_min"]


def measure(signals, market_rows, trading_days, as_of):
    days = sorted(str(day) for day in trading_days if str(day) <= str(as_of))
    records = []
    for signal in signals:
        first = signal["signal_first_seen_date"]
        window = [day for day in days if day > first][:20]
        context_window = [day for day in days if day <= first][-20:] + window
        by_date = {r["date"]: r for r in market_rows if r.get("entity") == (signal.get("theme") or signal["entity"])
                   and r["date"] in context_window and r.get("as_of_valid") is True}
        complete = len(window) == 20 and all(day in by_date and confirmation(by_date[day]) is not None for day in window)
        observed = [day for day in context_window if day in by_date and confirmation(by_date[day]) is True]
        hit = observed[0] if observed else None
        last = by_date.get(window[-1], {}) if window else {}
        survived = last.get("signal_direction_persisted") if complete else None
        records.append({"signal_first_seen_date": first, "signal_type": signal["signal_type"],
                        "entity": signal["entity"], "theme": signal.get("theme"), "company": signal.get("stock_code"),
                        "market_confirmation_date": hit,
                        "lead_trading_days": (len([d for d in days if first < d <= hit]) if hit >= first else -len([d for d in days if hit < d <= first])) if hit else None,
                        "pre_existing_market_confirmation": hit < first if hit else None,
                        "confirmation_search_scope": "20 prior and 20 subsequent trading sessions; first observed rule match",
                        "evaluation_status": "EVALUABLE" if complete else "RIGHT_CENSORED_OR_DATA_UNAVAILABLE",
                        "survived": survived, "independent_source_confirmation": last.get("independent_source_confirmation") if complete else None})
    return {"rule": RULE, "records": records, **_statistics(records),
            "by_signal_type": {key: _statistics([r for r in records if r["signal_type"] == key]) for key in CATEGORIES}}


def _statistics(records):
    eligible = [r for r in records if r["evaluation_status"] == "EVALUABLE"]
    leads = [r["lead_trading_days"] for r in eligible if r["lead_trading_days"] is not None]
    survival = [r["survived"] for r in eligible if isinstance(r["survived"], bool)]
    sources = [r["independent_source_confirmation"] for r in eligible if isinstance(r["independent_source_confirmation"], bool)]
    ratio = lambda rows: sum(rows)/len(rows) if rows else None
    hits = [r["market_confirmation_date"] is not None for r in eligible]
    return {"signal_count": len(records), "evaluable_count": len(eligible),
            "market_confirmation_rate": ratio(hits), "median_lead_time": statistics.median(leads) if leads else None,
            "false_positive_rate": ratio([not h for h in hits]), "signal_survival_rate": ratio(survival),
            "signal_decay_rate": ratio([not x for x in survival]), "source_confirmation_rate": ratio(sources),
            "status": "AVAILABLE" if eligible else "DATA_UNAVAILABLE",
            "denominator_policy": "20 observed subsequent trading sessions; censored/missing observations excluded"}


def market_validation_rows(observations, trading_days, cutoff):
    groups = defaultdict(dict)
    for row in sorted(observations, key=lambda r: r["first_seen_at"]):
        if row["signal_type"] == "MARKET_STRUCTURE_AND_FLOW" and visible(row, cutoff):
            groups[row["entity"]][row["source_date"]] = row
    days = sorted(trading_days)
    output = []
    for entity, records in groups.items():
        for day, row in records.items():
            if day not in days:
                continue
            index = days.index(day)
            five = days[max(0, index-4):index+1]
            twenty = days[max(0, index-20):index]
            facts = row["facts"]
            rise, fall = number(facts.get("rise_count")), number(facts.get("fall_count"))
            breadth = rise/(rise+fall) if rise is not None and fall is not None and rise+fall > 0 else None
            relative = None
            if len(five) == 5 and all(d in records for d in five):
                moves = [number(records[d]["facts"].get("return_1d")) for d in five]
                base = [number(records[d]["facts"].get("benchmark_return_1d")) for d in five]
                if all(v is not None for v in moves + base):
                    relative = 100 * (math.prod(1+v/100 for v in moves) - math.prod(1+v/100 for v in base))
            ratio = None
            if len(twenty) == 20 and all(d in records and records[d]["value"] is not None for d in twenty):
                mean = statistics.mean(records[d]["value"] for d in twenty)
                ratio = row["value"]/mean if mean and row["value"] is not None else None
            output.append({"entity": entity, "date": day, "as_of_valid": True, "relative_return_5d": relative,
                           "breadth": breadth, "amount_ratio_20d": ratio})
    return output
