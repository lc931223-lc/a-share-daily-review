import json
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


PROJECT_ROOT = Path(__file__).resolve().parents[2]
FONT_DIR = PROJECT_ROOT / "assets" / "fonts"


class FormalReportBlocked(RuntimeError):
    pass


def generate_pdf(snapshot: Any, output_path: str | Path) -> Path:
    if _status(snapshot) != "PASSED":
        raise FormalReportBlocked("只允许从 PASSED 正式快照生成 PDF")

    _register_fonts()
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    story = _build_story(snapshot)
    doc = SimpleDocTemplate(
        str(output),
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
    )
    doc.build(story)
    return output.resolve()


def _register_fonts() -> None:
    fonts = {
        "SourceHanSans": "SourceHanSansCN-Regular.ttf",
        "SourceHanSans-Medium": "SourceHanSansCN-Medium.ttf",
        "SourceHanSans-Bold": "SourceHanSansCN-Bold.ttf",
    }
    for name, filename in fonts.items():
        if name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(name, str(FONT_DIR / filename)))


def _build_story(snapshot: Any) -> list[Any]:
    styles = _styles()
    data = _snapshot_data(snapshot)
    trade_date = getattr(snapshot, "trade_date", data.get("date", ""))
    confidence = getattr(snapshot, "confidence", data.get("confidence", ""))
    story: list[Any] = [
        Paragraph(f"A股每日复盘 {trade_date}", styles["ReviewTitle"]),
        Paragraph(f"真实数据快照　完整度：{confidence}%", styles["ReviewBody"]),
        Paragraph(data.get("market_regime", ""), styles["ReviewLead"]),
        Spacer(1, 6 * mm),
    ]
    for paragraph in data.get("market_commentary", []):
        story.append(Paragraph(paragraph, styles["ReviewBody"]))
    if data.get("market_commentary"):
        story.append(Spacer(1, 5 * mm))

    rich_sections = [
        ("指数与量能", _index_rows(data), [34 * mm, 34 * mm, 34 * mm, 42 * mm]),
        ("情绪温度", _sentiment_rows(data), [40 * mm, 120 * mm]),
        ("强势方向", _sector_rows(data, "sector_strength"), [16 * mm, 34 * mm, 32 * mm, 78 * mm]),
        ("弱势方向", _sector_rows(data, "sector_weakness"), [16 * mm, 34 * mm, 32 * mm, 78 * mm]),
        ("涨停梯队与亏钱反馈", _ladder_rows(data), [26 * mm, 64 * mm, 70 * mm]),
        ("龙虎榜摘要", _dragon_tiger_rows(data), [40 * mm, 120 * mm]),
        ("次日推演", _tomorrow_plan_rows(data), [28 * mm, 62 * mm, 70 * mm]),
        ("主线评分拆解", _theme_score_rows(data), [22 * mm, 24 * mm, 20 * mm, 20 * mm, 20 * mm, 20 * mm, 18 * mm, 18 * mm]),
        ("核心个股评分", _stock_score_rows(data), [24 * mm, 20 * mm, 28 * mm, 20 * mm, 20 * mm, 20 * mm, 30 * mm]),
        ("东方财富情绪引擎校验", _engine_metric_rows(data), [40 * mm, 120 * mm]),
        ("东方财富题材强度排名", _engine_theme_rows(data), [14 * mm, 34 * mm, 18 * mm, 18 * mm, 18 * mm, 18 * mm, 40 * mm]),
        ("东方财富个股地位识别", _engine_role_rows(data), [24 * mm, 22 * mm, 28 * mm, 24 * mm, 18 * mm, 44 * mm]),
    ]
    for title, rows, widths in rich_sections:
        if rows:
            story.append(Paragraph(title, styles["ReviewHeading"]))
            story.append(_table(rows, styles, widths))
            story.append(Spacer(1, 5 * mm))

    sections = [
        ("市场结论与仓位纪律", _market_rows(data)),
        ("核心指标和情绪阶段", _metric_rows(data)),
        ("题材强度与周期", _theme_rows(data)),
        ("个股地位及风险分类", _stock_rows(data)),
        ("次日观察条件", _check_rows(data)),
        ("数据质量", _quality_rows(snapshot, data)),
    ]
    for title, rows in sections:
        story.append(Paragraph(title, styles["ReviewHeading"]))
        story.append(_table(rows, styles, [42 * mm, 120 * mm]))
        story.append(Spacer(1, 5 * mm))
    return story


def _styles():
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="ReviewLead",
            fontName="SourceHanSans-Medium",
            fontSize=12.5,
            leading=18,
            textColor=colors.HexColor("#25313a"),
            spaceAfter=5,
        )
    )
    styles.add(
        ParagraphStyle(
            name="ReviewTitle",
            fontName="SourceHanSans-Bold",
            fontSize=18,
            leading=24,
            textColor=colors.black,
            spaceAfter=8,
        )
    )
    styles.add(
        ParagraphStyle(
            name="ReviewHeading",
            fontName="SourceHanSans-Medium",
            fontSize=13,
            leading=18,
            textColor=colors.black,
            spaceAfter=5,
        )
    )
    styles.add(
        ParagraphStyle(
            name="ReviewBody",
            fontName="SourceHanSans",
            fontSize=12,
            leading=17,
            textColor=colors.black,
        )
    )
    return styles


