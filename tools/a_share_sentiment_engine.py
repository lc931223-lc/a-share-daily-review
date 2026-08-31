from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from datetime import date as current_date
from pathlib import Path
from typing import Callable

import pandas as pd

try:
    import akshare as ak
except Exception:  # pragma: no cover - handled at runtime for clear data gaps
    ak = None


INDEXES = {
    "sh000001": "上证指数",
    "sz399001": "深证成指",
    "sz399006": "创业板指",
    "sh000300": "沪深300",
    "sh000905": "中证500",
    "sh000852": "中证1000",
    "sh000688": "科创50",
}

POOL_FILES = {
    "limit_up": "limit_up",
    "failed_limit": "failed_limit",
    "limit_down": "limit_down",
    "previous_limit": "previous_limit",
}


def normalize_date(value: str) -> str:
    return value.replace("-", "").replace("/", "").strip()


def dashed_date(value: str) -> str:
    value = normalize_date(value)
    return f"{value[:4]}-{value[4:6]}-{value[6:8]}"


def range_label(start: str, end: str) -> str:
    return f"{dashed_date(start)}_to_{dashed_date(end)}"


def col(df: pd.DataFrame, index: int) -> pd.Series:
    if df.empty or len(df.columns) <= index:
        return pd.Series(dtype="object")
    return df.iloc[:, index]


def to_numeric(series: pd.Series, default: float = 0) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").fillna(default)


def clean_number(value, default=0):
    try:
        if value is None:
            return default
        if isinstance(value, float) and math.isnan(value):
            return default
        if pd.isna(value):
            return default
        return value
    except Exception:
        return default


def json_safe(value):
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [json_safe(v) for v in value]
    if isinstance(value, tuple):
        return [json_safe(v) for v in value]
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d")
    if hasattr(value, "item"):
        try:
            return json_safe(value.item())
        except Exception:
            pass
    if isinstance(value, float):
        return None if math.isnan(value) else round(value, 4)
    return value


def safe_read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    for encoding in ("utf-8-sig", "utf-8", "gbk"):
        try:
            df = pd.read_csv(path, encoding=encoding, dtype={"code": "string"})
            if "code" in df.columns:
                df["code"] = df["code"].astype(str).str.zfill(6)
            return df
        except Exception:
            continue
    return pd.DataFrame()


def safe_fetch(func: Callable, date: str) -> tuple[pd.DataFrame, str | None]:
    if ak is None:
        return pd.DataFrame(), "akshare 未成功导入"
    try:
        return func(date=date).copy(), None
    except Exception as exc:
        return pd.DataFrame(), f"{func.__name__}({date}) 拉取失败：{exc.__class__.__name__}"


def parse_limit_up(df: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "code",
        "name",
        "pct",
        "amount",
        "turnover",
        "seal_amount",
        "first_limit_time",
        "last_limit_time",
        "open_times",
        "board_stat",
        "board_count",
        "industry",
    ]
    if df.empty:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame(
        {
            "code": col(df, 1).astype(str).str.zfill(6),
            "name": col(df, 2).astype(str),
            "pct": to_numeric(col(df, 3)),
            "amount": to_numeric(col(df, 5)),
            "turnover": to_numeric(col(df, 8)),
            "seal_amount": to_numeric(col(df, 9)),
            "first_limit_time": col(df, 10).astype(str),
            "last_limit_time": col(df, 11).astype(str),
            "open_times": to_numeric(col(df, 12)).astype(int),
            "board_stat": col(df, 13).astype(str),
            "board_count": to_numeric(col(df, 14), default=1).astype(int),
            "industry": col(df, 15).astype(str),
        }
    )


def parse_failed_limit(df: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "code",
        "name",
        "pct",
        "amount",
        "turnover",
        "open_times",
        "board_stat",
        "amplitude",
        "industry",
    ]
    if df.empty:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame(
        {
            "code": col(df, 1).astype(str).str.zfill(6),
            "name": col(df, 2).astype(str),
            "pct": to_numeric(col(df, 3)),
            "amount": to_numeric(col(df, 6)),
            "turnover": to_numeric(col(df, 9)),
            "open_times": to_numeric(col(df, 12)).astype(int),
            "board_stat": col(df, 13).astype(str),
            "amplitude": to_numeric(col(df, 14)),
            "industry": col(df, 15).astype(str),
        }
    )


def parse_limit_down(df: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "code",
        "name",
        "pct",
        "amount",
        "turnover",
        "seal_amount",
        "last_limit_time",
        "down_count",
        "open_times",
        "industry",
    ]
    if df.empty:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame(
        {
            "code": col(df, 1).astype(str).str.zfill(6),
            "name": col(df, 2).astype(str),
            "pct": to_numeric(col(df, 3)),
            "amount": to_numeric(col(df, 5)),
            "turnover": to_numeric(col(df, 9)),
            "seal_amount": to_numeric(col(df, 10)),
            "last_limit_time": col(df, 11).astype(str),
            "down_count": to_numeric(col(df, 13), default=1).astype(int),
            "open_times": to_numeric(col(df, 14)).astype(int),
            "industry": col(df, 15).astype(str),
        }
    )


def parse_previous_limit(df: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "code",
        "name",
        "pct",
        "amount",
        "turnover",
        "speed",
        "amplitude",
        "last_limit_time",
        "prev_board_count",
        "board_stat",
        "industry",
    ]
    if df.empty:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame(
        {
            "code": col(df, 1).astype(str).str.zfill(6),
            "name": col(df, 2).astype(str),
            "pct": to_numeric(col(df, 3)),
            "amount": to_numeric(col(df, 6)),
            "turnover": to_numeric(col(df, 9)),
            "speed": to_numeric(col(df, 10)),
            "amplitude": to_numeric(col(df, 11)),
            "last_limit_time": col(df, 12).astype(str),
            "prev_board_count": to_numeric(col(df, 13), default=1).astype(int),
            "board_stat": col(df, 14).astype(str),
            "industry": col(df, 15).astype(str),
        }
    )


PARSERS = {
    "limit_up": parse_limit_up,
    "failed_limit": parse_failed_limit,
    "limit_down": parse_limit_down,
    "previous_limit": parse_previous_limit,
}


