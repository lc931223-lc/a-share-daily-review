import json
import math
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "market_reviews" / "2026-09-02"
REPORT_DIR = ROOT / "reports" / "market_reviews"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
EASTMONEY_CLIST = "https://push2.eastmoney.com/api/qt/clist/get"
EASTMONEY_INDEX = "https://push2.eastmoney.com/api/qt/ulist.np/get"
SESSION = requests.Session()
SESSION.trust_env = False


def em_get(url: str, params: dict[str, Any]) -> dict[str, Any]:
    last_error: Exception | None = None
    for _ in range(2):
        try:
            response = SESSION.get(url, params=params, headers={"User-Agent": UA}, timeout=20)
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            last_error = exc
            time.sleep(1.2)
    raise RuntimeError(f"公开行情接口请求失败：{url}") from last_error


def fetch_all_stocks() -> list[dict[str, Any]]:
    fields = "f2,f3,f4,f5,f6,f12,f13,f14,f15,f16,f17,f18,f20,f21,f62"
    rows: list[dict[str, Any]] = []
    page = 1
    while True:
        data = em_get(
            EASTMONEY_CLIST,
            {
                "pn": page,
                "pz": 500,
                "po": 1,
                "np": 1,
                "ut": "bd1d9ddb04089700cf9c27f6f7426281",
                "fltt": 2,
                "invt": 2,
                "fid": "f3",
                "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048",
                "fields": fields,
            },
        )
        diff = data.get("data", {}).get("diff") or []
        rows.extend(diff)
        if len(rows) >= int(data.get("data", {}).get("total") or 0) or not diff:
            break
        page += 1
        time.sleep(1.1)
    return rows


def fetch_board(fs: str, label: str) -> list[dict[str, Any]]:
    data = em_get(
        EASTMONEY_CLIST,
        {
            "pn": 1,
            "pz": 30,
            "po": 1,
            "np": 1,
            "ut": "bd1d9ddb04089700cf9c27f6f7426281",
            "fltt": 2,
            "invt": 2,
            "fid": "f3",
            "fs": fs,
            "fields": "f12,f14,f2,f3,f4,f5,f6,f20,f62,f128,f136,f140",
        },
    )
    rows = data.get("data", {}).get("diff") or []
    for row in rows:
        row["board_type"] = label
    return rows


def fetch_indices() -> list[dict[str, Any]]:
    data = em_get(
        EASTMONEY_INDEX,
        {
            "fltt": 2,
            "invt": 2,
            "fields": "f12,f13,f14,f2,f3,f4,f6,f104,f105,f106",
            "secids": "1.000001,0.399001,0.399006,1.000688,1.000300",
        },
    )
    return data.get("data", {}).get("diff") or []


def valid_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not math.isnan(value)


def summarize(stocks: list[dict[str, Any]]) -> dict[str, Any]:
    tradable = [row for row in stocks if valid_number(row.get("f3"))]
    advancers = sum(1 for row in tradable if row["f3"] > 0)
    decliners = sum(1 for row in tradable if row["f3"] < 0)
    flat = sum(1 for row in tradable if row["f3"] == 0)
    turnover_yi = sum(float(row.get("f6") or 0) for row in tradable) / 100_000_000
    limit_like = [row for row in tradable if row.get("f3") is not None and row["f3"] >= 9.8]
    limit_down_like = [row for row in tradable if row.get("f3") is not None and row["f3"] <= -9.8]
    return {
        "tradable_count": len(tradable),
        "advancers": advancers,
        "decliners": decliners,
        "flat": flat,
        "turnover_yi": round(turnover_yi, 2),
        "limit_like_count": len(limit_like),
        "limit_down_like_count": len(limit_down_like),
        "top_gainers": sorted(tradable, key=lambda row: row.get("f3") or -999, reverse=True)[:20],
        "top_losers": sorted(tradable, key=lambda row: row.get("f3") or 999)[:20],
    }


def build_payload() -> dict[str, Any]:
    try:
        stocks = fetch_all_stocks()
    except Exception as exc:
        return build_curated_payload(str(exc))
    payload = {
        "trade_date": "2026-09-02",
        "fetched_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "sources": [
            {
                "name": "东方财富沪深京A股行情接口",
                "url": EASTMONEY_CLIST,
                "usage": "全市场报价、涨跌分布、成交额、行业和概念排行",
            },
            {
                "name": "东方财富指数行情接口",
                "url": EASTMONEY_INDEX,
                "usage": "主要指数收盘表现",
            },
        ],
        "quality": {
            "status": "DRAFT_ONLY",
            "reason": "当前环境缺少 TUSHARE_TOKEN，未能通过 Tushare 核心主源门禁；本报告仅使用公开行情接口生成，不写入正式 PASSED 快照。",
        },
        "indices": fetch_indices(),
        "summary": summarize(stocks),
        "industries": fetch_board("m:90+t:2+f:!50", "industry"),
        "concepts": fetch_board("m:90+t:3+f:!50", "concept"),
    }
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "public_review_payload.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return payload