def _table(rows: list[list[Any]], styles, col_widths: list[float]) -> Table:
    wrapped = [[Paragraph(str(cell), styles["ReviewBody"]) for cell in row] for row in rows]
    table = Table(wrapped, colWidths=col_widths, repeatRows=1 if len(rows) > 1 else 0)
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), "SourceHanSans"),
                ("FONTSIZE", (0, 0), (-1, -1), 9.5),
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.black),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#9aa3aa")),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8edf1")),
                ("FONTNAME", (0, 0), (-1, 0), "SourceHanSans-Medium"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table


def _snapshot_data(snapshot: Any) -> dict[str, Any]:
    raw = getattr(snapshot, "result_json", None)
    if isinstance(raw, str) and raw.strip():
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}
    return getattr(snapshot, "result", {}) or {}


def _status(snapshot: Any) -> str:
    status = getattr(snapshot, "status", "")
    return getattr(status, "value", status)


def _market_rows(data: dict[str, Any]) -> list[list[Any]]:
    return [
        ["市场状态", data.get("market_regime", "待分析")],
        ["仓位纪律", f'{data.get("position_min", 0)}-{data.get("position_max", 0)}成'],
    ]


def _metric_rows(data: dict[str, Any]) -> list[list[Any]]:
    return [
        ["指标", "读数"],
        ["成交额", data.get("turnover", "缺失")],
        ["成交额变化", data.get("turnover_delta", "缺失")],
        ["上涨/下跌", f'{data.get("advancers", "缺失")} / {data.get("decliners", "缺失")}'],
        ["涨停/跌停", f'{data.get("limit_up_count", "缺失")} / {data.get("limit_down_count", "缺失")}'],
        ["最高板", data.get("max_board_height", "缺失")],
    ]


def _index_rows(data: dict[str, Any]) -> list[list[Any]]:
    rows = data.get("indices", [])
    if not rows:
        return []
    table = [["指数", "收盘", "涨跌幅", "成交额"]]
    for item in rows:
        turnover = item.get("turnover_yi")
        table.append(
            [
                item.get("name", ""),
                item.get("close", ""),
                f'{item.get("change_pct", 0):.2f}%',
                f"{turnover:.0f}亿元" if isinstance(turnover, (int, float)) else "缺失",
            ]
        )
    return table


def _sentiment_rows(data: dict[str, Any]) -> list[list[Any]]:
    sentiment = data.get("sentiment_dashboard") or {}
    if not sentiment:
        return []
    return [
        ["项目", "结论"],
        ["情绪温度", sentiment.get("temperature", "")],
        ["市场宽度", sentiment.get("breadth", "")],
        ["流动性", sentiment.get("liquidity", "")],
        ["风险偏好", sentiment.get("risk_appetite", "")],
        ["涨停池", sentiment.get("limit_pool", "")],
        ["亏钱效应", sentiment.get("loss_feedback", "")],
    ]


def _sector_rows(data: dict[str, Any], key: str) -> list[list[Any]]:
    rows = data.get(key, [])
    if not rows:
        return []
    table = [["排名", "方向", "状态", "证据"]]
    table.extend([[item.get("rank", ""), item.get("name", ""), item.get("status", ""), item.get("evidence", "")] for item in rows])
    return table


def _ladder_rows(data: dict[str, Any]) -> list[list[Any]]:
    rows = data.get("limit_ladder", [])
    if not rows:
        return []
    table = [["高度", "代表个股", "解读"]]
    table.extend([[item.get("height", ""), item.get("stocks", ""), item.get("read", "")] for item in rows])
    return table


def _dragon_tiger_rows(data: dict[str, Any]) -> list[list[Any]]:
    item = data.get("dragon_tiger") or {}
    if not item:
        return []
    return [
        ["项目", "读数"],
        ["日期", item.get("date", "")],
        ["上榜成交额", f'{item.get("amount_yi", 0):.2f}亿元'],
        ["上榜个股", f'{item.get("stock_count", 0)}只'],
        ["机构净买入", f'{item.get("institution_net_buy_count", 0)}只'],
        ["解读", item.get("read", "")],
    ]


def _tomorrow_plan_rows(data: dict[str, Any]) -> list[list[Any]]:
    rows = data.get("tomorrow_plan", [])
    if not rows:
        return []
    table = [["观察项", "触发条件", "含义"]]
    table.extend([[item.get("item", ""), item.get("trigger", ""), item.get("meaning", "")] for item in rows])
    return table


def _theme_score_rows(data: dict[str, Any]) -> list[list[Any]]:
    rows = data.get("main_themes", [])
    if not rows:
        return []
    table = [["主线", "基础逻辑", "兑现", "预期差", "持续性", "市场确认", "风险扣分", "综合"]]
    for item in rows:
        scores = item.get("scores", {})
        table.append(
            [
                item.get("name", ""),
                scores.get("base_logic_score", ""),
                scores.get("realization_score", ""),
                scores.get("expectation_gap_score", ""),
                scores.get("persistence_score", ""),
                scores.get("market_confirmation_score", ""),
                scores.get("risk_penalty", ""),
                f'{scores.get("total_score", "")}/{scores.get("rating", "")}',
            ]
        )
    return table