def load_or_fetch_pool(
    date_value: str,
    pool_name: str,
    output_dir: Path,
    refresh: bool,
) -> tuple[pd.DataFrame, str | None]:
    path = output_dir / f"{date_value}_{POOL_FILES[pool_name]}.csv"
    parser = PARSERS[pool_name]

    if path.exists() and not refresh:
        parsed = safe_read_csv(path)
        if not parsed.empty:
            parsed.to_csv(path, index=False, encoding="utf-8")
        return parsed, None

    func_name = {
        "limit_up": "stock_zt_pool_em",
        "failed_limit": "stock_zt_pool_zbgc_em",
        "limit_down": "stock_zt_pool_dtgc_em",
        "previous_limit": "stock_zt_pool_previous_em",
    }[pool_name]
    func = getattr(ak, func_name, None) if ak is not None else None
    if func is None:
        cached = safe_read_csv(path)
        if not cached.empty:
            return cached, f"{func_name} 不可用，使用本地缓存"
        return pd.DataFrame(), f"{func_name} 不可用且没有本地缓存"

    raw, error = safe_fetch(func, date_value)
    if raw.empty and path.exists():
        cached = safe_read_csv(path)
        if not cached.empty:
            return cached, f"{error}，使用本地缓存"

    parsed = parser(raw)
    parsed.to_csv(path, index=False, encoding="utf-8")
    return parsed, error


def cached_dates(output_dir: Path, start: str, end: str) -> list[str]:
    if not output_dir.exists():
        return []
    dates = set()
    for path in output_dir.glob("*_limit_up.csv"):
        date_value = path.name.split("_", 1)[0]
        if start <= date_value <= end:
            dates.add(date_value)
    return sorted(dates)


def trading_dates(start: str, end: str, output_dir: Path) -> tuple[list[str], list[str]]:
    gaps: list[str] = []
    if ak is not None:
        try:
            df = ak.stock_zh_index_daily(symbol="sh000001")
            df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y%m%d")
            dates = sorted(df[(df["date"] >= start) & (df["date"] <= end)]["date"].tolist())
            if dates:
                return dates, gaps
        except Exception as exc:
            gaps.append(f"交易日历拉取失败：{exc.__class__.__name__}")

    dates = cached_dates(output_dir, start, end)
    if dates:
        gaps.append("使用本地涨停池缓存推导交易日")
        return dates, gaps
    return [], gaps + ["无法取得交易日列表"]


def index_daily(dates: list[str]) -> tuple[dict, list[str]]:
    gaps: list[str] = []
    rows = {}
    if ak is None:
        return rows, ["akshare 未成功导入，指数数据缺失"]

    for code, name in INDEXES.items():
        try:
            df = ak.stock_zh_index_daily(symbol=code)
            df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y%m%d")
            df = df[df["date"].isin(dates)].sort_values("date").reset_index(drop=True)
            if df.empty:
                gaps.append(f"{name} 在目标区间内无日线数据")
                continue
            daily = []
            for idx, row in df.iterrows():
                pct = None
                if idx > 0:
                    previous_close = float(df.iloc[idx - 1]["close"])
                    pct = round((float(row["close"]) / previous_close - 1) * 100, 2)
                daily.append(
                    {
                        "date": row["date"],
                        "close": round(float(row["close"]), 3),
                        "pct": pct,
                    }
                )
            rows[code] = {
                "name": name,
                "daily": daily,
                "period_return_pct": round(
                    (float(df.iloc[-1]["close"]) / float(df.iloc[0]["close"]) - 1) * 100, 2
                ),
            }
        except Exception as exc:
            gaps.append(f"{name} 日线拉取失败：{exc.__class__.__name__}")
    return rows, gaps


def classify_sentiment(day: dict) -> tuple[int, str, str, str, list[str], list[str]]:
    score = 50
    warnings: list[str] = []
    zt = day["limit_up_count"]
    dt = day["limit_down_count"]
    failed = day["failed_limit_count"]
    touch = zt + failed
    failed_rate = day["failed_limit_rate"]
    prev_avg = day["prev_limit_avg_pct"]
    prev_positive = day["prev_limit_positive_rate"]
    height = day["highest_board"]
    multi = day["multi_board_count"]

    if zt >= 80:
        score += 18
    elif zt >= 50:
        score += 10
    elif zt < 30:
        score -= 8

    if dt >= 20:
        score -= 18
    elif dt >= 10:
        score -= 10
    elif dt <= 3:
        score += 6

    if touch > 0:
        if failed_rate >= 35:
            score -= 14
        elif failed_rate >= 25:
            score -= 8
        elif failed_rate <= 18:
            score += 6
    else:
        warnings.append("涨停池和炸板池均为空，短线情绪评分不可靠")

    if prev_avg >= 2:
        score += 10
    elif prev_avg >= 0:
        score += 4
    elif prev_avg <= -2:
        score -= 10

    if prev_positive >= 60:
        score += 4
    elif prev_positive < 40:
        score -= 4

    if height >= 5:
        score += 10
    elif height >= 3:
        score += 4
    else:
        score -= 4

    if multi >= 15:
        score += 4
    elif multi <= 5:
        score -= 4

    score = max(0, min(100, int(score)))
    if score >= 85:
        state, label, position = "高潮过热", "高潮/过热", "3-5成"
    elif score >= 65:
        state, label, position = "主升", "强势主升", "6-8成"
    elif score >= 50:
        state, label, position = "修复", "修复偏强", "3-5成"
    elif score >= 35:
        state, label, position = "分歧", "分歧偏弱", "0-3成"
    elif zt < 20 and dt >= 20:
        state, label, position = "冰点", "冰点", "0-2成"
    else:
        state, label, position = "退潮", "退潮", "0-2成"

    evidence = [
        f"涨停 {zt} 只，炸板 {failed} 只，炸板率 {failed_rate:.2f}%",
        f"跌停 {dt} 只，最高连板 {height} 板，连板股 {multi} 只",
        f"昨日涨停平均反馈 {prev_avg:+.2f}%，红盘率 {prev_positive:.2f}%",
    ]
    if state == "高潮过热":
        warnings.append("情绪读数过高，容易进入一致性拥挤后的分歧窗口")
    if failed_rate >= 25:
        warnings.append("炸板率偏高，接力分歧仍重")
    if dt >= 10:
        warnings.append("跌停数量偏多，亏钱效应未完全消除")

    return score, state, label, position, evidence, warnings


