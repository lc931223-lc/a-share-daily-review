from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any

from src.market_packet.collector import CollectedDataset


def normalize_packet_data(trade_date: date, datasets: dict[str, CollectedDataset]) -> dict[str, Any]:
    limit_up = datasets["limit_up"].rows
    failed = datasets["failed_limit"].rows
    limit_down = datasets["limit_down"].rows
    previous = datasets["previous_limit"].rows
    lhb = datasets["dragon_tiger_daily"].rows
    stock_ohlcv = datasets.get("stock_top_ohlcv").rows if datasets.get("stock_top_ohlcv") else []
    tushare_daily = datasets.get("tushare_daily_all").rows if datasets.get("tushare_daily_all") else []
    tushare_previous_daily = datasets.get("tushare_previous_daily_all").rows if datasets.get("tushare_previous_daily_all") else []
    tushare_daily_basic = datasets.get("tushare_daily_basic_all").rows if datasets.get("tushare_daily_basic_all") else []
    tushare_stock_basic = datasets.get("tushare_stock_basic").rows if datasets.get("tushare_stock_basic") else []
    industry_board_daily = datasets.get("industry_board_daily").rows if datasets.get("industry_board_daily") else []
    concept_board_daily = datasets.get("concept_board_daily").rows if datasets.get("concept_board_daily") else []
    indices = _indices(trade_date, datasets)
    stocks = _stocks(limit_up, failed, limit_down, previous, lhb, stock_ohlcv, tushare_daily, tushare_daily_basic, tushare_stock_basic)
    themes = _themes(limit_up, failed, limit_down, concept_board_daily)
    industries = _industries(limit_up, failed, limit_down, industry_board_daily, tushare_daily, tushare_stock_basic)
    capital_flow = _capital_flow(trade_date, datasets)
    highest_board = max((_number(row, "连板数") for row in limit_up), default=None)
    board_counts = {height: sum(1 for row in limit_up if _number(row, "连板数") == height) for height in (2, 3, 4)}
    board_counts["5_plus"] = sum(1 for row in limit_up if (_number(row, "连板数") or 0) >= 5)
    failed_rate = _rate(len(failed), len(limit_up) + len(failed))
    previous_red = sum(1 for row in previous if (_number(row, "涨跌幅") or 0) > 0)
    previous_limit = sum(1 for row in previous if (_number(row, "涨跌幅") or 0) >= 9.8)
    previous_down = sum(1 for row in previous if (_number(row, "涨跌幅") or 0) <= -9.8)
    prev_avg = _avg([_number(row, "涨跌幅") for row in previous])
    breadth_counts = _breadth_from_tushare_daily(tushare_daily)
    total_turnover = _tushare_turnover(tushare_daily)
    previous_turnover = _tushare_turnover(tushare_previous_daily)
    overview = {
        "trade_date": trade_date.isoformat(),
        "is_trading_day": bool(limit_up or failed or limit_down or previous),
        "market_closed": True,
        "indices": {item["name"]: item for item in indices},
        "sh_sz_turnover": _sum_index_amount(indices, {"上证指数", "深证成指"}),
        "total_market_turnover": total_turnover,
        "previous_turnover": previous_turnover,
        "turnover_delta": round(total_turnover - previous_turnover, 2) if total_turnover is not None and previous_turnover is not None else None,
        "turnover_delta_pct": _change_pct(total_turnover, previous_turnover),
        "rise_count": breadth_counts["rise_count"],
        "fall_count": breadth_counts["fall_count"],
        "flat_count": breadth_counts["flat_count"],
        "limit_up_count": len(limit_up) if limit_up else None,
        "limit_down_count": len(limit_down) if limit_down else None,
        "failed_limit_count": len(failed) if failed else None,
        "seal_rate": round(len(limit_up) / (len(limit_up) + len(failed)) * 100, 2) if limit_up or failed else None,
        "highest_board": highest_board,
        "previous_limit_up_avg_change_pct": prev_avg,
        "previous_continuous_board_performance": _previous_continuous(previous),
        "st_limit_up_count": _st_count(limit_up),
        "st_limit_down_count": _st_count(limit_down),
    }
    breadth = {
        "rise_count": breadth_counts["rise_count"],
        "fall_count": breadth_counts["fall_count"],
        "flat_count": breadth_counts["flat_count"],
        "source": "tushare.daily" if tushare_daily else None,
        "quality": "PASS" if tushare_daily else "FAIL",
    }
    limit_section = {
        "limit_up_count": len(limit_up) if limit_up else None,
        "limit_down_count": len(limit_down) if limit_down else None,
        "failed_limit_count": len(failed) if failed else None,
        "failed_limit_rate": failed_rate,
        "seal_rate": overview["seal_rate"],
        "highest_board": highest_board,
        "second_board_count": board_counts[2],
        "third_board_count": board_counts[3],
        "fourth_board_count": board_counts[4],
        "five_plus_board_count": board_counts["5_plus"],
        "promotion_rate": None,
        "previous_limit_up_performance": {
            "count": len(previous) if previous else None,
            "avg_change_pct": prev_avg,
            "high_open_rate": None,
            "red_rate": _rate(previous_red, len(previous)),
            "limit_up_rate": _rate(previous_limit, len(previous)),
            "limit_down_rate": _rate(previous_down, len(previous)),
        },
        "twenty_cm_limit_up_count": _twenty_cm_count(limit_up),
        "bse_limit_up_count": _bse_count(limit_up),
        "large_loss_count": None,
        "sky_floor_count": None,
        "floor_sky_count": None,
        "source": "akshare Eastmoney limit pools",
    }
    liquidity = {
        "sh_sz_turnover": overview["sh_sz_turnover"],
        "total_market_turnover": total_turnover,
        "previous_turnover": previous_turnover,
        "turnover_delta": overview["turnover_delta"],
        "turnover_delta_pct": overview["turnover_delta_pct"],
        "source": "tushare.daily amount sum; index amount when available",
    }
    leader_candidates = _leader_candidates(stocks)
    return {
        "market_overview": overview,
        "indices": indices,
        "market_breadth": breadth,
        "liquidity": liquidity,
        "limit_up_down": limit_section,
        "industries": industries,
        "themes": themes,
        "stocks": stocks,
        "leader_candidates": leader_candidates,
        "leader_board": leader_candidates,
        "capital_flow": capital_flow,
        "evidence": _evidence(datasets),
    }


