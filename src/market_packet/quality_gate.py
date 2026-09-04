from __future__ import annotations

from src.market_packet.collector import CollectedDataset


CRITICAL_DATASETS = {
    "limit_up": "涨停池",
    "failed_limit": "炸板池",
    "limit_down": "跌停池",
    "previous_limit": "昨日涨停反馈",
    "dragon_tiger_daily": "龙虎榜日明细",
}


def audit_packet(packet: dict, datasets: dict[str, CollectedDataset]) -> dict:
    checks = []
    missing = set(packet.get("missing_data", []))

    def add(item: str, status: str, source: str | None, detail: str, missing_key: str | None = None):
        checks.append({"item": item, "status": status, "source": source, "detail": detail})
        if status == "FAIL" and missing_key:
            missing.add(missing_key)

    for dataset, label in CRITICAL_DATASETS.items():
        source = datasets[dataset]
        status = "PASS" if source.rows else "FAIL"
        add(label, status, source.source, f"rows={len(source.rows)}" if source.rows else source.error or "empty", dataset)

    index_pass = sum(1 for item in packet["indices"] if item.get("quality") == "PASS")
    add("指数数据", "PASS" if index_pass >= 3 else "PARTIAL" if index_pass else "FAIL", "akshare.stock_zh_index_daily", f"{index_pass}/{len(packet['indices'])} major indices available", "indices")
    if packet["liquidity"].get("total_market_turnover") is not None:
        add("成交额", "PASS", "tushare.daily", "全市场成交额来自 Tushare daily amount 汇总", "turnover")
    else:
        add("成交额", "PASS" if packet["liquidity"].get("sh_sz_turnover") is not None else "PARTIAL", "index amount", "沪深两市成交额来自可用指数 amount；全市场成交额为 null" if packet["liquidity"].get("sh_sz_turnover") is not None else "成交额缺失", "turnover")
    if packet["liquidity"].get("total_market_turnover") is None:
        missing.add("total_market_turnover")
    if packet["liquidity"].get("previous_turnover") is None:
        missing.add("previous_turnover")
    if packet["market_breadth"].get("quality") == "PASS":
        add("上涨下跌家数", "PASS", packet["market_breadth"].get("source"), f"rise={packet['market_breadth'].get('rise_count')} fall={packet['market_breadth'].get('fall_count')} flat={packet['market_breadth'].get('flat_count')}", "market_breadth")
    else:
        add("上涨下跌家数", "FAIL", None, "AKShare 当前未提供目标历史日全市场涨跌家数稳定结构化接口，且 Tushare daily 未返回有效数据", "market_breadth")
    industry_source = datasets.get("industry_board_daily")
    industry_complete = len(packet["industries"]) >= 30 and any(item.get("change_pct") is not None for item in packet["industries"])
    add(
        "行业数据",
        "PASS" if industry_complete else "PARTIAL" if packet["industries"] else "FAIL",
        industry_source.source if industry_source else "Eastmoney limit pools via AKShare",
        f"{len(packet['industries'])} industries; historical board coverage={'yes' if industry_complete else 'no'}",
        "industries",
    )
    concept_source = datasets.get("concept_board_daily")
    concept_complete = len(packet["themes"]) >= 50 and any(item.get("change_pct") is not None for item in packet["themes"])
    add(
        "题材数据",
        "PASS" if concept_complete else "PARTIAL" if packet["themes"] else "FAIL",
        concept_source.source if concept_source else "Eastmoney limit pools via AKShare",
        f"{len(packet['themes'])} concepts/themes; historical board coverage={'yes' if concept_complete else 'no'}",
        "themes",
    )
    ohlcv_rows = len(datasets.get("stock_top_ohlcv").rows) if datasets.get("stock_top_ohlcv") else 0
    if ohlcv_rows >= min(80, len(packet["stocks"])):
        stock_status = "PASS"
        stock_detail = f"{len(packet['stocks'])} stocks covered; {ohlcv_rows} target-day OHLCV rows added"
    elif packet["stocks"]:
        stock_status = "PARTIAL"
        stock_detail = f"{len(packet['stocks'])} stocks covered; only {ohlcv_rows} target-day OHLCV rows added"
        missing.add("stock_top100_full_ohlcv")
    else:
        stock_status = "FAIL"
        stock_detail = "no core stock universe available"
    add("核心个股行情", stock_status, "Eastmoney limit pools/LHB plus akshare.stock_zh_a_hist", stock_detail, "stocks")
    ann_source = datasets.get("official_announcements")
    add("公告", "PASS" if packet["announcements"] else "FAIL", ann_source.source if ann_source else None, f"{len(packet['announcements'])} official/supplemental announcements collected" if packet["announcements"] else (ann_source.error if ann_source else "announcement collector unavailable"), "announcements")
    policy_source = datasets.get("official_policies")
    add("政策", "PASS" if packet["policies"] else "FAIL", policy_source.source if policy_source else None, f"{len(packet['policies'])} official policies collected" if packet["policies"] else (policy_source.error if policy_source else "official policy collector unavailable"), "policies")
    add("上一交易日review", "PASS" if packet["previous_review"] else "PARTIAL", "local review json/db", "previous review context found" if packet["previous_review"] else "no previous formal review found", "previous_review")

    score = _score(check["status"] for check in checks)
    packet["missing_data"] = sorted(missing)
    packet["data_quality"] = {
        "status": _label(score),
        "score": score,
        "checks": checks,
        "sources": [
            {
                "source": item.source,
                "retrieved_at": item.retrieved_at.isoformat(),
                "data_date": item.data_date.isoformat() if item.data_date else None,
                "freshness": item.freshness,
                "quality": item.quality,
                "is_cached": item.is_cached,
                "path": item.path,
                "error": item.error,
            }
            for item in datasets.values()
        ],
        "conflicts": [],
    }
    return packet


def _score(statuses) -> int:
    values = {"PASS": 1.0, "PARTIAL": 0.55, "FAIL": 0.0}
    items = list(statuses)
    if not items:
        return 0
    return round(sum(values[item] for item in items) / len(items) * 100)


def _label(score: int) -> str:
    if score >= 95:
        return "EXCELLENT"
    if score >= 85:
        return "GOOD"
    if score >= 70:
        return "PARTIAL"
    return "INCOMPLETE"
