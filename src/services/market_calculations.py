from dataclasses import dataclass


@dataclass(frozen=True)
class MarketBreadth:
    advancers: int
    flat: int
    decliners: int
    turnover_yi: float


def quotes(pct_changes: list[float]) -> list[dict]:
    return [
        {"ts_code": f"600{index:03d}.SH", "pct_chg": pct_chg, "amount": 0.0}
        for index, pct_chg in enumerate(pct_changes, start=1)
    ]


def calculate_breadth(quote_rows: list[dict]) -> MarketBreadth:
    advancers = 0
    flat = 0
    decliners = 0
    amount_thousand_yuan = 0.0
    for row in quote_rows:
        pct_chg = float(row["pct_chg"])
        if pct_chg > 0:
            advancers += 1
        elif pct_chg < 0:
            decliners += 1
        else:
            flat += 1
        amount_thousand_yuan += float(row.get("amount") or 0)
    return MarketBreadth(
        advancers=advancers,
        flat=flat,
        decliners=decliners,
        turnover_yi=amount_thousand_yuan / 100_000,
    )


def calculate_limit_price(previous_close: float, ts_code: str, is_st: bool = False) -> float:
    if is_st:
        ratio = 0.05
    elif ts_code.startswith(("300", "688")):
        ratio = 0.20
    elif ts_code.endswith(".BJ"):
        ratio = 0.30
    else:
        ratio = 0.10
    return round(previous_close * (1 + ratio) + 1e-8, 2)
