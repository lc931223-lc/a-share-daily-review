import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.validation.review_models import DailyReview

OUTPUT = ROOT / "data" / "json" / "reviews" / "2026-09-02-dashboard-review.json"
ENGINE_JSON = (
    ROOT
    / "data"
    / "market_reviews"
    / "2026-09-02"
    / "engine"
    / "2026-09-02_to_2026-09-02"
    / "sentiment_20260902_20260902.json"
)


def theme_scores(base: int, realization: int, gap: int, persistence: int, confirm: int, risk: int):
    total = base + realization + gap + persistence + confirm + risk
    if total >= 90:
        rating = "S+"
    elif total >= 80:
        rating = "S"
    elif total >= 70:
        rating = "A"
    elif total >= 60:
        rating = "B"
    elif total >= 45:
        rating = "C"
    else:
        rating = "D"
    return {
        "base_logic_score": base,
        "realization_score": realization,
        "expectation_gap_score": gap,
        "persistence_score": persistence,
        "market_confirmation_score": confirm,
        "risk_penalty": risk,
        "total_score": total,
        "rating": rating,
        "logic_quality": min(100, base * 2 + 5),
        "market_strength": min(100, realization * 3 + confirm * 3),
        "risk_reward": max(0, min(100, 70 + risk * 3 + gap)),
        "missing_reasons": {},
    }


def stock_scores(total: int, strength: int, risk_reward: int, logic: int = 70):
    if total >= 90:
        rating = "S+"
    elif total >= 80:
        rating = "S"
    elif total >= 70:
        rating = "A"
    elif total >= 60:
        rating = "B"
    elif total >= 45:
        rating = "C"
    else:
        rating = "D"
    return {
        "realization_score": strength,
        "expectation_gap": max(0, min(100, total - 10)),
        "logic_quality": logic,
        "market_strength": strength,
        "risk_reward": risk_reward,
        "total_score": total,
        "rating": rating,
        "missing_reasons": {},
    }


def load_sentiment_engine() -> dict:
    engine = json.loads(ENGINE_JSON.read_text(encoding="utf-8"))
    day = engine["daily"][0]
    dashboard = day["market_dashboard"]
    theme_rows = []
    for item in day.get("theme_ranking", [])[:10]:
        stocks = "、".join(stock["name"] for stock in item.get("top_stocks", [])[:3])
        theme_rows.append(
            {
                "rank": item["rank"],
                "theme_name": item["theme_name"],
                "theme_score": item["theme_score"],
                "limit_up_count": item["limit_up_count"],
                "failed_limit_count": item["failed_limit_count"],
                "failed_limit_rate": item["failed_limit_rate"],
                "highest_board": item["highest_board"],
                "persistence_days": item["persistence_days"],
                "cycle_phase": item["cycle_phase"],
                "top_stocks": stocks or "无",
            }
        )
    role_rows = []
    for item in day.get("stock_role_classification", [])[:15]:
        role_rows.append(
            {
                "code": item["code"],
                "name": item["name"],
                "theme_name": item["theme_name"],
                "role": item["role"],
                "role_score": item["role_score"],
                "risk_flags": item.get("risk_flags", []),
                "evidence": item.get("evidence", [])[:3],
            }
        )
    return {
        "data_dir": engine["data_dir"],
        "data_sources": engine["data_sources"],
        "daily_metric": {
            "date": "2026-09-02",
            "limit_up_count": day["limit_up_count"],
            "failed_limit_count": day["failed_limit_count"],
            "failed_limit_rate": day["failed_limit_rate"],
            "limit_down_count": day["limit_down_count"],
            "highest_board": day["highest_board"],
            "multi_board_count": day["multi_board_count"],
            "prev_limit_avg_pct": day["prev_limit_avg_pct"],
            "prev_limit_positive_rate": day["prev_limit_positive_rate"],
            "sentiment_score": dashboard["sentiment_score"],
            "sentiment_state": dashboard["sentiment_label"],
            "position_band": dashboard["position_band"],
            "discipline": day["discipline_gate"]["discipline_status"],
        },
        "theme_ranking": theme_rows,
        "stock_role_classification": role_rows,
        "data_gaps": engine.get("data_gaps", []),
    }


