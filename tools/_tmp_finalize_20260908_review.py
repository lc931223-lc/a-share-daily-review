from __future__ import annotations

import json
from pathlib import Path

from src.formal_review.persistence import import_record

ROOT = Path(__file__).resolve().parents[1]
DAY = "2026-09-08"
PREV = "2026-09-07"
FACTOR_NAMES = {
1:"0→1技术突破",2:"1→10渗透率提升",3:"国产替代/自主可控",4:"海外产业映射",5:"国家级产业政策",6:"财政刺激/补贴",7:"货币与流动性政策",8:"监管边际改善/行业松绑",9:"反内卷/供给侧改革",10:"国企改革/市值管理",11:"国际重大事件",12:"国内重大会议/重要文件",13:"行业大会/产品发布会",14:"突发供给事故",15:"需求型涨价",16:"供给收缩型涨价",17:"库存周期/补库",18:"成本下降+售价稳定",19:"大额订单",20:"订单超预期",21:"下游资本开支爆发",22:"排产/交期/稼动率",23:"业绩超预期",24:"亏损转盈利/困境反转",25:"利润率提升",26:"业绩加速",27:"并购重组",28:"资产注入/控制权变更",29:"股权激励",30:"回购/增持/高分红",31:"重大客户认证/新供应链",32:"行业出清",33:"估值修复",34:"增量资金",35:"指数纳入/被动配置",36:"筹码出清/突破",37:"龙头效应与补涨",38:"风格切换/高低切",39:"名称玄学",40:"生肖/谐音/数字/地名",41:"情绪抱团/妖股"}

def read(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))

def evidence_rows(rows):
    out=[]
    for e in rows or []:
        out.append({
            "source": str(e.get("source") or "MarketPacket/ReviewIntelligence"),
            "source_type": str(e.get("source_type") or "objective_calculation"),
            "source_date": str(e.get("source_date") or DAY)[:10],
            "tier": int(e.get("tier") or 3),
            "confidence": str(e.get("confidence") or "MEDIUM"),
            **({"url": e.get("url")} if "url" in e else {}),
        })
    return out

def factor_rows(theme):
    by_id={int(f["factor_id"]):f for f in theme.get("41_factors",[])}
    result=[]
    for i in range(1,42):
        src=by_id.get(i,{})
        status=src.get("status","UNCONFIRMED")
        ev=evidence_rows(src.get("evidence",[])) if status in {"CONFIRMED","PARTIAL"} else []
        result.append({
            "factor_id":i,"factor_name":FACTOR_NAMES[i],"status":status,
            "evidence":ev,"confidence":src.get("confidence","MEDIUM" if ev else "NONE")
        })
    return result

def component(raw, available, reason):
    return {"raw_score":raw,"available_score":available,"subcomponents":[],"evidence":[],"reason":reason}

def nv(point,strong,weak,false):
    return {"validation_point":point,"strengthening_condition":strong,"weakening_condition":weak,"falsification_condition":false}

support=read(f"data/formal_review_support/{DAY}.json")
context=read(f"data/review_context/{DAY}.json")
rows=sorted(support.get("theme_support",[]), key=lambda x:int(x.get("theme_rank") or x.get("rank") or 999))
if len(rows)<3:
    raise RuntimeError("formal review support has fewer than three ranked themes")
by_rank={int(x.get("theme_rank") or x.get("rank")):x for x in rows}