def _stock_score_rows(data: dict[str, Any]) -> list[list[Any]]:
    rows = data.get("stocks", [])
    if not rows:
        return []
    table = [["个股", "主线", "地位", "综合", "行情强度", "风险收益", "催化"]]
    for item in rows:
        scores = item.get("scores", {})
        table.append(
            [
                f'{item.get("name", "")} {item.get("code", "")}',
                item.get("theme", ""),
                item.get("role", ""),
                f'{scores.get("total_score", "")}/{scores.get("rating", "")}',
                scores.get("market_strength", ""),
                scores.get("risk_reward", ""),
                item.get("catalyst", ""),
            ]
        )
    return table


def _engine_metric_rows(data: dict[str, Any]) -> list[list[Any]]:
    engine = data.get("sentiment_engine") or {}
    metric = engine.get("daily_metric") or {}
    if not metric:
        return []
    return [
        ["项目", "读数"],
        ["涨停/炸板/跌停", f'{metric.get("limit_up_count", "")}/{metric.get("failed_limit_count", "")}/{metric.get("limit_down_count", "")}'],
        ["炸板率", f'{metric.get("failed_limit_rate", "")}%'],
        ["最高板/连板数", f'{metric.get("highest_board", "")}板 / {metric.get("multi_board_count", "")}只'],
        ["昨日涨停反馈", f'均涨幅 {metric.get("prev_limit_avg_pct", "")}%，红盘率 {metric.get("prev_limit_positive_rate", "")}%'],
        ["情绪分/状态", f'{metric.get("sentiment_score", "")} / {metric.get("sentiment_state", "")}'],
        ["仓位与纪律", f'{metric.get("position_band", "")}，{metric.get("discipline", "")}'],
    ]


def _engine_theme_rows(data: dict[str, Any]) -> list[list[Any]]:
    engine = data.get("sentiment_engine") or {}
    rows = engine.get("theme_ranking", [])
    if not rows:
        return []
    table = [["排名", "题材", "综合分", "涨停", "炸板", "最高板", "代表股"]]
    for item in rows:
        table.append(
            [
                item.get("rank", ""),
                item.get("theme_name", ""),
                item.get("theme_score", ""),
                item.get("limit_up_count", ""),
                item.get("failed_limit_count", ""),
                item.get("highest_board", ""),
                item.get("top_stocks", ""),
            ]
        )
    return table


def _engine_role_rows(data: dict[str, Any]) -> list[list[Any]]:
    engine = data.get("sentiment_engine") or {}
    rows = engine.get("stock_role_classification", [])
    if not rows:
        return []
    table = [["代码", "名称", "题材", "地位", "置信分", "证据"]]
    for item in rows:
        table.append(
            [
                item.get("code", ""),
                item.get("name", ""),
                item.get("theme_name", ""),
                item.get("role", ""),
                item.get("role_score", ""),
                "；".join(item.get("evidence", [])[:2]),
            ]
        )
    return table


def _theme_rows(data: dict[str, Any]) -> list[list[Any]]:
    themes = data.get("main_themes", [])
    if not themes:
        return [["题材", "暂无正式题材结论"]]
    return [["题材", "结论"]] + [[item.get("name", ""), item.get("delta_reason", "")] for item in themes]


def _stock_rows(data: dict[str, Any]) -> list[list[Any]]:
    stocks = data.get("stocks", [])
    if not stocks:
        return [["个股", "暂无正式个股结论"]]
    return [["个股", "地位与反馈"]] + [[f'{item.get("name", "")} {item.get("code", "")}', f'{item.get("role_detail") or item.get("role", "")}；{item.get("delta_reason", "")}'] for item in stocks]


def _check_rows(data: dict[str, Any]) -> list[list[Any]]:
    checks = data.get("tomorrow_checks", [])
    if not checks:
        return [["观察条件", "暂无次日观察条件"]]
    return [["观察对象", "条件"]] + [[item.get("entity_key", ""), item.get("description", "")] for item in checks]


def _quality_rows(snapshot: Any, data: dict[str, Any]) -> list[list[Any]]:
    detail = data.get("data_quality_detail") or {}
    gaps = "；".join(detail.get("known_gaps", [])) or "无"
    resolved = "；".join(detail.get("resolved_gaps", [])) or "无"
    disagreements = "；".join(detail.get("source_disagreements", [])) or "无"
    sources = "；".join(detail.get("sources", [])) or "见证据中心"
    return [
        ["项目", "说明"],
        ["规则版本", getattr(snapshot, "rule_version", data.get("schema_version", ""))],
        ["数据版本", getattr(snapshot, "data_version", "")],
        ["来源策略", detail.get("primary_source", data.get("fallback_summary", "东方财富公开源优先"))],
        ["已补齐缺口", resolved],
        ["口径差异", disagreements],
        ["仍未纳入项", gaps],
        ["来源", sources],
    ]
