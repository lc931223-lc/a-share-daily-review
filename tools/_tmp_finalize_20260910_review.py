from __future__ import annotations
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.formal_review.persistence import import_record

DAY='2026-09-10'; PREV='2026-09-09'
SUPPORT=json.loads((ROOT/f'data/formal_review_support/{DAY}.json').read_text(encoding='utf-8'))
CONTEXT=json.loads((ROOT/f'data/review_context/{DAY}.json').read_text(encoding='utf-8'))
ROWS=SUPPORT.get('theme_support',[])
CAT={x['factor_id']:x['factor_name'] for x in SUPPORT['factor_catalog']}

def evs(rows):
    out=[]
    for e in rows or []:
        out.append({'source':str(e.get('source') or 'MarketPacket/ReviewIntelligence'),'source_type':str(e.get('source_type') or 'objective_calculation'),'source_date':str(e.get('source_date') or DAY)[:10],'tier':int(e.get('tier') or 3),'confidence':str(e.get('confidence') or 'MEDIUM'),**({'url':e.get('url')} if 'url' in e else {})})
    return out

def factors(src):
    by={int(f['factor_id']):f for f in src.get('41_factors',[])}
    out=[]
    for i in range(1,42):
        f=by.get(i,{})
        st=f.get('status','UNCONFIRMED')
        e=evs(f.get('evidence')) if st in {'CONFIRMED','PARTIAL'} else []
        out.append({'factor_id':i,'factor_name':CAT[i],'status':st,'evidence':e,'confidence':f.get('confidence','MEDIUM' if e else 'NONE')})
    return out

def comp(raw,avail,reason):
    return {'raw_score':raw,'available_score':avail,'subcomponents':[],'evidence':[],'reason':reason}

def nv(point,strong,weak,fals):
    return {'validation_point':point,'strengthening_condition':strong,'weakening_condition':weak,'falsification_condition':fals}

J=[
 {'name':'多元金融','score':68.0,'rating':'B','state':'VALIDATION','core':[('600318.SH','新力金融','ELASTICITY',94.03)],'reason':'Weak-market relative strength and a sharp financial-style rotation support a validation state, but no same-date hard fundamental catalyst is confirmed.','checks':[nv('弱市中的独立强度能否延续','竞价板块正向广度>=60%，且新力金融相对强度继续为正','仅单一高标强而板块无扩散','新力金融与板块同步转弱且开盘后无法修复')]},
 {'name':'旅游及景区','score':64.0,'rating':'B','state':'VALIDATION','core':[('000978.SZ','桂林旅游','CAPACITY',78.95)],'reason':'Objective strength remains elevated and 桂林旅游 has a confirmed high-volume breakout; unchanged one-day strength and absent fundamental evidence keep this as validation rather than main-up.','checks':[nv('突破结构是否保持','桂林旅游竞价量能>=自身历史60分位且竞价后不快速失守','竞价量能偏弱或突破后快速回落','桂林旅游跌破关键突破结构且板块同步弱')]},
 {'name':'食品加工','score':62.0,'rating':'C','state':'VALIDATION','core':[('002661.SZ','克明食品','CAPACITY',74.8)],'reason':'Strong one-day objective-strength acceleration and a confirmed breakout candidate support a tactical validation line, but the broader market is risk-off and no hard fundamental driver is confirmed.','checks':[nv('防御/消费轮动是否获得容量确认','克明食品竞价量能>=自身历史60分位且板块正向广度>=55%','容量股偏弱且仅小票活跃','克明食品与板块同时转弱且无承接')]}
]

def find(name):
    for x in ROWS:
        if x.get('theme_identity',{}).get('canonical_name')==name or x.get('theme_name')==name or (name=='旅游及景区' and x.get('theme_name')=='旅游及景'):
            return x
    raise RuntimeError(name)