judgements={
1:{"name":"农化制品","score":78.0,"rating":"A","state":"VALIDATION","prev":None,"continuity":10.0,"market":10.0,
   "transition":"Objective strength 81.88, strong one-day acceleration, 100% breadth and 8 limit-ups support validation; no qualifying same-date fundamental factor prevents high-confidence fundamental MAIN_UP classification.",
   "cores":[("002470.SZ","金正大","LEADER",75.17,["LEADER_CANDIDATE","objective theme leadership"]),("600227.SH","赤天化","CAPACITY",93.54,["CAPACITY_CANDIDATE","capital_preference_score=70.64"]),("603077.SH","和邦生物","TREND_LEADER",84.15,["TREND_LEADER_CANDIDATE"])],
   "validation":[nv("主题成交额与广度继续保持前列","竞价板块正向广度>=60%，容量股同步不掉队","板块广度下降或仅高标独强","龙头与容量同时转弱且板块广度跌破40%"),nv("容量与弹性共振","赤天化竞价量能达到自身历史60分位以上，且金正大保持板块领先","仅金正大高开而赤天化/和邦生物明显偏弱","容量与趋势核心同步低于板块且开盘后无法修复")],
   "uncertainties":["No same-date qualifying fundamental factor confirmed; classification is market-structure-led.","Parent chemical-products theme overlaps and is not double-counted as a separate formal mainline."]},
2:{"name":"出版","score":74.0,"rating":"B","state":"MAIN_UP","prev":"VALIDATION","continuity":8.2422,"market":10.0,
   "transition":"Objective strength 78.63 with 100% breadth, 4 limit-ups and confirmed high-volume breakouts supports a MAIN_UP market-structure state; absence of fundamental evidence keeps confidence medium.",
   "cores":[("300788.SZ","中信出版","LEADER",100.0,["LEADER_CANDIDATE","TREND_LEADER_CANDIDATE","ELASTICITY_CANDIDATE"]),("601999.SH","出版传媒","CAPACITY",81.66,["CAPACITY_CANDIDATE","capital_preference_score=68.81"])],
   "validation":[nv("主升结构是否由容量确认","出版传媒竞价量能达到历史60分位以上且板块正向广度>=60%","中信出版独强、出版传媒和板块广度明显走弱","龙头与容量同步转弱且突破结构失守"),nv("突破结构延续","前一日确认的高量突破个股竞价/开盘后不出现集体回落","突破股分化但容量仍稳","突破股与容量同时失守")],
   "uncertainties":["No same-date qualifying fundamental factor confirmed; current strength is primarily technical/market-structure evidence."]},
3:{"name":"农产品加工","score":72.0,"rating":"B","state":"VALIDATION","prev":"VALIDATION","continuity":10.0,"market":10.0,
   "transition":"Objective strength 74.71, 100% breadth, 4 limit-ups and confirmed breakout evidence support continued validation; no hard fundamental catalyst is confirmed, so the line is not promoted to MAIN_UP.",
   "cores":[("920371.BJ","欧福蛋业","LEADER",100.0,["LEADER_CANDIDATE","TREND_LEADER_CANDIDATE","ELASTICITY_CANDIDATE"]),("600127.SH","金健米业","CAPACITY",100.0,["CAPACITY_CANDIDATE","TREND_LEADER_CANDIDATE","capital_preference_score=82.31"])],
   "validation":[nv("龙头与容量共振","欧福蛋业保持相对强势，金健米业竞价量能>=自身历史60分位","弹性股独强、金健米业明显偏弱","欧福蛋业与金健米业同时转弱且板块广度跌破40%"),nv("板块广度持续","竞价板块正向广度>=60%","板块广度40%-60%","板块广度<40%且核心同步弱")],
   "uncertainties":["No same-date qualifying fundamental factor confirmed; current thesis is market-structure-led."]}
}

def make_theme(rank):
    src=by_rank[rank]; j=judgements[rank]
    factors=factor_rows(src)
    cores=[]
    for code,name,role,score,reasons in j["cores"]:
        cores.append({"code":code,"name":name,"role":role,"role_score":score,"role_confidence":"MEDIUM","reason":reasons,"confirmed_evidence":[],"unconfirmed_claims":["Role is a ChatGPT judgement from objective market-structure candidates; no same-date hard fundamental catalyst is confirmed."]})
    scores={
      "base_logic":component(None,0,"No same-date qualifying fundamental evidence; unavailable rather than inferred from price."),
      "realization":component(None,0,"No same-date qualifying order/earnings/price-cycle realization evidence."),
      "expectation_gap":component(None,0,"Exact previous formal review is unavailable, so no formal expectation baseline exists."),
      "continuity":component(j["continuity"],10,"Objective short-window continuity support from formal_review_support."),
      "market_confirmation":component(j["market"],10,"Objective theme return/breadth/limit-up/liquidity confirmation."),
      "risk_deduction":component(0.0,8,"No explicit supported deduction is applied; unavailable risks are not assumed absent."),
      "total_score":j["score"],"rating":j["rating"]}
    return {"theme_name":j["name"],"theme_rank":rank,"41_factors":factors,"base_logic_score":None,"realization_score":None,"expectation_gap_score":None,"continuity_score":j["continuity"],"market_confirmation_score":j["market"],"risk_deduction":0.0,"total_score":j["score"],"rating":j["rating"],"scores":scores,"lifecycle":{"previous_state":j["prev"],"current_state":j["state"],"transition_reason":j["transition"],"positive_evidence":["Strong objective theme strength/breadth","Same-date market confirmation is available"],"negative_evidence":["No same-date qualifying fundamental factor confirmed","Exact previous formal review unavailable"],"confidence":"MEDIUM"},"previous_lifecycle":j["prev"],"core_stocks":cores,"next_day_validation":j["validation"],"uncertainties":j["uncertainties"]}