def build_market_dashboard(day: dict) -> dict:
    score, state, label, position, evidence, warnings = classify_sentiment(day)
    return {
        "sentiment_score": score,
        "sentiment_state": state,
        "sentiment_label": label,
        "position_band": position,
        "evidence": evidence,
        "warnings": warnings,
    }


def theme_stats(zt: pd.DataFrame, failed: pd.DataFrame) -> dict[str, dict]:
    stats: dict[str, dict] = {}
    industries = set(zt.get("industry", pd.Series(dtype=str)).dropna().astype(str))
    industries.update(failed.get("industry", pd.Series(dtype=str)).dropna().astype(str))
    industries.discard("")
    industries.discard("nan")

    for industry in industries:
        zt_part = zt[zt["industry"].astype(str) == industry] if not zt.empty else pd.DataFrame()
        failed_part = (
            failed[failed["industry"].astype(str) == industry] if not failed.empty else pd.DataFrame()
        )
        failed_count = int(len(failed_part))
        limit_count = int(len(zt_part))
        touch = limit_count + failed_count
        amount = float(zt_part["amount"].sum()) if not zt_part.empty else 0.0
        failed_amount = float(failed_part["amount"].sum()) if not failed_part.empty else 0.0
        top = (
            zt_part.sort_values(["board_count", "amount"], ascending=[False, False])
            .head(5)
            .to_dict("records")
            if not zt_part.empty
            else []
        )
        stats[industry] = {
            "theme_name": industry,
            "limit_up_count": limit_count,
            "failed_limit_count": failed_count,
            "failed_limit_rate": round(failed_count / touch * 100, 2) if touch else 0,
            "turnover_amount": round(amount + failed_amount, 2),
            "limit_up_amount": round(amount, 2),
            "highest_board": int(zt_part["board_count"].max()) if not zt_part.empty else 0,
            "multi_board_count": int((zt_part["board_count"] >= 2).sum()) if not zt_part.empty else 0,
            "top_stocks": [
                {
                    "code": str(row.get("code", "")),
                    "name": str(row.get("name", "")),
                    "board_count": int(clean_number(row.get("board_count"), 0)),
                    "amount": float(clean_number(row.get("amount"), 0)),
                    "open_times": int(clean_number(row.get("open_times"), 0)),
                }
                for row in top
            ],
        }
    return stats


def score_theme(item: dict, persistence_days: int) -> float:
    amount_score = 0
    if item["turnover_amount"] > 0:
        amount_score = min(18, math.log10(item["turnover_amount"] + 1) * 2)
    score = (
        item["limit_up_count"] * 6
        + item["multi_board_count"] * 7
        + item["highest_board"] * 4
        + amount_score
        + min(12, persistence_days * 3)
        - item["failed_limit_rate"] * 0.25
    )
    return round(max(0, min(100, score)), 2)