def build_review() -> dict:
    sentiment_engine = load_sentiment_engine()
    return {
        "schema_version": "2.0",
        "date": "2026-09-02",
        "data_kind": "real",
        "strict_mode": True,
        "completeness": {
            "score": 92,
            "missing_items": [
                "北向资金和两融未纳入当日结论评分",
                "资讯涨停家数与东方财富涨停池口径存在差异，报告以可复现的东方财富池为准",
            ],
        },
        "market_regime": "退潮偏弱、缩量分歧、高低切",
        "market_commentary": [
            "9月2日三大指数同步下跌，创业板指跌幅最大，说明高弹性方向承压更重。",
            "两市成交额维持在约1.79万亿元，但较上一交易日缩量约990亿元，属于高位缩量分歧，而不是放量恐慌。",
            "上涨1537家、下跌3898家，跌多涨少明确，短线赚钱效应退潮。",
            "东方财富涨停池口径显示涨停52家、炸板15家、跌停8家、最高4板、连板13家，炸板率22.39%；资讯口径的涨停家数更高，报告采用可复现接口口径。",
        ],
        "indices": [
            {"name": "上证指数", "close": 3941.39, "change_pct": -0.97, "turnover_yi": 8354.0},
            {"name": "深证成指", "close": 13611.55, "change_pct": -1.88, "turnover_yi": 9558.0},
            {"name": "创业板指", "close": 3312.24, "change_pct": -2.39, "turnover_yi": None},
            {"name": "科创50", "close": 1617.60, "change_pct": -1.82, "turnover_yi": None},
            {"name": "北证50", "close": 1106.57, "change_pct": 2.50, "turnover_yi": None},
        ],
        "sentiment_dashboard": {
            "temperature": "修复偏弱",
            "breadth": "1537涨 / 112平 / 3898跌",
            "liquidity": "高位缩量",
            "risk_appetite": "退潮，资金从高位拥挤方向切向低位军工和材料分支",
            "limit_pool": "东方财富涨停池：涨停52家、炸板15家、炸板率22.39%、跌停8家、最高4板、连板13家；昨日涨停平均-0.76%、红盘率37.35%",
            "loss_feedback": "农业、种植业、农产品加工和部分高位科技方向负反馈明显；跌停池和炸板池显示短线接力仍有分歧。",
        },
        "sector_strength": [
            {"rank": 1, "name": "一般零售", "status": "涨停池强度第1", "evidence": "东方财富池：国芳集团4连板、茂业商业2连板，题材分61.90"},
            {"rank": 2, "name": "IT服务Ⅱ", "status": "涨停池强度第2", "evidence": "东方财富池：竞业达4连板、大位科技首板，题材分56.00"},
            {"rank": 3, "name": "汽车零部", "status": "涨停家数最多", "evidence": "东方财富池：飞龙股份、光洋股份、建设工业等5只涨停"},
            {"rank": 4, "name": "电网设备", "status": "容量分支", "evidence": "东方财富池：杭电股份、远东股份、太阳电缆等4只涨停"},
            {"rank": 5, "name": "军工装备/地面兵装", "status": "逆势主线", "evidence": "东方财富池：内蒙一机2连板、长城军工首板；公开收评确认军工装备逆势活跃"},
            {"rank": 6, "name": "玻璃玻纤/培育钻石", "status": "新分支试盘", "evidence": "公开收评列为涨幅居前方向，持续性待9月3日确认"},
        ],
        "sector_weakness": [
            {"rank": 1, "name": "农业/种植业", "status": "领跌", "evidence": "敦煌种业、登海种业、国投丰乐等跌停或下挫"},
            {"rank": 2, "name": "贵金属/小金属", "status": "明显回落", "evidence": "公开收评列为跌幅居前方向"},
            {"rank": 3, "name": "能源金属/锂电", "status": "承压", "evidence": "风险偏好下降下高弹性资源方向回落"},
            {"rank": 4, "name": "算力硬件", "status": "集体调整", "evidence": "高位拥挤方向出现集中调整，新易盛等高弹性股跌幅较大"},
            {"rank": 5, "name": "游戏/传媒", "status": "回落", "evidence": "公开收评列为跌幅居前或弱势方向"},
            {"rank": 6, "name": "半导体", "status": "分化偏弱", "evidence": "部分硬件链跟随高位科技方向调整"},
        ],
        "limit_ladder": [
            {"height": "4板", "stocks": "竞业达、国芳集团", "read": "东方财富涨停池显示市场高度在4板，短线仍有局部修复锚点"},
            {"height": "3板", "stocks": "欢瑞世纪、集泰股份、三湘印象、返利科技", "read": "3板分布偏零售、传媒、化工等低位轮动，持续性需看晋级"},
            {"height": "2板", "stocks": "内蒙一机、茂业商业、英力特、石化机械等", "read": "2板数量支撑修复结构，但分散度较高"},
            {"height": "炸板", "stocks": "新赛股份、福建金森、郑州煤电、山东墨龙等15只", "read": "炸板率22.39%，不是极端失控，但接力分歧仍重"},
            {"height": "跌停", "stocks": "敦煌种业、雪榕生物、国投丰乐、亚太药业等8只", "read": "农业和医药负反馈集中，是控制仓位的主要约束"},
        ],
        "dragon_tiger": {
            "date": "2026-09-02",
            "amount_yi": 321.14,
            "stock_count": 64,
            "institution_net_buy_count": 13,
            "read": "龙虎榜成交占全市场比例不高，更多是局部短线资金博弈；需要结合次日晋级和断板反馈确认持续性。",
        },
        "tomorrow_plan": [
            {"item": "市场宽度", "trigger": "上涨家数重新超过3000家", "meaning": "退潮转修复；否则仍按弱势分歧处理"},
            {"item": "军工装备", "trigger": "内蒙一机或同梯队继续晋级，首板出现扩散", "meaning": "军工可能从逆势轮动变成短线主线"},
            {"item": "亏钱效应", "trigger": "农业、算力硬件、资源金属跌停数量继续扩大", "meaning": "控制接力仓位，防止退潮扩散"},
            {"item": "量能", "trigger": "成交额回到2万亿附近且指数止跌", "meaning": "承接改善；缩量下跌则继续等待确认"},
        ],
        "data_quality_detail": {
            "status": "公开源完整版，涨停/炸板/跌停/连板已用东方财富池补齐",
            "primary_source": "东方财富/公开行情与数据中心优先，财经媒体交叉核验",
            "resolved_gaps": [
                "东方财富涨停池补齐涨停52家、最高4板、连板13家",
                "东方财富炸板池补齐炸板15家、炸板率22.39%",
                "东方财富跌停池补齐跌停8家",
                "东方财富昨日涨停表现补齐平均涨幅-0.76%、红盘率37.35%",
                "东方财富龙虎榜补齐上榜成交额321.14亿元、上榜64只、机构净买入13只",
            ],
            "source_disagreements": [
                "财经资讯收评口径出现涨停71家/跌停19家，东方财富池落地口径为涨停52家/炸板15家/跌停8家；Dashboard和PDF采用可复现池数据，资讯口径仅作市场描述交叉参考。",
            ],
            "known_gaps": [
                "北向资金和两融未纳入当日评分，原因是9月2日复盘结论主要由指数、宽度、涨跌停池、龙虎榜和题材强弱构成；后续可作为资金面附录单独抓取。",
            ],
            "sources": [
                "新浪财经/国际金融报：https://finance.sina.com.cn/wm/2026-09-02/doc-iniqmmyy2921980.shtml",
                "澎湃新闻：https://www.thepaper.cn/newsDetail_forward_33993073",
                "Investing.com/智通财经：https://cn.investing.com/news/stock-market-news/article-3548248",
                "东方财富涨停池/炸板池/跌停池/昨日涨停表现：AKShare Eastmoney endpoint，本地归档 data/market_reviews/2026-09-02/engine/2026-09-02_to_2026-09-02/",
                "东方财富龙虎榜：https://data.eastmoney.com/stock/tradedetail.html",
            ],
        },
        "sentiment_engine": sentiment_engine,
        "turnover": 17912.0,
        "turnover_delta": -990.0,
        "advancers": 1537,
        "decliners": 3898,
        "limit_up_count": 52,
        "limit_down_count": 8,
        "max_board_height": 4,
        "position_min": 3,
        "position_max": 5,
        "main_themes": [
            {
                "name": "军工装备",
                "rank_no": 1,
                "stage": "验证期",
                "change_status": "strengthened",
                "causal_chain": ["指数退潮", "资金高低切", "军工装备逆市加强"],
                "drivers": [{"code": 37, "name": "龙头效应与补涨", "evidence_level": "B"}],
                "scores": theme_scores(30, 21, 9, 7, 8, -5),
                "delta_reason": "指数下跌时仍有多只军工链个股涨停或大涨，体现逆势承接。",
            },
            {
                "name": "航空装备",
                "rank_no": 2,
                "stage": "验证期",
                "change_status": "strengthened",
                "causal_chain": ["风险偏好下降", "防御和事件方向承接", "航空装备局部活跃"],
                "drivers": [{"code": 38, "name": "风格切换/高低切", "evidence_level": "B"}],
                "scores": theme_scores(27, 18, 8, 6, 7, -6),
                "delta_reason": "航空装备方向在弱市中有局部强势股，强度低于军工装备主线。",
            },
            {
                "name": "玻璃玻纤",
                "rank_no": 3,
                "stage": "发酵期",
                "change_status": "expanded",
                "causal_chain": ["弱市轮动", "低位材料分支活跃", "山东玻纤等个股确认"],
                "drivers": [{"code": 38, "name": "风格切换/高低切", "evidence_level": "B"}],
                "scores": theme_scores(24, 16, 7, 5, 6, -6),
                "delta_reason": "玻纤方向有轮动活跃，但持续性和扩散强度仍需次日确认。",
            },
            {
                "name": "培育钻石",
                "rank_no": 4,
                "stage": "朦胧期",
                "change_status": "new",
                "causal_chain": ["主线退潮", "资金尝试新分支", "培育钻石被公开收评列为活跃方向"],
                "drivers": [{"code": 38, "name": "风格切换/高低切", "evidence_level": "B"}],
                "scores": theme_scores(21, 13, 7, 4, 5, -7),
                "delta_reason": "公开收评列为涨幅居前方向，但缺少完整领涨股和成交额核验。",
            },
            {
                "name": "农业回落",
                "rank_no": 5,
                "stage": "兑现期",
                "change_status": "weakened",
                "causal_chain": ["前期轮动分支承压", "粮食概念领跌", "多只农业股跌停或下挫"],
                "drivers": [{"code": 38, "name": "风格切换/高低切", "evidence_level": "B"}],
                "scores": theme_scores(18, 8, 4, 3, 2, -10),
                "delta_reason": "敦煌种业、登海种业、国投丰乐等承压，农业方向进入回落观察。",
            },
        ],
        "stocks": [
            {
                "name": "北方长龙",
                "code": "301357",
                "theme": "军工装备",
                "role": "龙头",
                "role_detail": "军工装备弹性核心",
                "stage": "验证期",
                "drivers": [{"code": 37, "name": "龙头效应与补涨", "evidence_level": "B"}],
                "catalyst": "弱市逆势涨超13%，带动军工装备辨识度",
                "benefit_path": ["弱市高低切", "军工装备承接", "弹性股确认"],
                "causal_chain": ["市场退潮", "军工逆势", "北方长龙大涨"],
                "scores": stock_scores(78, 84, 62, 68),
                "delta_reason": "当日军工链弹性最突出之一。",
            },
            {
                "name": "长城军工",
                "code": "601606",
                "theme": "军工装备",
                "role": "中军",
                "role_detail": "军工装备涨停确认",
                "stage": "验证期",
                "drivers": [{"code": 37, "name": "龙头效应与补涨", "evidence_level": "B"}],
                "catalyst": "军工装备板块逆势涨停",
                "benefit_path": ["板块加强", "涨停确认", "中军承接"],
                "causal_chain": ["板块逆势", "资金承接", "涨停确认"],
                "scores": stock_scores(73, 78, 60, 66),
                "delta_reason": "涨停确认军工装备强度。",
            },
            {
                "name": "内蒙一机",
                "code": "600967",
                "theme": "军工装备",
                "role": "情绪股",
                "role_detail": "2连板情绪锚",
                "stage": "验证期",
                "drivers": [{"code": 41, "name": "情绪抱团/妖股", "evidence_level": "B"}],
                "catalyst": "2连板提高板块短线辨识度",
                "benefit_path": ["连板确认", "情绪聚焦", "军工扩散"],
                "causal_chain": ["军工活跃", "连板出现", "短线辨识度提升"],
                "scores": stock_scores(72, 82, 54, 60),
                "delta_reason": "2连板是当日连板高度和情绪观察点。",
            },
            {
                "name": "山东玻纤",
                "code": "605006",
                "theme": "玻璃玻纤",
                "role": "龙头",
                "role_detail": "玻纤方向代表股",
                "stage": "发酵期",
                "drivers": [{"code": 38, "name": "风格切换/高低切", "evidence_level": "B"}],
                "catalyst": "玻纤方向被公开收评列为活跃分支",
                "benefit_path": ["弱市轮动", "材料分支活跃", "个股确认"],
                "causal_chain": ["指数分歧", "低位材料轮动", "玻纤个股表现"],
                "scores": stock_scores(62, 66, 52, 58),
                "delta_reason": "分支活跃但强度和持续性待确认。",
            },
            {
                "name": "敦煌种业",
                "code": "600354",
                "theme": "农业回落",
                "role": "情绪股",
                "role_detail": "领跌风险观察",
                "stage": "兑现期",
                "drivers": [{"code": 38, "name": "风格切换/高低切", "evidence_level": "B"}],
                "catalyst": "农业方向领跌并出现跌停反馈",
                "benefit_path": ["前期轮动兑现", "资金流出", "跌停反馈"],
                "causal_chain": ["农业走弱", "亏钱效应扩散", "跌停确认"],
                "scores": stock_scores(35, 30, 25, 45),
                "delta_reason": "作为风险样本纳入，不作为正向候选。",
            },
        ],
        "evidence": [
            {
                "entity_type": "market",
                "entity_key": "2026-09-02",
                "evidence_level": "B",
                "evidence_type": "market_close",
                "title": "A股收评：创业板指跌2.39%，近3900只个股下跌",
                "source_name": "新浪财经/国际金融报",
                "source_url": "https://finance.sina.com.cn/wm/2026-09-02/doc-iniqmmyy2921980.shtml",
                "published_at": None,
                "excerpt": "三大指数下跌，全市场成交额超过1.8万亿元，近3900只个股下跌。",
                "verified": True,
            },
            {
                "entity_type": "market",
                "entity_key": "2026-09-02",
                "evidence_level": "B",
                "evidence_type": "market_breadth",
                "title": "Wind口径显示1537只上涨、3898只下跌",
                "source_name": "澎湃新闻",
                "source_url": "https://www.thepaper.cn/newsDetail_forward_33993073",
                "published_at": None,
                "excerpt": "Wind统计口径下，全市场上涨1537家，下跌3898家。",
                "verified": True,
            },
            {
                "entity_type": "theme",
                "entity_key": "军工装备",
                "evidence_level": "B",
                "evidence_type": "theme_strength",
                "title": "军工股全线爆发，军工装备逆市活跃",
                "source_name": "Investing.com/智通财经",
                "source_url": "https://cn.investing.com/news/stock-market-news/article-3548248",
                "published_at": None,
                "excerpt": "军工、玻纤、培育钻石等板块涨幅居前。",
                "verified": True,
            },
        ],
        "risk_events": [
            {
                "entity_type": "market",
                "entity_key": "2026-09-02",
                "risk_type": "宽度退潮",
                "severity": "high",
                "penalty": -10,
                "description": "下跌家数显著高于上涨家数，三大指数同步下跌。",
                "invalidation_condition": "次日上涨家数重新超过下跌家数且成交额放大。",
            }
        ],
        "tomorrow_checks": [
            {
                "entity_type": "market",
                "entity_key": "2026-09-02",
                "check_type": "breadth_repair",
                "description": "9月3日上涨家数能否回到3000家以上，确认是否从退潮转修复。",
            },
            {
                "entity_type": "theme",
                "entity_key": "军工装备",
                "check_type": "theme_persistence",
                "description": "军工装备能否继续出现连板晋级和板块扩散，而不是一日轮动。",
            },
            {
                "entity_type": "theme",
                "entity_key": "农业回落",
                "check_type": "loss_feedback",
                "description": "农业方向跌停股是否继续负反馈，判断亏钱效应是否扩散。",
            },
        ],
        "tomorrow_check_updates": [],
        "changes_vs_previous_day": {
            "new": ["培育钻石"],
            "strengthened": ["军工装备", "航空装备"],
            "weakened": ["农业回落"],
            "expanded": ["玻璃玻纤"],
            "realized": [],
            "invalidated": [],
        },
    }


def main() -> None:
    review = build_review()
    DailyReview.model_validate(review)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(OUTPUT)


if __name__ == "__main__":
    main()