def build_curated_payload(error: str) -> dict[str, Any]:
    payload = {
        "trade_date": "2026-09-02",
        "fetched_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "sources": [
            {
                "name": "新浪财经/国际金融报 A股收报",
                "url": "https://finance.sina.com.cn/wm/2026-09-02/doc-iniqmmyy2921980.shtml",
                "usage": "三大指数涨跌、全市成交额、近3900只个股下跌、强弱板块交叉核验",
            },
            {
                "name": "澎湃新闻 A股收评",
                "url": "https://www.thepaper.cn/newsDetail_forward_33993073",
                "usage": "指数点位、Wind 上涨下跌家数、成交额、9%以上涨跌幅家数核验",
            },
            {
                "name": "Investing.com/智通财经 A股收评",
                "url": "https://cn.investing.com/news/stock-market-news/article-3548248",
                "usage": "指数点位、成交额、涨停跌停家数、板块强弱交叉核验",
            },
            {
                "name": "东方财富 龙虎榜详情页",
                "url": "https://data.eastmoney.com/stock/tradedetail.html",
                "usage": "确认数据中心日期已切换到 2026-09-02；本脚本未成功拉取明细表",
            },
        ],
        "quality": {
            "status": "DRAFT_ONLY",
            "reason": f"当前环境缺少 TUSHARE_TOKEN，且公开行情接口批量抓取失败：{error}。本报告使用网页核验数据生成，不写入正式 PASSED 快照。",
        },
        "indices": [
            {"f14": "上证指数", "f2": 3941.39, "f3": -0.97, "f6": 835_400_000_000, "f104": "缺失", "f105": "缺失", "f106": "缺失"},
            {"f14": "深证成指", "f2": 13611.55, "f3": -1.88, "f6": 955_800_000_000, "f104": "缺失", "f105": "缺失", "f106": "缺失"},
            {"f14": "创业板指", "f2": 3312.24, "f3": -2.39, "f6": None, "f104": "缺失", "f105": "缺失", "f106": "缺失"},
            {"f14": "科创50", "f2": 1617.60, "f3": -1.82, "f6": None, "f104": "缺失", "f105": "缺失", "f106": "缺失"},
            {"f14": "北证50", "f2": 1106.57, "f3": 2.50, "f6": None, "f104": "缺失", "f105": "缺失", "f106": "缺失"},
        ],
        "summary": {
            "tradable_count": 5547,
            "advancers": 1537,
            "decliners": 3898,
            "flat": 112,
            "turnover_yi": 17912.0,
            "turnover_note": "澎湃/Wind口径17912亿元；新浪聚合口径18202亿元；差异来自统计市场范围和数据供应商口径。",
            "limit_like_count": 71,
            "limit_down_like_count": 19,
            "top_gainers": [
                {"f14": "北方长龙", "f12": "301357", "f3": 13.90, "f6": None},
                {"f14": "长城军工", "f12": "601606", "f3": 10.00, "f6": None},
                {"f14": "内蒙一机", "f12": "600967", "f3": "2连板", "f6": None},
                {"f14": "建设工业", "f12": "002265", "f3": "涨停", "f6": None},
                {"f14": "博云新材", "f12": "002297", "f3": "涨停", "f6": None},
                {"f14": "晟楠科技", "f12": "837006", "f3": "涨停", "f6": None},
            ],
            "top_losers": [
                {"f14": "敦煌种业", "f12": "600354", "f3": "跌停", "f6": None},
                {"f14": "登海种业", "f12": "002041", "f3": "跌停", "f6": None},
                {"f14": "国投丰乐", "f12": "000713", "f3": "跌停", "f6": None},
                {"f14": "华绿生物", "f12": "300970", "f3": "下挫", "f6": None},
            ],
        },
        "industries": [
            {"f14": "地面兵装/军工装备", "f3": "逆市走强", "f6": None, "f128": "内蒙一机、建设工业、长城军工、北方长龙"},
            {"f14": "航空装备", "f3": "逆市活跃", "f6": None, "f128": "天秦装备、国科军工、通易航天"},
            {"f14": "玻璃玻纤", "f3": "活跃", "f6": None, "f128": "山东玻纤"},
            {"f14": "教育", "f3": "局部上涨", "f6": None, "f128": "网页未给出完整领涨股"},
            {"f14": "旅游及景区", "f3": "局部上涨", "f6": None, "f128": "网页未给出完整领涨股"},
            {"f14": "种植业/农业", "f3": "领跌", "f6": None, "f128": "敦煌种业、登海种业、国投丰乐"},
            {"f14": "焦炭/煤炭", "f3": "跌幅居前", "f6": None, "f128": "网页未给出完整领跌股"},
            {"f14": "能源金属/小金属", "f3": "跌幅居前", "f6": None, "f128": "网页未给出完整领跌股"},
        ],
        "concepts": [
            {"f14": "玻纤", "f3": "活跃", "f6": None, "f128": "山东玻纤"},
            {"f14": "培育钻石", "f3": "活跃", "f6": None, "f128": "网页未给出完整领涨股"},
            {"f14": "粮食概念", "f3": "领跌", "f6": None, "f128": "敦煌种业、登海种业、国投丰乐"},
            {"f14": "锂电/能源金属", "f3": "下挫", "f6": None, "f128": "网页未给出完整领跌股"},
            {"f14": "文化传媒/影视院线", "f3": "跌幅居前", "f6": None, "f128": "网页未给出完整领跌股"},
        ],
    }
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "public_review_payload.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return payload