def cycle_phase(item: dict, persistence_days: int, previous_limit_count: int | None) -> str:
    if item["failed_limit_rate"] >= 35 and item["highest_board"] >= 3:
        return "高位分歧"
    if previous_limit_count is not None and previous_limit_count > 0:
        if item["limit_up_count"] <= max(1, previous_limit_count // 2):
            return "退潮"
    if persistence_days >= 2 and item["limit_up_count"] >= 3 and item["failed_limit_rate"] < 30:
        return "主升"
    if persistence_days >= 2 and item["limit_up_count"] < 3:
        return "轮动修复"
    return "启动"


def add_theme_ranks(items: list[dict]) -> list[dict]:
    def rank_by(key: str, reverse: bool = True) -> dict[str, int]:
        ordered = sorted(items, key=lambda item: item[key], reverse=reverse)
        return {item["theme_name"]: idx + 1 for idx, item in enumerate(ordered)}

    price_rank = rank_by("price_proxy_score")
    emotion_rank = rank_by("emotion_proxy_score")
    liquidity_rank = rank_by("turnover_amount")
    overall_rank = rank_by("theme_score")

    for item in items:
        name = item["theme_name"]
        item["rank"] = overall_rank[name]
        item["price_strength_rank"] = price_rank[name]
        item["emotion_strength_rank"] = emotion_rank[name]
        item["liquidity_strength_rank"] = liquidity_rank[name]
        item.pop("price_proxy_score", None)
        item.pop("emotion_proxy_score", None)
    return sorted(items, key=lambda item: item["rank"])


def build_theme_rankings(daily_frames: dict[str, dict]) -> dict[str, list[dict]]:
    raw_stats = {
        date_value: theme_stats(frames["limit_up"], frames["failed_limit"])
        for date_value, frames in daily_frames.items()
    }
    date_values = sorted(raw_stats)
    previous_presence: dict[str, list[str]] = defaultdict(list)
    result: dict[str, list[dict]] = {}

    for idx, date_value in enumerate(date_values):
        current = raw_stats[date_value]
        items: list[dict] = []
        previous_stats = raw_stats[date_values[idx - 1]] if idx > 0 else {}
        for theme_name, item in current.items():
            previous_days = previous_presence.get(theme_name, [])
            persistence_days = 1
            for prev_date in reversed(date_values[:idx]):
                if prev_date in previous_days:
                    persistence_days += 1
                else:
                    break
            previous_limit_count = (
                previous_stats.get(theme_name, {}).get("limit_up_count") if previous_stats else None
            )
            enriched = dict(item)
            enriched["persistence_days"] = persistence_days
            enriched["theme_score"] = score_theme(enriched, persistence_days)
            enriched["price_proxy_score"] = (
                enriched["limit_up_count"] * 5
                + enriched["highest_board"] * 6
                + enriched["multi_board_count"] * 4
            )
            enriched["emotion_proxy_score"] = (
                enriched["limit_up_count"] * 6
                + enriched["multi_board_count"] * 7
                - enriched["failed_limit_rate"] * 0.3
            )
            enriched["cycle_phase"] = cycle_phase(enriched, persistence_days, previous_limit_count)
            enriched["catalyst_status"] = "unknown"
            items.append(enriched)

        ranked = add_theme_ranks(items)
        result[date_value] = ranked
        for theme in ranked[:10]:
            if theme["limit_up_count"] >= 2 or theme["rank"] <= 8:
                previous_presence[theme["theme_name"]].append(date_value)
    return result


def amount_threshold(df: pd.DataFrame, quantile: float) -> float:
    if df.empty or "amount" not in df.columns:
        return 0
    values = pd.to_numeric(df["amount"], errors="coerce").dropna()
    if values.empty:
        return 0
    return float(values.quantile(quantile))


def stock_risk_flags(row: dict, market_state: str, role_hint: str = "") -> list[str]:
    flags = []
    open_times = int(clean_number(row.get("open_times"), 0))
    amount = float(clean_number(row.get("amount"), 0))
    board_count = int(clean_number(row.get("board_count"), row.get("prev_board_count", 0)))

    if open_times >= 15:
        flags.append("严重开板")
    elif open_times >= 10:
        flags.append("开板次数偏多")
    if amount and amount < 50_000_000:
        flags.append("成交额偏低")
    if board_count >= 3 and market_state == "高潮过热":
        flags.append("高位拥挤")
    if role_hint == "中位股" and market_state in {"分歧", "退潮", "高潮过热"}:
        flags.append("中位股淘汰风险")
    return flags


def role_score(row: dict, theme_rank: int | None, theme_count: int, role: str, risk_flags: list[str]) -> int:
    score = 50
    board_count = int(clean_number(row.get("board_count"), 0))
    amount = float(clean_number(row.get("amount"), 0))
    open_times = int(clean_number(row.get("open_times"), 0))

    score += min(25, board_count * 5)
    if theme_rank is not None:
        score += max(0, 12 - theme_rank)
    if theme_count >= 3:
        score += 8
    if amount >= 1_000_000_000:
        score += 8
    elif amount >= 300_000_000:
        score += 4
    score -= min(20, open_times)
    score -= len(risk_flags) * 6
    if role == "风险票":
        score = min(score, 45)
    return max(0, min(100, int(score)))


def classify_limit_up_stock(
    row: dict,
    market_state: str,
    theme_rank_map: dict[str, int],
    theme_count_map: dict[str, int],
    global_highest_board: int,
    capacity_amount: float,
) -> dict:
    industry = str(row.get("industry", ""))
    board_count = int(clean_number(row.get("board_count"), 0))
    amount = float(clean_number(row.get("amount"), 0))
    open_times = int(clean_number(row.get("open_times"), 0))
    theme_rank = theme_rank_map.get(industry)
    theme_count = theme_count_map.get(industry, 0)

    role = "孤立票"
    if open_times >= 15:
        role = "风险票"
    elif theme_count <= 1:
        role = "孤立票"
    elif board_count == global_highest_board and board_count >= 3:
        role = "龙头"
    elif amount >= capacity_amount and theme_rank is not None and theme_rank <= 8:
        role = "容量中军"
    elif 2 <= board_count < global_highest_board:
        role = "中位股"
    elif board_count <= 2 and theme_rank is not None and theme_rank <= 8:
        role = "低位补涨"

    flags = stock_risk_flags(row, market_state, role)
    evidence = [
        f"连板 {board_count}，所属题材 {industry or '未知'}",
        f"题材排名 {theme_rank if theme_rank is not None else '无'}，题材涨停 {theme_count} 只",
        f"成交额 {amount / 100000000:.2f} 亿，开板 {open_times} 次",
    ]
    return {
        "code": str(row.get("code", "")),
        "name": str(row.get("name", "")),
        "theme_name": industry,
        "role": role,
        "role_score": role_score(row, theme_rank, theme_count, role, flags),
        "risk_flags": flags,
        "evidence": evidence,
    }


def classify_failed_stock(row: dict, market_state: str) -> dict:
    flags = stock_risk_flags(row, market_state)
    flags.append("炸板")
    return {
        "code": str(row.get("code", "")),
        "name": str(row.get("name", "")),
        "theme_name": str(row.get("industry", "")),
        "role": "风险票",
        "role_score": 25,
        "risk_flags": flags,
        "evidence": [
            "当日触及涨停但未封住",
            f"成交额 {float(clean_number(row.get('amount'), 0)) / 100000000:.2f} 亿，开板 {int(clean_number(row.get('open_times'), 0))} 次",
        ],
    }


def build_stock_roles(
    zt: pd.DataFrame,
    failed: pd.DataFrame,
    market_state: str,
    theme_ranking: list[dict],
) -> list[dict]:
    if zt.empty and failed.empty:
        return []
    theme_rank_map = {item["theme_name"]: item["rank"] for item in theme_ranking}
    theme_count_map = {item["theme_name"]: item["limit_up_count"] for item in theme_ranking}
    global_highest = int(zt["board_count"].max()) if not zt.empty else 0
    capacity_amount = max(300_000_000, amount_threshold(zt, 0.75))

    roles = []
    if not zt.empty:
        for row in zt.sort_values(["board_count", "amount"], ascending=[False, False]).to_dict(
            "records"
        ):
            roles.append(
                classify_limit_up_stock(
                    row,
                    market_state,
                    theme_rank_map,
                    theme_count_map,
                    global_highest,
                    capacity_amount,
                )
            )
    if not failed.empty:
        for row in failed.sort_values("amount", ascending=False).head(30).to_dict("records"):
            roles.append(classify_failed_stock(row, market_state))
    return roles


def build_discipline_gate(market_dashboard: dict, stock_roles: list[dict]) -> dict:
    state = market_dashboard["sentiment_state"]
    reasons = []
    required = []

    if state in {"退潮", "冰点"}:
        status = "block"
        max_position = "0-2成"
        reasons.append(f"市场状态为{state}，优先保护账户")
        required.append("等待跌停减少、昨日涨停反馈修复、最高标止跌")
    elif state == "高潮过热":
        status = "reduce"
        max_position = "3-5成"
        reasons.append("市场状态为高潮过热，不适合继续扩大风险敞口")
        required.append("观察最高标断板反馈、炸板率是否抬升、昨日涨停反馈是否转负")
    elif state == "分歧":
        status = "reduce"
        max_position = "0-3成"
        reasons.append("市场处于分歧，只允许轻仓试错或等待确认")
        required.append("等待涨停扩散、跌停收敛、昨日涨停反馈转强")
    else:
        status = "allow"
        max_position = market_dashboard["position_band"]
        reasons.append(f"市场状态为{state}，允许在计划内寻找结构性机会")
        required.append("只处理事前计划内、题材支持明确、流动性合格的标的")

    risky_middle = [
        item for item in stock_roles if item["role"] == "中位股" and item.get("risk_flags")
    ]
    isolated = [item for item in stock_roles if item["role"] == "孤立票"]
    if risky_middle and status == "allow":
        status = "reduce"
        max_position = "3-5成"
        reasons.append("中位股风险标签增加，降低可用仓位")
    if isolated:
        required.append("孤立票必须有独立催化证据，否则不纳入核心模式")

    return {
        "discipline_status": status,
        "max_position_band": max_position,
        "reason": reasons,
        "required_observation": required,
    }


def build_day_summary(date_value: str, frames: dict, theme_ranking: list[dict]) -> dict:
    zt = frames["limit_up"]
    failed = frames["failed_limit"]
    dt = frames["limit_down"]
    prev = frames["previous_limit"]

    industries = Counter(zt["industry"].dropna().astype(str).tolist()) if not zt.empty else Counter()
    failed_rate = len(failed) / (len(zt) + len(failed)) * 100 if len(zt) + len(failed) else 0
    day = {
        "date": date_value,
        "limit_up_count": int(len(zt)),
        "failed_limit_count": int(len(failed)),
        "failed_limit_rate": round(float(failed_rate), 2),
        "limit_down_count": int(len(dt)),
        "highest_board": int(zt["board_count"].max()) if not zt.empty else 0,
        "multi_board_count": int((zt["board_count"] >= 2).sum()) if not zt.empty else 0,
        "prev_limit_count": int(len(prev)),
        "prev_limit_avg_pct": round(float(prev["pct"].mean()), 2) if not prev.empty else 0,
        "prev_limit_positive_rate": round(float((prev["pct"] > 0).mean()) * 100, 2)
        if not prev.empty
        else 0,
        "top_limit_industries": [
            {"industry": k, "count": int(v)} for k, v in industries.most_common(8)
        ],
        "top_boards": (
            zt.sort_values(["board_count", "amount"], ascending=[False, False])
            .head(10)[
                [
                    "code",
                    "name",
                    "industry",
                    "board_count",
                    "pct",
                    "amount",
                    "open_times",
                    "board_stat",
                ]
            ]
            .to_dict("records")
            if not zt.empty
            else []
        ),
    }
    dashboard = build_market_dashboard(day)
    roles = build_stock_roles(zt, failed, dashboard["sentiment_state"], theme_ranking)
    gate = build_discipline_gate(dashboard, roles)
    day["sentiment_score"] = dashboard["sentiment_score"]
    day["sentiment_state"] = dashboard["sentiment_label"]
    day["market_dashboard"] = dashboard
    day["theme_ranking"] = theme_ranking
    day["stock_role_classification"] = roles
    day["discipline_gate"] = gate
    return json_safe(day)


def write_markdown_report(result: dict, report_path: Path) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# {dashed_date(result['start_date'])} 至 {dashed_date(result['end_date'])} A股情绪复盘",
        "",
        f"生成日期：{result['generated_at']}  ",
        f"数据目录：`{result['data_dir']}`  ",
        "数据来源：AKShare 指数日线、东方财富涨停池、炸板池、跌停池、昨日涨停表现。",
        "",
        "## 市场情绪仪表盘",
        "",
        "| 日期 | 涨停 | 炸板 | 炸板率 | 跌停 | 最高板 | 连板数 | 昨日涨停均涨幅 | 红盘率 | 情绪分 | 状态 | 仓位上限 | 纪律 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- | --- |",
    ]
    for day in result["daily"]:
        dashboard = day["market_dashboard"]
        gate = day["discipline_gate"]
        lines.append(
            f"| {dashed_date(day['date'])} | {day['limit_up_count']} | {day['failed_limit_count']} | "
            f"{day['failed_limit_rate']:.2f}% | {day['limit_down_count']} | {day['highest_board']} | "
            f"{day['multi_board_count']} | {day['prev_limit_avg_pct']:+.2f}% | "
            f"{day['prev_limit_positive_rate']:.2f}% | {dashboard['sentiment_score']} | "
            f"{dashboard['sentiment_state']} | {gate['max_position_band']} | {gate['discipline_status']} |"
        )

    lines.extend(["", "## 题材强度排名", ""])
    for day in result["daily"]:
        lines.append(f"### {dashed_date(day['date'])}")
        lines.append("")
        lines.append("| 排名 | 题材 | 综合分 | 涨停 | 炸板 | 最高板 | 持续 | 阶段 | 催化 | 代表股 |")
        lines.append("| ---: | --- | ---: | ---: | ---: | ---: | ---: | --- | --- | --- |")
        for item in day["theme_ranking"][:8]:
            top_names = "、".join(stock["name"] for stock in item["top_stocks"][:3])
            lines.append(
                f"| {item['rank']} | {item['theme_name']} | {item['theme_score']:.2f} | "
                f"{item['limit_up_count']} | {item['failed_limit_count']} | {item['highest_board']} | "
                f"{item['persistence_days']} | {item['cycle_phase']} | {item['catalyst_status']} | {top_names} |"
            )
        lines.append("")

    lines.extend(["## 个股地位识别", ""])
    for day in result["daily"]:
        key_roles = [
            item
            for item in day["stock_role_classification"]
            if item["role"] in {"龙头", "容量中军", "低位补涨", "中位股", "风险票"}
        ][:12]
        lines.append(f"### {dashed_date(day['date'])}")
        lines.append("")
        lines.append("| 代码 | 名称 | 题材 | 地位 | 置信分 | 风险标签 |")
        lines.append("| --- | --- | --- | --- | ---: | --- |")
        for item in key_roles:
            flags = "、".join(item["risk_flags"]) if item["risk_flags"] else ""
            lines.append(
                f"| {item['code']} | {item['name']} | {item['theme_name']} | "
                f"{item['role']} | {item['role_score']} | {flags} |"
            )
        lines.append("")

    lines.extend(["## 交易纪律熔断器", ""])
    for day in result["daily"]:
        gate = day["discipline_gate"]
        lines.append(
            f"- {dashed_date(day['date'])}：`{gate['discipline_status']}`，最高仓位 `{gate['max_position_band']}`；"
            f"{'；'.join(gate['reason'])}"
        )

    if result["data_gaps"]:
        lines.extend(["", "## 数据缺口", ""])
        for gap in result["data_gaps"]:
            lines.append(f"- {gap}")

    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def chinese_font_name() -> str:
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    candidates = [
        Path("C:/Windows/Fonts/STSONG.TTF"),
        Path("C:/Windows/Fonts/simsun.ttc"),
        Path("C:/Windows/Fonts/msyh.ttc"),
    ]
    for font_path in candidates:
        if font_path.exists():
            font_name = "A股报告中文字体"
            pdfmetrics.registerFont(TTFont(font_name, str(font_path)))
            return font_name
    return "Helvetica"