def theme(rank,j):
    s=find(j['name'])
    cores=[{'code':c,'name':n,'role':r,'role_score':sc,'role_confidence':'MEDIUM','reason':['ChatGPT role judgement from objective candidate scores'],'confirmed_evidence':[],'unconfirmed_claims':['No same-date hard fundamental catalyst confirmed.']} for c,n,r,sc in j['core']]
    continuity=max(0.0,min(10.0,5.0 + float((s.get('lifecycle_inputs') or {}).get('strength_change_1d') or 0)/10.0))
    market=7.0 if rank==1 else 6.0
    scores={'base_logic':comp(None,0,'No same-date qualifying fundamental evidence; not inferred from price.'),'realization':comp(None,0,'No same-date qualifying order/earnings realization evidence.'),'expectation_gap':comp(None,0,'Exact previous formal review for 2026-09-09 is unavailable.'),'continuity':comp(round(continuity,2),10,'Objective one-day theme strength change.'),'market_confirmation':comp(market,10,'Relative objective strength under a weak overall market.'),'risk_deduction':comp(2.0 if rank==1 else 1.0,8,'Weak full-market breadth and shrinking turnover are explicit macro risk.'),'total_score':j['score'],'rating':j['rating']}
    return {'theme_name':j['name'],'theme_rank':rank,'41_factors':factors(s),'base_logic_score':None,'realization_score':None,'expectation_gap_score':None,'continuity_score':round(continuity,2),'market_confirmation_score':market,'risk_deduction':2.0 if rank==1 else 1.0,'total_score':j['score'],'rating':j['rating'],'scores':scores,'lifecycle':{'previous_state':None,'current_state':j['state'],'transition_reason':j['reason'],'positive_evidence':['Objective relative strength is available'],'negative_evidence':['Only 955 advancers vs 4512 decliners','Total turnover contracted materially','No same-date hard fundamental factor confirmed'],'confidence':'MEDIUM'},'previous_lifecycle':None,'core_stocks':cores,'next_day_validation':j['checks'],'uncertainties':['Exact 2026-09-09 formal review unavailable; lifecycle comparison is not formal-delta eligible.','Theme strength is primarily market-structure evidence, not order/earnings validation.']}

m=CONTEXT.get('market_environment') or {}
# fallback to compact snapshot if review_context fields differ
payload={
 'schema_version':'formal_review.3','date':DAY,'previous_trade_date':PREV,'final_judgement_owner':'chatgpt',
 'market_overview':{'total_turnover':1662337526004.42,'turnover_change_abs':-210729513778.89,'rise_count':955,'fall_count':4512,'median_return':-1.4908,'limit_up_count':35,'limit_down_count':11,'failed_limit_count':22,'failed_limit_rate':38.6,'highest_board':4,'interpretation':'Broad risk-off session with sharply negative breadth and shrinking turnover; only localized theme/limit-up style strength remained.'},
 'market_regime':'风险收缩、广度显著恶化、成交缩量；局部抱团与防御轮动替代全面主线进攻',
 'main_themes':[theme(i+1,j) for i,j in enumerate(J)],
 'changes_vs_previous_day':{'new':[],'strengthened':[],'weakened':[],'diffused':[],'realized':[],'falsified':[]},
 'previous_day_validation':{'records':[],'prediction_count':0,'confirmed_count':0,'partial_count':0,'failed_count':0,'not_evaluable_count':0,'hit_rate':None,'weighted_hit_rate':None},
 'tomorrow_checks':[
   {'id':'fin_breadth_0911','entity_type':'theme','entity_key':'多元金融','metric':'sector_positive_ratio','operator':'>=','threshold':0.6,'time_window':'auction','description':'多元金融竞价正向广度至少60%'},
   {'id':'fin_rel_0911','entity_type':'stock','entity_key':'600318.SH','metric':'relative_strength','operator':'>=','threshold':0,'time_window':'auction','description':'新力金融竞价相对强度保持非负'},
   {'id':'tourism_amt_0911','entity_type':'stock','entity_key':'000978.SZ','metric':'auction_amount_percentile','operator':'>=','threshold':60,'time_window':'auction','description':'桂林旅游竞价金额达到自身历史60分位以上'},
   {'id':'food_amt_0911','entity_type':'stock','entity_key':'002661.SZ','metric':'auction_amount_percentile','operator':'>=','threshold':60,'time_window':'auction','description':'克明食品竞价金额达到自身历史60分位以上'}],
 'uncertainties':['Exact 2026-09-09 formal review is unavailable, so formal previous-day hit-rate is intentionally unavailable.','2026-09-10 objective support quality is PARTIAL.','No top formal theme has same-date qualifying hard fundamental evidence; price strength must not be restated as order/earnings confirmation.']}
print(json.dumps(import_record(ROOT,payload),ensure_ascii=False))