def _indices(trade_date: date, datasets: dict[str, CollectedDataset]) -> list[dict[str, Any]]:
    names = {
        "000001.SH": "上证指数",
        "399001.SZ": "深证成指",
        "399006.SZ": "创业板指",
        "000688.SH": "科创50",
        "899050.BJ": "北证50",
    }
    rows = []
    compact = trade_date.strftime("%Y%m%d")
    dashed = trade_date.isoformat()
    for ts_code, name in names.items():
        data = datasets.get(f"index_{ts_code}")
        record = None
        if data:
            for row in data.rows:
                if str(row.get("date") or row.get("日期") or row.get("trade_date")) in {compact, dashed}:
                    record = row
                    break
        rows.append(
            {
                "name": name,
                "ts_code": ts_code,
                "close": _first_number(record, ["close", "收盘"]) if record else None,
                "change_pct": _first_number(record, ["pct_chg", "涨跌幅"]) if record else None,
                "open": _first_number(record, ["open", "开盘"]) if record else None,
                "high": _first_number(record, ["high", "最高"]) if record else None,
                "low": _first_number(record, ["low", "最低"]) if record else None,
                "volume": _first_number(record, ["volume", "成交量"]) if record else None,
                "amount": _first_number(record, ["amount", "成交额"]) if record else None,
                "source": data.source if data else None,
                "quality": "PASS" if record else "FAIL",
            }
        )
    return rows