def build_pdf_table(
    rows: list[list],
    widths: list[int],
    header_color,
    font_name: str,
    body_style=None,
    header_style=None,
    extra_styles: list[tuple] | None = None,
):
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Table, TableStyle

    if body_style is None:
        body_style = ParagraphStyle(
            "DefaultTableBody",
            fontName=font_name,
            fontSize=8,
            leading=11,
            textColor=colors.HexColor("#1F2937"),
        )
    if header_style is None:
        header_style = ParagraphStyle(
            "DefaultTableHeader",
            parent=body_style,
            fontName=font_name,
            textColor=colors.white,
        )

    def cell(value, style):
        from reportlab.platypus import Paragraph

        return Paragraph(str(value), style)

    wrapped_rows = []
    for row_index, row in enumerate(rows):
        style = header_style if row_index == 0 else body_style
        wrapped_rows.append([cell(value, style) for value in row])

    table = Table(wrapped_rows, colWidths=widths, repeatRows=1, hAlign="LEFT")
    commands = [
        ("BACKGROUND", (0, 0), (-1, 0), header_color),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#E5E7EB")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
    ]
    if extra_styles:
        commands.extend(extra_styles)
    table.setStyle(TableStyle(commands))
    return table


def write_pdf_report(result: dict, pdf_path: Path) -> None:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        PageBreak,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    font_name = chinese_font_name()
    styles = getSampleStyleSheet()
    page_width, page_height = landscape(A4)
    content_width = page_width - 22 * mm

    title = ParagraphStyle(
        "ChineseTitle",
        parent=styles["Title"],
        fontName=font_name,
        fontSize=22,
        leading=30,
        textColor=colors.HexColor("#111827"),
        alignment=0,
        spaceAfter=8,
    )
    heading = ParagraphStyle(
        "ChineseHeading",
        parent=styles["Heading2"],
        fontName=font_name,
        fontSize=15,
        leading=20,
        textColor=colors.HexColor("#111827"),
        spaceBefore=4,
        spaceAfter=8,
    )
    body = ParagraphStyle(
        "ChineseBody",
        parent=styles["BodyText"],
        fontName=font_name,
        fontSize=9.5,
        leading=14,
        textColor=colors.HexColor("#374151"),
        spaceAfter=5,
    )
    small = ParagraphStyle(
        "ChineseSmall",
        parent=body,
        fontSize=8.2,
        leading=12,
        textColor=colors.HexColor("#4B5563"),
    )
    label = ParagraphStyle(
        "ChineseLabel",
        parent=small,
        fontSize=7.5,
        leading=10,
        textColor=colors.HexColor("#667085"),
    )
    value = ParagraphStyle(
        "ChineseValue",
        parent=body,
        fontSize=16,
        leading=21,
        textColor=colors.HexColor("#111827"),
    )
    table_body = ParagraphStyle(
        "ChineseTableBody",
        parent=small,
        fontSize=7.7,
        leading=10.5,
        textColor=colors.HexColor("#1F2937"),
    )
    table_header = ParagraphStyle(
        "ChineseTableHeader",
        parent=table_body,
        textColor=colors.white,
    )
    note = ParagraphStyle(
        "ChineseNote",
        parent=small,
        fontSize=8.5,
        leading=13,
        textColor=colors.HexColor("#475467"),
    )

    def P(text, style=body):
        return Paragraph(str(text), style)

    def status_label(status: str) -> str:
        return {"allow": "允许", "reduce": "降级", "block": "拦截"}.get(status, status)

    def state_color(state: str):
        if state == "主升":
            return colors.HexColor("#16A34A")
        if state in {"分歧", "退潮", "冰点"}:
            return colors.HexColor("#DC2626")
        if state == "高潮过热":
            return colors.HexColor("#EA580C")
        return colors.HexColor("#2563EB")

    def state_bg(state: str):
        if state == "主升":
            return colors.HexColor("#ECFDF3")
        if state in {"分歧", "退潮", "冰点"}:
            return colors.HexColor("#FEF2F2")
        if state == "高潮过热":
            return colors.HexColor("#FFF7ED")
        return colors.HexColor("#EFF6FF")

    def card(title_text: str, value_text: str, note_text: str, accent):
        rows = [
            [P(title_text, label)],
            [P(value_text, value)],
            [P(note_text, note)],
        ]
        table = Table(rows, colWidths=[content_width / 4 - 3 * mm], hAlign="LEFT")
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
                    ("BOX", (0, 0), (-1, -1), 0.7, colors.HexColor("#E5E7EB")),
                    ("LINEBEFORE", (0, 0), (0, -1), 3, accent),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        return table

    def day_metric(day: dict, key: str):
        return day.get(key, "")

    def draw_page(canvas, doc):
        canvas.saveState()
        canvas.setFont(font_name, 8)
        canvas.setFillColor(colors.HexColor("#667085"))
        canvas.drawString(11 * mm, page_height - 7 * mm, "A股情绪复盘")
        canvas.drawRightString(page_width - 11 * mm, 7 * mm, f"第 {doc.page} 页")
        canvas.setStrokeColor(colors.HexColor("#E5E7EB"))
        canvas.setLineWidth(0.4)
        canvas.line(11 * mm, page_height - 9 * mm, page_width - 11 * mm, page_height - 9 * mm)
        canvas.line(11 * mm, 10 * mm, page_width - 11 * mm, 10 * mm)
        canvas.restoreState()

    latest = result["daily"][-1] if result["daily"] else {}
    latest_dashboard = latest.get("market_dashboard", {})
    latest_gate = latest.get("discipline_gate", {})
    latest_themes = latest.get("theme_ranking", [])
    top_theme = latest_themes[0]["theme_name"] if latest_themes else "无"
    top_risk = "；".join(latest_gate.get("reason", [])[:1]) or "暂无显著风险"
    path_text = " -> ".join(
        day["market_dashboard"]["sentiment_state"] for day in result["daily"]
    )

    story = [
        P(f"{dashed_date(result['start_date'])} 至 {dashed_date(result['end_date'])} A股情绪复盘", title),
        P(f"生成日期：{result['generated_at']}　数据来源：AKShare / 东方财富短线情绪数据", small),
        Spacer(1, 4 * mm),
        Table(
            [
                [
                    card("当前情绪", latest_dashboard.get("sentiment_state", "无"), path_text, state_color(latest_dashboard.get("sentiment_state", ""))),
                    card("纪律后仓位", latest_gate.get("max_position_band", "无"), status_label(latest_gate.get("discipline_status", "")), colors.HexColor("#0F766E")),
                    card("最强题材", top_theme, "按涨停、成交、持续性综合排序", colors.HexColor("#2563EB")),
                    card("主要风险", status_label(latest_gate.get("discipline_status", "无")), top_risk, colors.HexColor("#EA580C")),
                ]
            ],
            colWidths=[content_width / 4] * 4,
        ),
        Spacer(1, 8 * mm),
        P("情绪路径", heading),
    ]

    path_rows = [["日期", "状态", "情绪分", "涨停", "跌停", "最高板", "纪律"]]
    path_styles = []
    for idx, day in enumerate(result["daily"], start=1):
        dashboard = day["market_dashboard"]
        gate = day["discipline_gate"]
        path_rows.append(
            [
                dashed_date(day["date"]),
                dashboard["sentiment_state"],
                dashboard["sentiment_score"],
                day["limit_up_count"],
                day["limit_down_count"],
                day["highest_board"],
                status_label(gate["discipline_status"]),
            ]
        )
        path_styles.append(("BACKGROUND", (1, idx), (1, idx), state_bg(dashboard["sentiment_state"])))
        path_styles.append(("TEXTCOLOR", (1, idx), (1, idx), state_color(dashboard["sentiment_state"])))
    story.append(
        build_pdf_table(
            path_rows,
            [28 * mm, 28 * mm, 18 * mm, 18 * mm, 18 * mm, 20 * mm, 22 * mm],
            colors.HexColor("#1F2937"),
            font_name,
            table_body,
            table_header,
            path_styles,
        )
    )
    story.extend(
        [
            Spacer(1, 6 * mm),
            P("使用边界", heading),
            P("本报告只做市场环境、题材阶段、个股地位和纪律风险判断，不执行交易，不连接券商账户，也不构成买卖建议。", body),
            PageBreak(),
            P("市场情绪仪表盘", heading),
        ]
    )

    dashboard_rows = [
        ["日期", "涨停", "炸板率", "跌停", "最高板", "昨涨停均涨", "红盘率", "情绪分", "状态", "纪律"]
    ]
    dashboard_styles = []
    for day in result["daily"]:
        dashboard = day["market_dashboard"]
        gate = day["discipline_gate"]
        row_idx = len(dashboard_rows)
        dashboard_rows.append(
            [
                dashed_date(day["date"]),
                day["limit_up_count"],
                f"{day['failed_limit_rate']:.2f}%",
                day["limit_down_count"],
                day["highest_board"],
                f"{day['prev_limit_avg_pct']:+.2f}%",
                f"{day['prev_limit_positive_rate']:.2f}%",
                dashboard["sentiment_score"],
                dashboard["sentiment_state"],
                status_label(gate["discipline_status"]),
            ]
        )
        dashboard_styles.append(("BACKGROUND", (8, row_idx), (8, row_idx), state_bg(dashboard["sentiment_state"])))
        dashboard_styles.append(("TEXTCOLOR", (8, row_idx), (8, row_idx), state_color(dashboard["sentiment_state"])))
    story.append(
        build_pdf_table(
            dashboard_rows,
            [25 * mm, 17 * mm, 22 * mm, 17 * mm, 20 * mm, 26 * mm, 22 * mm, 18 * mm, 24 * mm, 22 * mm],
            colors.HexColor("#243B53"),
            font_name,
            table_body,
            table_header,
            dashboard_styles,
        )
    )

    story.extend([Spacer(1, 6 * mm), P("关键证据", heading)])
    for day in result["daily"]:
        evidence = "；".join(day["market_dashboard"].get("evidence", []))
        warnings = "；".join(day["market_dashboard"].get("warnings", [])) or "无"
        story.append(P(f"{dashed_date(day['date'])}：{evidence}。风险提示：{warnings}", note))

    story.extend([PageBreak(), P("题材强度排名", heading)])
    for day in result["daily"]:
        story.append(P(dashed_date(day["date"]), body))
        theme_rows = [["排名", "题材", "综合分", "涨停", "最高板", "持续", "阶段", "代表股"]]
        for item in day["theme_ranking"][:5]:
            top_names = "、".join(stock["name"] for stock in item["top_stocks"][:3])
            theme_rows.append(
                [
                    item["rank"],
                    item["theme_name"],
                    f"{item['theme_score']:.2f}",
                    item["limit_up_count"],
                    item["highest_board"],
                    item["persistence_days"],
                    item["cycle_phase"],
                    top_names,
                ]
            )
        story.append(
            build_pdf_table(
                theme_rows,
                [13 * mm, 30 * mm, 18 * mm, 14 * mm, 16 * mm, 14 * mm, 24 * mm, 84 * mm],
                colors.HexColor("#2563EB"),
                font_name,
                table_body,
                table_header,
            )
        )
        story.append(Spacer(1, 2.5 * mm))

    story.extend([PageBreak(), P("个股地位识别", heading)])
    for day in result["daily"]:
        story.append(P(dashed_date(day["date"]), body))
        role_rows = [["代码", "名称", "题材", "地位", "置信分", "风险标签"]]
        key_roles = [
            item
            for item in day["stock_role_classification"]
            if item["role"] in {"龙头", "容量中军", "低位补涨", "中位股", "风险票"}
        ][:8]
        role_styles = []
        for item in key_roles:
            row_idx = len(role_rows)
            flags = "、".join(item["risk_flags"]) if item["risk_flags"] else ""
            role_rows.append(
                [
                    item["code"],
                    item["name"],
                    item["theme_name"],
                    item["role"],
                    item["role_score"],
                    flags,
                ]
            )
            if item["role"] == "风险票":
                role_styles.append(("BACKGROUND", (3, row_idx), (3, row_idx), colors.HexColor("#FEF2F2")))
                role_styles.append(("TEXTCOLOR", (3, row_idx), (3, row_idx), colors.HexColor("#DC2626")))
            elif item["role"] == "龙头":
                role_styles.append(("BACKGROUND", (3, row_idx), (3, row_idx), colors.HexColor("#ECFDF3")))
                role_styles.append(("TEXTCOLOR", (3, row_idx), (3, row_idx), colors.HexColor("#16A34A")))
        story.append(
            build_pdf_table(
                role_rows,
                [22 * mm, 26 * mm, 30 * mm, 25 * mm, 18 * mm, 92 * mm],
                colors.HexColor("#047857"),
                font_name,
                table_body,
                table_header,
                role_styles,
            )
        )
        story.append(Spacer(1, 2.5 * mm))

    story.extend([PageBreak(), P("交易纪律熔断器", heading)])
    discipline_rows = [["日期", "纪律", "最高仓位", "触发原因", "继续观察"]]
    for day in result["daily"]:
        gate = day["discipline_gate"]
        discipline_rows.append(
            [
                dashed_date(day["date"]),
                status_label(gate["discipline_status"]),
                gate["max_position_band"],
                "；".join(gate["reason"]),
                "；".join(gate["required_observation"][:2]),
            ]
        )
    story.append(
        build_pdf_table(
            discipline_rows,
            [24 * mm, 18 * mm, 22 * mm, 86 * mm, 86 * mm],
            colors.HexColor("#7C2D12"),
            font_name,
            table_body,
            table_header,
        )
    )

    if result["data_gaps"]:
        story.extend([Spacer(1, 5 * mm), P("数据缺口", heading)])
        for gap in result["data_gaps"]:
            story.append(P(f"- {gap}", small))

    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=landscape(A4),
        rightMargin=11 * mm,
        leftMargin=11 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
    )
    doc.build(story, onFirstPage=draw_page, onLaterPages=draw_page)