def fmt(value: Any, suffix: str = "") -> str:
    if isinstance(value, float):
        return f"{value:.2f}{suffix}"
    if isinstance(value, int):
        return f"{value}{suffix}"
    if value is None or value == "-":
        return "缺失"
    return str(value)


def amount_yi(value: Any) -> str:
    if isinstance(value, (int, float)):
        return fmt(value / 100_000_000, "亿元")
    return "缺失"


def count_with_unit(value: Any, unit: str) -> str:
    if isinstance(value, int):
        return f"{value}{unit}"
    return str(value)


def row_name(row: dict[str, Any]) -> str:
    return f"{row.get('f14', '')}({row.get('f12', '')})"


def write_markdown(payload: dict[str, Any]) -> Path:
    summary = payload["summary"]
    indices = payload["indices"]
    industries = payload["industries"][:10]
    concepts = payload["concepts"][:10]
    top_gainers = summary["top_gainers"][:10]
    top_losers = summary["top_losers"][:10]
    advancers = summary["advancers"] if isinstance(summary["advancers"], int) else 0
    decliners = summary["decliners"] if isinstance(summary["decliners"], int) else 3900
    limit_like = summary["limit_like_count"] if isinstance(summary["limit_like_count"], int) else 0
    breadth_ratio = advancers / max(1, advancers + decliners)
    if breadth_ratio >= 0.62 and limit_like >= 80:
        sentiment = "偏热修复"
    elif breadth_ratio >= 0.55:
        sentiment = "温和修复"
    elif breadth_ratio <= 0.42:
        sentiment = "退潮偏弱"
    else:
        sentiment = "分歧震荡"
    lines = [
        "# 2026-09-02 A股市场复盘报告",
        "",
        f"- 报告状态：{payload['quality']['status']}（公开数据复盘，非 Tushare PASSED 正式快照）",
        f"- 抓取时间：{payload['fetched_at']}",
        f"- 数据质量说明：{payload['quality']['reason']}",
        "",
        "## 市场温度",
        "",
        f"- 情绪判断：{sentiment}",
        f"- 可交易样本：{count_with_unit(summary['tradable_count'], '只')}",
        f"- 上涨/平盘/下跌：{summary['advancers']} / {summary['flat']} / {summary['decliners']}",
        f"- 全市场成交额：{summary['turnover_yi']:.2f} 亿元",
        f"- 成交额口径：{summary.get('turnover_note', '单一数据源口径')}",
        f"- 近似涨停/跌停：{summary['limit_like_count']} / {summary['limit_down_like_count']}（按涨跌幅 >= 9.8% 与 <= -9.8% 粗略识别，未做 ST/北交所涨跌停精细校验）",
        "",
        "## 主要指数",
        "",
        "| 指数 | 收盘 | 涨跌幅 | 成交额 | 上涨/下跌/平盘 |",
        "|---|---:|---:|---:|---:|",
    ]
    for item in indices:
        lines.append(
            f"| {item.get('f14')} | {fmt(item.get('f2'))} | {fmt(item.get('f3'), '%')} | {amount_yi(item.get('f6'))} | {item.get('f104', '缺失')}/{item.get('f105', '缺失')}/{item.get('f106', '缺失')} |"
        )
    lines += [
        "",
        "## 行业强弱",
        "",
        "| 排名 | 行业 | 涨跌幅 | 成交额 | 领涨股 |",
        "|---:|---|---:|---:|---|",
    ]
    for idx, item in enumerate(industries, 1):
        lines.append(
            f"| {idx} | {item.get('f14')} | {fmt(item.get('f3'), '%')} | {amount_yi(item.get('f6'))} | {item.get('f128') or '缺失'} |"
        )
    lines += [
        "",
        "## 概念题材",
        "",
        "| 排名 | 概念 | 涨跌幅 | 成交额 | 领涨股 |",
        "|---:|---|---:|---:|---|",
    ]
    for idx, item in enumerate(concepts, 1):
        lines.append(
            f"| {idx} | {item.get('f14')} | {fmt(item.get('f3'), '%')} | {amount_yi(item.get('f6'))} | {item.get('f128') or '缺失'} |"
        )
    lines += [
        "",
        "## 个股观察",
        "",
        "| 涨幅前列 | 涨跌幅 | 成交额 |",
        "|---|---:|---:|",
    ]
    for item in top_gainers:
        lines.append(f"| {row_name(item)} | {fmt(item.get('f3'), '%')} | {amount_yi(item.get('f6'))} |")
    lines += [
        "",
        "| 跌幅前列 | 涨跌幅 | 成交额 |",
        "|---|---:|---:|",
    ]
    for item in top_losers:
        lines.append(f"| {row_name(item)} | {fmt(item.get('f3'), '%')} | {amount_yi(item.get('f6'))} |")
    lines += [
        "",
        "## 复盘结论",
        "",
        f"1. 市场宽度为 {summary['advancers']} 涨对 {summary['decliners']} 跌，整体为退潮偏弱格局；本报告缺少 Tushare 全量日线、正式涨跌停池、炸板率和连板梯队核验，因此不能升级为正式 PASSED 报告。",
        f"2. 成交额约 {fmt(summary['turnover_yi'], '亿元')}，较多个公开收评口径显示的上一交易日明显缩量。若后续 Tushare 核心数据补齐，需要复核全市场成交额、指数成交额和可交易样本覆盖率。",
        "3. 题材和个股表只作为当日公开行情强弱观察，不固定使用任何历史示例题材或股票名称。",
        "",
        "## 数据来源",
        "",
    ]
    for source in payload["sources"]:
        lines.append(f"- {source['name']}：{source['url']}；用途：{source['usage']}")
    path = REPORT_DIR / "2026-09-02-a-share-public-data-review.md"
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def register_fonts() -> None:
    font_dir = ROOT / "assets" / "fonts"
    for name, filename in {
        "SourceHanSans": "SourceHanSansCN-Regular.ttf",
        "SourceHanSans-Medium": "SourceHanSansCN-Medium.ttf",
        "SourceHanSans-Bold": "SourceHanSansCN-Bold.ttf",
    }.items():
        if name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(name, str(font_dir / filename)))