def _stocks(
    limit_up: list[dict],
    failed: list[dict],
    limit_down: list[dict],
    previous: list[dict],
    lhb: list[dict],
    stock_ohlcv: list[dict],
    tushare_daily: list[dict],
    tushare_daily_basic: list[dict],
    tushare_stock_basic: list[dict],
) -> list[dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    basic_by_code = {_ts_code(row): row for row in tushare_stock_basic if _ts_code(row)}
    for source_name, source_rows in (("limit_up", limit_up), ("failed_limit", failed), ("limit_down", limit_down), ("previous_limit_up", previous), ("dragon_tiger", lhb)):
        for row in source_rows:
            code = _code(row)
            if not code:
                continue
            item = rows.setdefault(code, _empty_stock(code, row))
            item["sources"].append(source_name)
            if source_name == "limit_up":
                item["limit_up"] = True
                item["continuous_board_count"] = _number(row, "连板数")
                item["board_count"] = _number(row, "连板数")
                item["opened_limit"] = bool(_number(row, "炸板次数"))
            elif source_name == "failed_limit":
                item["failed_limit"] = True
                item["opened_limit"] = True
            elif source_name == "limit_down":
                item["limit_down"] = True
            elif source_name == "previous_limit_up":
                item["previous_day_change"] = _number(row, "涨跌幅")
            item["stock_name"] = item["stock_name"] or str(row.get("名称") or row.get("name") or "")
            item["industry"] = item["industry"] or row.get("所属行业")
            item["change_pct"] = item["change_pct"] if item["change_pct"] is not None else _number(row, "涨跌幅")
            item["close"] = item["close"] if item["close"] is not None else _number(row, "最新价")
            item["amount"] = item["amount"] if item["amount"] is not None else _number(row, "成交额")
            item["turnover_rate"] = item["turnover_rate"] if item["turnover_rate"] is not None else _number(row, "换手率")
            item["market_cap"] = item["market_cap"] if item["market_cap"] is not None else _number(row, "总市值")
            item["float_market_cap"] = item["float_market_cap"] if item["float_market_cap"] is not None else _number(row, "流通市值")
            _apply_stock_basic(item, basic_by_code.get(_ts_code_from_code(code)))
    daily_by_code = {_ts_code(row): row for row in tushare_daily if _ts_code(row)}
    daily_basic_by_code = {_ts_code(row): row for row in tushare_daily_basic if _ts_code(row)}
    for ts_code, daily_row in daily_by_code.items():
        code = ts_code.split(".")[0]
        if code not in rows:
            continue
        item = rows[code]
        if "tushare_daily" not in item["sources"]:
            item["sources"].append("tushare_daily")
        _apply_tushare_daily(item, daily_row)
        _apply_tushare_daily_basic(item, daily_basic_by_code.get(ts_code))
        _apply_stock_basic(item, basic_by_code.get(ts_code))
    for hist_row in stock_ohlcv:
        code = _hist_code(hist_row)
        if not code:
            continue
        item = rows.setdefault(code, _empty_stock(code, hist_row))
        if "stock_top_ohlcv" not in item["sources"]:
            item["sources"].append("stock_top_ohlcv")
        item["open"] = item["open"] if item["open"] is not None else _first_number(hist_row, ["开盘", "open"])
        item["high"] = item["high"] if item["high"] is not None else _first_number(hist_row, ["最高", "high"])
        item["low"] = item["low"] if item["low"] is not None else _first_number(hist_row, ["最低", "low"])
        item["close"] = item["close"] if item["close"] is not None else _first_number(hist_row, ["收盘", "close"])
        item["volume"] = item["volume"] if item["volume"] is not None else _first_number(hist_row, ["成交量", "volume"])
        item["amount"] = item["amount"] if item["amount"] is not None else _first_number(hist_row, ["成交额", "amount"])
        item["turnover_rate"] = item["turnover_rate"] if item["turnover_rate"] is not None else _first_number(hist_row, ["换手率", "turnover_rate"])
        item["change_pct"] = item["change_pct"] if item["change_pct"] is not None else _first_number(hist_row, ["涨跌幅", "pct_chg"])
    for item in rows.values():
        item["themes"] = [item["industry"]] if item.get("industry") else []
        item["leader_candidate_score"] = _leader_score(item)
        item["capacity_candidate_score"] = _capacity_score(item)
        item["catch_up_candidate_score"] = _catch_up_score(item)
    return sorted(rows.values(), key=lambda row: max(row["leader_candidate_score"], row["capacity_candidate_score"], row["catch_up_candidate_score"]), reverse=True)[:220]


def _themes(limit_up: list[dict], failed: list[dict], limit_down: list[dict], concept_board_daily: list[dict]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = defaultdict(lambda: {"top_gainers": [], "top_losers": [], "leader_candidates": [], "capacity_candidates": [], "catch_up_candidates": [], "amount": 0, "limit_up_count": 0, "limit_down_count": 0, "failed_limit_count": 0})
    for row in limit_up:
        name = str(row.get("所属行业") or "未分类")
        item = grouped[name]
        item["theme_name"] = name
        item["normalized_name"] = name
        item["limit_up_count"] += 1
        item["amount"] += _number(row, "成交额") or 0
        stock = {"stock_code": _code(row), "stock_name": row.get("名称"), "change_pct": _number(row, "涨跌幅"), "amount": _number(row, "成交额"), "board_count": _number(row, "连板数")}
        item["top_gainers"].append(stock)
        if (_number(row, "连板数") or 0) >= 2:
            item["leader_candidates"].append(stock)
        elif (_number(row, "成交额") or 0) >= 500_000_000:
            item["capacity_candidates"].append(stock)
        else:
            item["catch_up_candidates"].append(stock)
    for row in failed:
        name = str(row.get("所属行业") or "未分类")
        item = grouped[name]
        item["theme_name"] = name
        item["normalized_name"] = name
        item["failed_limit_count"] += 1
        item["amount"] += _number(row, "成交额") or 0
    for row in limit_down:
        name = str(row.get("所属行业") or "未分类")
        item = grouped[name]
        item["theme_name"] = name
        item["normalized_name"] = name
        item["limit_down_count"] += 1
        item["top_losers"].append({"stock_code": _code(row), "stock_name": row.get("名称"), "change_pct": _number(row, "涨跌幅"), "amount": _number(row, "成交额")})
    rows_by_name: dict[str, dict[str, Any]] = {}
    for row in concept_board_daily:
        name = str(row.get("board_name") or row.get("板块名称") or row.get("名称") or "")
        if not name:
            continue
        rows_by_name[name] = {
            "theme_name": name,
            "normalized_name": name,
            "change_pct": _first_number(row, ["涨跌幅", "change_pct", "pct_chg"]),
            "rise_count": _first_number(row, ["上涨家数", "rise_count"]),
            "fall_count": _first_number(row, ["下跌家数", "fall_count"]),
            "limit_up_count": _first_number(row, ["涨停家数", "limit_up_count"]),
            "limit_down_count": _first_number(row, ["跌停家数", "limit_down_count"]),
            "failed_limit_count": None,
            "amount": _first_number(row, ["成交额", "amount"]),
            "amount_change": None,
            "turnover_rate": _first_number(row, ["换手率", "turnover_rate"]),
            "main_net_inflow": None,
            "top_gainers": [],
            "top_losers": [],
            "leader_candidates": [],
            "capacity_candidates": [],
            "catch_up_candidates": [],
            "source": "Eastmoney concept board historical via AKShare",
            "quality": "PASS",
        }
    for item in grouped.values():
        rise = item["limit_up_count"]
        fall = item["limit_down_count"] + item["failed_limit_count"]
        row = rows_by_name.setdefault(
            item["theme_name"],
            {
                "theme_name": item["theme_name"],
                "normalized_name": item["normalized_name"],
                "change_pct": None,
                "rise_count": rise or None,
                "fall_count": fall or None,
                "limit_up_count": item["limit_up_count"] or None,
                "limit_down_count": item["limit_down_count"] or None,
                "failed_limit_count": item["failed_limit_count"] or None,
                "amount": round(item["amount"], 2) if item["amount"] else None,
                "amount_change": None,
                "turnover_rate": None,
                "main_net_inflow": None,
                "top_gainers": [],
                "top_losers": [],
                "leader_candidates": [],
                "capacity_candidates": [],
                "catch_up_candidates": [],
                "source": "Eastmoney limit pools via AKShare",
                "quality": "PARTIAL",
            },
        )
        row["limit_up_count"] = item["limit_up_count"] or row.get("limit_up_count")
        row["limit_down_count"] = item["limit_down_count"] or row.get("limit_down_count")
        row["failed_limit_count"] = item["failed_limit_count"] or row.get("failed_limit_count")
        row["top_gainers"] = sorted(item["top_gainers"], key=lambda x: (x.get("board_count") or 0, x.get("amount") or 0), reverse=True)[:10]
        row["top_losers"] = sorted(item["top_losers"], key=lambda x: x.get("change_pct") or 0)[:10]
        row["leader_candidates"] = item["leader_candidates"][:10]
        row["capacity_candidates"] = item["capacity_candidates"][:10]
        row["catch_up_candidates"] = item["catch_up_candidates"][:10]
    return sorted(rows_by_name.values(), key=lambda row: (row.get("change_pct") is not None, row.get("limit_up_count") or 0, row.get("amount") or 0), reverse=True)[:160]


def _industries(
    limit_up: list[dict],
    failed: list[dict],
    limit_down: list[dict],
    industry_board_daily: list[dict],
    tushare_daily: list[dict],
    tushare_stock_basic: list[dict],
) -> list[dict[str, Any]]:
    counts = _industry_breadth_counts(tushare_daily, tushare_stock_basic)
    limit_counts = _industry_limit_counts(limit_up, failed, limit_down)
    rows_by_name: dict[str, dict[str, Any]] = {}
    for row in industry_board_daily:
        name = str(row.get("board_name") or row.get("板块名称") or row.get("名称") or "")
        if not name:
            continue
        rows_by_name[name] = {
            "name": name,
            "change_pct": _first_number(row, ["涨跌幅", "change_pct", "pct_chg"]),
            "amount": _first_number(row, ["成交额", "amount"]),
            "turnover_rate": _first_number(row, ["换手率", "turnover_rate"]),
            "rise_count": counts.get(name, {}).get("rise_count"),
            "fall_count": counts.get(name, {}).get("fall_count"),
            "limit_up_count": limit_counts.get(name, {}).get("limit_up_count"),
            "limit_down_count": limit_counts.get(name, {}).get("limit_down_count"),
            "failed_limit_count": limit_counts.get(name, {}).get("failed_limit_count"),
            "main_net_inflow": None,
            "main_net_inflow_pct": None,
            "top_stocks": [],
            "five_day_change_pct": None,
            "twenty_day_change_pct": None,
            "source": "Eastmoney industry board historical via AKShare",
            "quality": "PASS",
        }
    for name, value in {**counts, **limit_counts}.items():
        row = rows_by_name.setdefault(
            name,
            {
                "name": name,
                "change_pct": None,
                "amount": None,
                "turnover_rate": None,
                "rise_count": None,
                "fall_count": None,
                "limit_up_count": None,
                "limit_down_count": None,
                "failed_limit_count": None,
                "main_net_inflow": None,
                "main_net_inflow_pct": None,
                "top_stocks": [],
                "five_day_change_pct": None,
                "twenty_day_change_pct": None,
                "source": "Tushare stock_basic/daily and Eastmoney limit pools",
                "quality": "PARTIAL",
            },
        )
        for key in ("rise_count", "fall_count", "limit_up_count", "limit_down_count", "failed_limit_count", "change_pct", "amount"):
            if value.get(key) is not None:
                row[key] = value[key]
    return sorted(rows_by_name.values(), key=lambda row: (row.get("change_pct") is not None, row.get("amount") or 0), reverse=True)


def _capital_flow(trade_date: date, datasets: dict[str, CollectedDataset]) -> dict[str, Any]:
    nb = _row_by_date(datasets["northbound_hist"].rows, trade_date, "日期")
    net_buy = _number(nb, "当日成交净买额") if nb else None
    buy = _number(nb, "买入成交额") if nb else None
    sell = _number(nb, "卖出成交额") if nb else None
    amounts = (net_buy, buy, sell)
    if not nb or all(value is None for value in amounts):
        northbound_quality = "UNAVAILABLE"
        northbound_reason = "目标日期未取得可验证的北向资金关键金额字段"
    elif any(value is None for value in amounts):
        northbound_quality = "PARTIAL"
        northbound_reason = "北向资金金额字段仅部分可用"
    else:
        northbound_quality = "PASS"
        northbound_reason = None
    sse_margin = datasets.get("sse_margin")
    szse_margin = datasets.get("szse_margin")
    sse_row = sse_margin.rows[0] if sse_margin and sse_margin.rows else None
    szse_row = szse_margin.rows[0] if szse_margin and szse_margin.rows else None
    margin_quality = "PASS" if sse_row and szse_row else "PARTIAL" if sse_row or szse_row else "UNAVAILABLE"
    return {
        "northbound": {
            "net_buy_amount": net_buy,
            "buy_amount": buy,
            "sell_amount": sell,
            "source": datasets["northbound_hist"].source,
            "quality": northbound_quality,
            "reason": northbound_reason,
        },
        "margin": {
            "sse": sse_row,
            "szse": szse_row,
            "source": "AKShare SSE/SZSE margin datasets",
            "quality": margin_quality,
        },
        "industry_fund_flow": None,
        "concept_fund_flow": None,
        "current_only_exclusions": [
            {
                "dataset": name,
                "status": "not_historical_available",
                "reason": "current-only source is not written into historical packet fields unless source_data_date equals requested trade_date",
            }
            for name in ("industry_fund_flow_current", "concept_fund_flow_current", "hsgt_summary")
            if datasets.get(name) and datasets[name].freshness == "current_only"
        ],
    }


def _leader_candidates(stocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for stock in stocks[:60]:
        rows.append(
            {
                "stock_code": stock["stock_code"],
                "stock_name": stock["stock_name"],
                "industry": stock["industry"],
                "leader_candidate_score": stock["leader_candidate_score"],
                "capacity_candidate_score": stock["capacity_candidate_score"],
                "catch_up_candidate_score": stock["catch_up_candidate_score"],
                "candidate_only": True,
                "basis": "objective proxies: board height, limit status, amount, float market cap, failed-limit flags",
            }
        )
    return rows


def _evidence(datasets: dict[str, CollectedDataset]) -> list[dict[str, Any]]:
    rows = []
    for item in datasets.values():
        if item.quality == "PASS":
            rows.append(
                {
                    "evidence_level": "B",
                    "source": item.source,
                    "dataset": item.name,
                    "retrieved_at": item.retrieved_at.isoformat(),
                    "data_date": item.data_date.isoformat() if item.data_date else None,
                    "record_count": len(item.rows),
                    "url": None,
                    "fact": f"{item.name} returned {len(item.rows)} rows",
                }
            )
    return rows


def _empty_stock(code: str, row: dict[str, Any]) -> dict[str, Any]:
    return {
        "stock_code": code,
        "stock_name": str(row.get("名称") or row.get("name") or ""),
        "industry": row.get("所属行业"),
        "themes": [],
        "open": None,
        "high": None,
        "low": None,
        "close": _number(row, "最新价"),
        "change_pct": _number(row, "涨跌幅"),
        "volume": None,
        "amount": _number(row, "成交额"),
        "turnover_rate": _number(row, "换手率"),
        "market_cap": _number(row, "总市值"),
        "float_market_cap": _number(row, "流通市值"),
        "limit_up": False,
        "limit_down": False,
        "board_count": None,
        "continuous_board_count": None,
        "opened_limit": False,
        "failed_limit": False,
        "previous_day_change": None,
        "five_day_change": None,
        "twenty_day_change": None,
        "five_day_amount_average": None,
        "twenty_day_amount_average": None,
        "relative_volume": None,
        "sources": [],
    }


def _code(row: dict[str, Any]) -> str:
    value = row.get("代码") or row.get("code") or ""
    return str(value).split(".")[0].zfill(6) if value != "" else ""


def _hist_code(row: dict[str, Any]) -> str:
    value = row.get("股票代码") or row.get("source_stock_code") or row.get("代码") or row.get("code") or ""
    return str(value).split(".")[0].zfill(6) if value != "" else ""


def _ts_code(row: dict[str, Any] | None) -> str:
    if not row:
        return ""
    value = row.get("ts_code") or ""
    return str(value).upper()


def _ts_code_from_code(code: str) -> str:
    if code.startswith(("5", "6", "9")):
        return f"{code}.SH"
    if code.startswith(("0", "2", "3")):
        return f"{code}.SZ"
    if code.startswith(("4", "8")):
        return f"{code}.BJ"
    return code


def _apply_tushare_daily(item: dict[str, Any], row: dict[str, Any] | None) -> None:
    if not row:
        return
    item["open"] = item["open"] if item["open"] is not None else _number(row, "open")
    item["high"] = item["high"] if item["high"] is not None else _number(row, "high")
    item["low"] = item["low"] if item["low"] is not None else _number(row, "low")
    item["close"] = item["close"] if item["close"] is not None else _number(row, "close")
    item["change_pct"] = item["change_pct"] if item["change_pct"] is not None else _number(row, "pct_chg")
    item["volume"] = item["volume"] if item["volume"] is not None else _number(row, "vol")
    amount = _number(row, "amount")
    item["amount"] = item["amount"] if item["amount"] is not None else round(amount * 1000, 2) if amount is not None else None


def _apply_tushare_daily_basic(item: dict[str, Any], row: dict[str, Any] | None) -> None:
    if not row:
        return
    item["turnover_rate"] = item["turnover_rate"] if item["turnover_rate"] is not None else _number(row, "turnover_rate")
    total_mv = _number(row, "total_mv")
    circ_mv = _number(row, "circ_mv")
    item["market_cap"] = item["market_cap"] if item["market_cap"] is not None else round(total_mv * 10000, 2) if total_mv is not None else None
    item["float_market_cap"] = item["float_market_cap"] if item["float_market_cap"] is not None else round(circ_mv * 10000, 2) if circ_mv is not None else None


def _apply_stock_basic(item: dict[str, Any], row: dict[str, Any] | None) -> None:
    if not row:
        return
    item["stock_name"] = item["stock_name"] or str(row.get("name") or "")
    item["industry"] = item["industry"] or row.get("industry")


def _industry_breadth_counts(tushare_daily: list[dict], tushare_stock_basic: list[dict]) -> dict[str, dict[str, int | None]]:
    industry_by_code = {_ts_code(row): row.get("industry") for row in tushare_stock_basic if _ts_code(row) and row.get("industry")}
    grouped: dict[str, dict[str, Any]] = defaultdict(lambda: {"rise_count": 0, "fall_count": 0, "change_values": [], "amount": 0.0})
    for row in tushare_daily:
        industry = industry_by_code.get(_ts_code(row))
        change = _number(row, "pct_chg")
        if not industry or change is None:
            continue
        grouped[str(industry)]["change_values"].append(change)
        amount = _number(row, "amount")
        if amount is not None:
            grouped[str(industry)]["amount"] += amount * 1000
        if change > 0:
            grouped[str(industry)]["rise_count"] += 1
        elif change < 0:
            grouped[str(industry)]["fall_count"] += 1
    return {
        name: {
            "rise_count": values["rise_count"] or None,
            "fall_count": values["fall_count"] or None,
            "change_pct": round(sum(values["change_values"]) / len(values["change_values"]), 2) if values["change_values"] else None,
            "amount": round(values["amount"], 2) if values["amount"] else None,
        }
        for name, values in grouped.items()
    }


def _industry_limit_counts(limit_up: list[dict], failed: list[dict], limit_down: list[dict]) -> dict[str, dict[str, int | None]]:
    grouped: dict[str, dict[str, int]] = defaultdict(lambda: {"limit_up_count": 0, "limit_down_count": 0, "failed_limit_count": 0})
    for key, rows in (("limit_up_count", limit_up), ("failed_limit_count", failed), ("limit_down_count", limit_down)):
        for row in rows:
            industry = row.get("所属行业")
            if industry:
                grouped[str(industry)][key] += 1
    return {name: {key: value or None for key, value in values.items()} for name, values in grouped.items()}


def _number(row: dict[str, Any] | None, key: str) -> float | None:
    if not row:
        return None
    value = row.get(key)
    if value in ("", None):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _first_number(row: dict[str, Any] | None, keys: list[str]) -> float | None:
    for key in keys:
        value = _number(row, key)
        if value is not None:
            return value
    return None


def _avg(values: list[float | None]) -> float | None:
    clean = [value for value in values if value is not None]
    return round(sum(clean) / len(clean), 2) if clean else None


def _rate(count: int, total: int) -> float | None:
    return round(count / total * 100, 2) if total else None


def _change_pct(current: float | None, previous: float | None) -> float | None:
    if current is None or previous in (None, 0):
        return None
    return round((current - previous) / previous * 100, 2)


def _breadth_from_tushare_daily(rows: list[dict[str, Any]]) -> dict[str, int | None]:
    if not rows:
        return {"rise_count": None, "fall_count": None, "flat_count": None}
    changes = [_number(row, "pct_chg") for row in rows]
    clean = [value for value in changes if value is not None]
    return {
        "rise_count": sum(1 for value in clean if value > 0),
        "fall_count": sum(1 for value in clean if value < 0),
        "flat_count": sum(1 for value in clean if value == 0),
    }


def _tushare_turnover(rows: list[dict[str, Any]]) -> float | None:
    amounts = [_number(row, "amount") for row in rows]
    clean = [value for value in amounts if value is not None]
    return round(sum(clean) * 1000, 2) if clean else None


def _row_by_date(rows: list[dict[str, Any]], trade_date: date, key: str) -> dict[str, Any] | None:
    expected = {trade_date.isoformat(), trade_date.strftime("%Y%m%d")}
    for row in rows:
        if str(row.get(key)) in expected:
            return row
    return None


def _sum_index_amount(indices: list[dict[str, Any]], names: set[str]) -> float | None:
    amounts = [item["amount"] for item in indices if item["name"] in names and item["amount"] is not None]
    return round(sum(amounts), 2) if amounts else None


def _previous_continuous(rows: list[dict[str, Any]]) -> dict[str, Any]:
    continuous = [row for row in rows if (_number(row, "昨日连板数") or 0) >= 2]
    return {
        "count": len(continuous) if rows else None,
        "avg_change_pct": _avg([_number(row, "涨跌幅") for row in continuous]),
        "red_rate": _rate(sum(1 for row in continuous if (_number(row, "涨跌幅") or 0) > 0), len(continuous)),
    }


def _st_count(rows: list[dict[str, Any]]) -> int | None:
    return sum(1 for row in rows if "ST" in str(row.get("名称") or "").upper()) if rows else None


def _twenty_cm_count(rows: list[dict[str, Any]]) -> int | None:
    if not rows:
        return None
    return sum(1 for row in rows if _code(row).startswith(("30", "68")) and (_number(row, "涨跌幅") or 0) >= 19)


def _bse_count(rows: list[dict[str, Any]]) -> int | None:
    if not rows:
        return None
    return sum(1 for row in rows if _code(row).startswith(("8", "9")))


def _leader_score(stock: dict[str, Any]) -> int:
    score = 0
    score += min(45, int(stock.get("continuous_board_count") or 0) * 12)
    score += 25 if stock.get("limit_up") else 0
    score -= 25 if stock.get("failed_limit") else 0
    score += 10 if (stock.get("amount") or 0) >= 500_000_000 else 0
    return max(0, min(100, score))


def _capacity_score(stock: dict[str, Any]) -> int:
    score = 20 if stock.get("limit_up") else 5
    score += 35 if (stock.get("amount") or 0) >= 1_000_000_000 else 15 if (stock.get("amount") or 0) >= 500_000_000 else 0
    score += 20 if (stock.get("float_market_cap") or 0) >= 5_000_000_000 else 0
    score -= 20 if stock.get("failed_limit") else 0
    return max(0, min(100, score))


def _catch_up_score(stock: dict[str, Any]) -> int:
    if not stock.get("limit_up") or (stock.get("continuous_board_count") or 0) > 1:
        return 0
    score = 45
    score += 15 if (stock.get("amount") or 0) < 800_000_000 else 5
    score -= 15 if stock.get("opened_limit") else 0
    return max(0, min(100, score))