def run_engine(
    start: str,
    end: str,
    data_root: Path = Path("data/sentiment_reviews"),
    report_dir: Path | None = Path("reports/market_reviews"),
    pdf_dir: Path | None = Path("reports/market_reviews"),
    generate_pdf: bool = False,
    refresh: bool = False,
    generated_at: str | None = None,
) -> tuple[dict, Path, Path | None, Path | None]:
    start = normalize_date(start)
    end = normalize_date(end)
    output_dir = data_root / range_label(start, end)
    output_dir.mkdir(parents=True, exist_ok=True)

    dates, gaps = trading_dates(start, end, output_dir)
    indexes, index_gaps = index_daily(dates)
    gaps.extend(index_gaps)

    daily_frames: dict[str, dict] = {}
    for date_value in dates:
        frames = {}
        for pool_name in POOL_FILES:
            df, error = load_or_fetch_pool(date_value, pool_name, output_dir, refresh)
            frames[pool_name] = df
            if error:
                gaps.append(error)
        daily_frames[date_value] = frames

    theme_rankings = build_theme_rankings(daily_frames)
    daily = [
        build_day_summary(date_value, daily_frames[date_value], theme_rankings.get(date_value, []))
        for date_value in dates
    ]

    result = {
        "start_date": start,
        "end_date": end,
        "dates": dates,
        "generated_at": generated_at or current_date.today().isoformat(),
        "data_dir": str(output_dir),
        "data_sources": [
            "AKShare stock_zh_index_daily",
            "AKShare stock_zt_pool_em",
            "AKShare stock_zt_pool_zbgc_em",
            "AKShare stock_zt_pool_dtgc_em",
            "AKShare stock_zt_pool_previous_em",
        ],
        "indexes": indexes,
        "daily": daily,
        "data_gaps": sorted(set(gaps)),
    }
    json_path = output_dir / f"sentiment_{start}_{end}.json"
    json_path.write_text(json.dumps(json_safe(result), ensure_ascii=False, indent=2), encoding="utf-8")

    report_path = None
    if report_dir is not None:
        report_path = report_dir / (
            f"{result['generated_at']}-sentiment-review-{dashed_date(start)}-to-{dashed_date(end)}.md"
        )
        write_markdown_report(result, report_path)

    pdf_path = None
    if generate_pdf and pdf_dir is not None:
        pdf_path = pdf_dir / (
            f"{result['generated_at']}-sentiment-review-{dashed_date(start)}-to-{dashed_date(end)}.pdf"
        )
        write_pdf_report(result, pdf_path)

    return result, json_path, report_path, pdf_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="A股情绪温度计、题材周期和个股地位识别引擎")
    parser.add_argument("--start", required=True, help="起始日期，格式 YYYYMMDD 或 YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="结束日期，格式 YYYYMMDD 或 YYYY-MM-DD")
    parser.add_argument("--data-root", default="data/sentiment_reviews", help="数据输出根目录")
    parser.add_argument("--report-dir", default="reports/market_reviews", help="报告输出目录")
    parser.add_argument("--pdf-dir", default="reports/market_reviews", help="PDF 输出目录")
    parser.add_argument("--pdf", action="store_true", help="生成 PDF 报告")
    parser.add_argument("--no-report", action="store_true", help="只输出 JSON 和 CSV，不生成 Markdown 报告")
    parser.add_argument("--refresh", action="store_true", help="忽略本地缓存，重新拉取数据")
    parser.add_argument("--generated-at", default=None, help="报告生成日期，默认使用当前日期")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report_dir = None if args.no_report else Path(args.report_dir)
    result, json_path, report_path, pdf_path = run_engine(
        args.start,
        args.end,
        data_root=Path(args.data_root),
        report_dir=report_dir,
        pdf_dir=Path(args.pdf_dir),
        generate_pdf=args.pdf,
        refresh=args.refresh,
        generated_at=args.generated_at,
    )
    print(json.dumps(json_safe(result), ensure_ascii=False, indent=2))
    print(f"JSON saved to {json_path}")
    if report_path:
        print(f"Report saved to {report_path}")
    if pdf_path:
        print(f"PDF saved to {pdf_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