def write_pdf(markdown_path: Path) -> Path:
    register_fonts()
    styles = getSampleStyleSheet()
    body = ParagraphStyle("CNBody", fontName="SourceHanSans", fontSize=11, leading=16, textColor=colors.black)
    title = ParagraphStyle("CNTitle", fontName="SourceHanSans-Bold", fontSize=18, leading=24, textColor=colors.black)
    heading = ParagraphStyle("CNHeading", fontName="SourceHanSans-Medium", fontSize=13, leading=18, textColor=colors.black)
    story = []
    for line in markdown_path.read_text("utf-8").splitlines():
        if line.startswith("# "):
            story.extend([Paragraph(line[2:], title), Spacer(1, 5 * mm)])
        elif line.startswith("## "):
            story.extend([Spacer(1, 3 * mm), Paragraph(line[3:], heading)])
        elif line.startswith("|") or not line.strip():
            continue
        else:
            story.append(Paragraph(line.replace("- ", "", 1), body))
    pdf_path = markdown_path.with_suffix(".pdf")
    doc = SimpleDocTemplate(str(pdf_path), pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=16 * mm, bottomMargin=16 * mm)
    doc.build(story)
    return pdf_path


def main() -> None:
    payload = build_payload()
    markdown = write_markdown(payload)
    pdf = write_pdf(markdown)
    print(json.dumps({"markdown": str(markdown), "pdf": str(pdf), "data": str(DATA_DIR / "public_review_payload.json")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
