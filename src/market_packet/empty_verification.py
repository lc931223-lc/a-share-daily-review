"""Conservative empty-pool verification; absence is never inferred from HTTP success."""
from dataclasses import replace
from decimal import Decimal, ROUND_HALF_UP


def verify_empty_limit_down(datasets, target, *, minimum_rows=4000):
    pool = datasets.get("limit_down")
    daily = datasets.get("tushare_daily_all")
    if pool is None or pool.rows:
        return
    reasons = []
    if daily is None or daily.data_date != target or daily.quality != "PASS":
        reasons.append("same-date daily unavailable")
    rows = daily.rows if daily else []
    if len(rows) < minimum_rows or len({r.get('ts_code') for r in rows}) != len(rows):
        reasons.append("daily coverage incomplete or duplicated")
    candidates = []
    limits = datasets.get("daily_price_limits")
    bands_by_code = {r["ts_code"]: r for r in limits.rows if str(r.get("trade_date", "")).replace("-", "") == target.strftime("%Y%m%d")} if limits and limits.data_date == target and limits.quality == "PASS" else {}
    for row in rows:
        row = row | {key: value for key, value in bands_by_code.get(row.get("ts_code"), {}).items() if key == "down_limit"}
        try:
            if str(row.get("trade_date", "")).replace("-", "") != target.strftime("%Y%m%d"):
                raise ValueError("date")
            close = Decimal(str(row["close"]))
            previous = Decimal(str(row["pre_close"]))
            if not close.is_finite() or not previous.is_finite() or previous <= 0:
                raise ValueError("price")
            # Authoritative per-security daily bands override conservative possible bands.
            if row.get("down_limit") is not None:
                bands = [Decimal(str(row["down_limit"]))]
            else:
                code = str(row["ts_code"])
                rates = ["0.30"] if code.endswith(".BJ") else ["0.20"] if code.startswith(("30", "68")) else ["0.05", "0.10"]
                bands = [(previous * (1 - Decimal(rate))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) for rate in rates]
            # A price at/below any possible band needs instrument-specific exemption evidence.
            if any(close <= band for band in bands):
                candidates.append(row["ts_code"])
        except (KeyError, ValueError, ArithmeticError):
            reasons.append("invalid daily price/date")
    if candidates:
        reasons.append(f"{len(candidates)} securities require exact bands/exemption verification")
    valid = not reasons
    datasets["limit_down"] = replace(
        pool, quality="EMPTY_VALID" if valid else "UNAVAILABLE",
        error=None if valid else "; ".join(sorted(set(reasons))),
        error_type=None if valid else "SOURCE_FAILURE",
    )
    datasets["limit_down_verification"] = replace(
        pool, name="limit_down_verification", source="daily_price_band_verifier.v1",
        data_date=target, rows=[{"checked_rows": len(rows), "status": "EMPTY_VALID" if valid else "UNAVAILABLE", "unresolved_codes": candidates, "reasons": sorted(set(reasons)), "method": "conservative possible price bands; exact band preferred"}],
        quality="PASS" if valid else "PARTIAL", error=None, error_type=None,
    )