m=context.get("market_environment") or {}
payload={
 "schema_version":"formal_review.3","date":DAY,"previous_trade_date":PREV,"final_judgement_owner":"chatgpt",
 "market_overview":{"total_turnover":m.get("total_turnover"),"turnover_change_pct":m.get("turnover_change_pct"),"rise_count":m.get("rise_count"),"fall_count":m.get("fall_count"),"flat_count":m.get("flat_count"),"limit_up_count":m.get("limit_up_count"),"limit_down_count":m.get("limit_down_count"),"failed_limit_count":m.get("failed_limit_count"),"seal_rate":m.get("seal_rate"),"highest_board":m.get("highest_board"),"previous_limit_avg_return":m.get("previous_limit_avg_return"),"continuous_board_feedback":m.get("continuous_board_feedback"),"market_operability_score":m.get("market_operability_score"),"market_operability_available_max":m.get("market_operability_available_max"),"interpretation":"Breadth and short-line feedback are strong while turnover contracted; this is a profitable multi-theme expansion/validation environment, not a clean single hard-fundamental mainline."},
 "market_regime":"赚钱效应扩散、短线反馈偏强但成交缩量；低位/题材轮动与多主线验证并存",
 "main_themes":[make_theme(1),make_theme(2),make_theme(3)],
 "changes_vs_previous_day":{"new":[],"strengthened":[],"weakened":[],"diffused":[],"realized":[],"falsified":[]},
 "previous_day_validation":{"records":[],"prediction_count":0,"confirmed_count":0,"partial_count":0,"failed_count":0,"not_evaluable_count":0,"hit_rate":None,"weighted_hit_rate":None},
 "tomorrow_checks":[
  {"id":"agro_breadth_0909","entity_type":"theme","entity_key":"农化制品","metric":"sector_positive_ratio","operator":">=","threshold":0.6,"time_window":"auction","description":"农化制品竞价正向广度至少60%"},
  {"id":"agro_capacity_0909","entity_type":"stock","entity_key":"600227.SH","metric":"auction_amount_percentile","operator":">=","threshold":60,"time_window":"auction","description":"赤天化竞价金额达到自身历史60分位以上"},
  {"id":"publishing_breadth_0909","entity_type":"theme","entity_key":"出版","metric":"sector_positive_ratio","operator":">=","threshold":0.6,"time_window":"auction","description":"出版板块竞价正向广度至少60%"},
  {"id":"publishing_capacity_0909","entity_type":"stock","entity_key":"601999.SH","metric":"auction_amount_percentile","operator":">=","threshold":60,"time_window":"auction","description":"出版传媒竞价金额达到自身历史60分位以上"},
  {"id":"food_breadth_0909","entity_type":"theme","entity_key":"农产品加工","metric":"sector_positive_ratio","operator":">=","threshold":0.6,"time_window":"auction","description":"农产品加工竞价正向广度至少60%"},
  {"id":"food_capacity_0909","entity_type":"stock","entity_key":"600127.SH","metric":"auction_amount_percentile","operator":">=","threshold":60,"time_window":"auction","description":"金健米业竞价金额达到自身历史60分位以上"}],
 "uncertainties":["Exact 2026-09-07 formal review is unavailable, so formal previous-day hit-rate and expectation-gap validation are intentionally unavailable.","2026-09-08 formal support quality is PARTIAL_WITH_UPSTREAM_FAILURE; Market Packet quality is FAIL and Review Context is PARTIAL.","No same-date qualifying fundamental factor is confirmed for the top three formal mainlines; market strength must not be restated as order/earnings validation.","The 2026-09-08 auction packet is unavailable and is not backfilled from another date."]}

result=import_record(ROOT,payload)
print(json.dumps(result,ensure_ascii=False))
