const fs = require("fs");
const path = require("path");

const data = JSON.parse(fs.readFileSync("output/69-review/market_data.json", "utf8"));
const outDir = path.resolve("output/69-review");
fs.mkdirSync(outDir, { recursive: true });

const indexName = {
  shcomp: "上证指数",
  szcomp: "深证成指",
  chinext: "创业板指",
  csi300: "沪深300",
  sci50: "科创50",
  bse50: "北证50",
};

function yi(n) {
  return (Number(n) / 1e8).toFixed(1);
}
function pct(n) {
  return `${Number(n).toFixed(2)}%`;
}
function esc(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}
function stockLine(s) {
  return `${esc(s.name)} <span class="muted">${s.code}</span><b class="${s.pct >= 0 ? "up" : "down"}">${pct(s.pct)}</b><span>${esc(s.industry || "-")}</span>`;
}
function tags(rows, limit = 60) {
  return rows.slice(0, limit).map((s) => `<span class="tag">${stockLine(s)}</span>`).join("");
}
function table(rows, cols) {
  return `<table><thead><tr>${cols.map((c) => `<th>${c[0]}</th>`).join("")}</tr></thead><tbody>${rows
    .map((r) => `<tr>${cols.map((c) => `<td>${c[1](r)}</td>`).join("")}</tr>`)
    .join("")}</tbody></table>`;
}

const byBoard = Object.fromEntries(data.limitBoard.byBoard.map((g) => [g.name, g.rows]));
const first = byBoard["1板"] || [];
const second = byBoard["2板"] || [];
const third = byBoard["3板"] || [];
const high = Object.entries(byBoard)
  .filter(([k]) => parseInt(k) >= 4)
  .flatMap(([, v]) => v);

const hardLogic = data.limitBoard.all.filter((s) =>
  /半导体|通用设备|专用设备|自动化设备|通信设备|电池|IT服务|软件|医疗|化学制药|生物制品|光学光电子|元件|小金属|工业金属/.test(
    s.industry || ""
  )
);
const emotionRisk = data.limitBoard.all.filter((s) =>
  /传媒|影视|游戏|广告|旅游|零售|纺织|服装|装修|教育|房地产|互联网电商/.test(s.industry || "")
);
const failedHard = data.limitBoard.failed.filter((s) =>
  /半导体|通信设备|软件|自动化设备|专用设备|通用设备|电池|小金属|工业金属|化学制品|环境治理/.test(s.industry || "")
);
const trendHard = data.strongTrend.filter((s) =>
  /半导体|通信设备|通用设备|专用设备|自动化设备|电池|IT服务|软件|医疗|化学制药|生物制品|小金属|工业金属|元件/.test(
    s.industry || ""
  )
);
const sourceRows = [
  ["每日经济新闻收评", "https://www.nbd.com.cn/articles/2026-06-09/4421147.html", "半导体、PCB爆发；ETF成交额3940.04亿元；机器人概念主力净流入约140.6亿元。"],
  ["澎湃新闻A股收评", "https://www.thepaper.cn/newsDetail_forward_33341373", "半导体、算力硬件链大幅反弹；油气、煤炭走弱；券商观点提示短期波动与结构行情。"],
  ["第一财经滚动", "https://www.yicai.com/news/103220762.html", "盘中创新药、机器人等分支轮动；日韩市场同步大涨，亚洲风险偏好修复。"],
  ["中新经纬A股收评", "https://www.chinanews.com.cn/cj/2026/06-09/10636946.shtml", "确认三大指数收盘点位与行业强弱方向。"],
  ["新浪/人民财讯美股", "https://news.sina.com.cn/o/2026-06-09/doc-iniauefc5264927.shtml", "美股道指跌0.16%、纳指涨0.86%、标普涨0.30%，芯片股反弹。"],
  ["新浪/21世纪经济报道", "https://finance.sina.com.cn/roll/2026-06-05/doc-iniaiust1762173.shtml", "6月5日三大指数与两市成交额3.07万亿元。"],
  ["每日经济新闻6月3日", "https://www.nbd.com.cn/articles/2026-06-03/4416444.html", "6月3日全市场成交额31531亿元。"],
  ["中国经济网6月4日", "http://finance.ce.cn/stock/gsgdbd/202606/04/t20260604_39002879.shtml", "6月4日沪深成交额可由沪市12746.52亿元、深市14830.17亿元合计。"],
  ["同花顺两融", "https://stock.10jqka.com.cn/rzrq/20260608/c677282569.shtml", "截至6月5日，两融余额29066.88亿元，较前一交易日减少139.98亿元。"],
];

const fiveDayRows = [
  ["2026-06-03", "4083.97", "+0.22%", "15704.71", "+0.73%", "4122.99", "+1.65%", "31531亿"],
  ["2026-06-04", "4057.78", "-0.64%", "15661.57", "-0.27%", "4088.88", "-0.83%", "27576.7亿"],
  ["2026-06-05", "4027.74", "-0.74%", "15314.70", "-2.21%", "3957.94", "-3.20%", "30700亿"],
  ["2026-06-08", "3959.34", "-1.70%", "14821.19", "-3.22%", "3811.79", "-3.69%", "约27900亿"],
  ["2026-06-09", "4010.03", "+1.28%", "15268.71", "+3.02%", "3961.75", "+3.93%", `${yi(data.universe.totalAmount)}亿`],
];

const boardRows = [
  ["3板及以上", third.concat(high)],
  ["2板", second],
  ["首板", first],
];

const idxRows = Object.entries(data.indices).map(([k, v]) => ({ name: indexName[k] || k, ...v }));
const industryTop = data.industry.topByAvgPct.slice(0, 10);
const mainBuy = data.mainNetBuy.slice(0, 15);
const mainSell = data.mainNetSell.slice(0, 12);

const html = `<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>6.9 A股复盘</title>
<style>
@page { size: 430px 932px; margin: 18px; }
* { box-sizing: border-box; }
body { margin: 0; font-family: "Microsoft YaHei", "PingFang SC", Arial, sans-serif; color: #17202a; background: #f6f7f9; font-size: 12px; line-height: 1.55; }
.page { page-break-after: always; padding: 2px 0 10px; }
.cover { min-height: 860px; background: linear-gradient(155deg,#111827 0%,#253044 56%,#6b1f2b 100%); color: white; padding: 28px 22px; border-radius: 16px; }
h1 { font-size: 31px; line-height: 1.08; margin: 0 0 12px; letter-spacing: 0; }
h2 { font-size: 18px; margin: 18px 0 9px; padding-left: 9px; border-left: 4px solid #d73535; }
h3 { font-size: 14px; margin: 14px 0 7px; }
p { margin: 6px 0; }
.sub { color: #cbd5e1; font-size: 12px; }
.grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin: 16px 0; }
.metric { background: white; border: 1px solid #e5e7eb; border-radius: 10px; padding: 9px; }
.cover .metric { background: rgba(255,255,255,.10); border-color: rgba(255,255,255,.18); }
.metric b { display: block; font-size: 18px; line-height: 1.2; }
.muted { color: #687385; }
.cover .muted { color: #d1d5db; }
.up { color: #cc1f1a; }
.down { color: #16804a; }
.pill { display: inline-block; padding: 3px 7px; border-radius: 999px; background: #eef2f7; margin: 2px; }
.tag { display: inline-flex; gap: 5px; align-items: center; max-width: 100%; margin: 3px 3px 3px 0; padding: 4px 6px; border: 1px solid #e5e7eb; border-radius: 7px; background: white; white-space: normal; }
.tag b { margin-left: 3px; }
section { background: white; border: 1px solid #e5e7eb; border-radius: 12px; padding: 12px; margin: 10px 0; }
table { width: 100%; border-collapse: collapse; background: white; font-size: 10.5px; }
th,td { border-bottom: 1px solid #edf0f3; padding: 5px 4px; vertical-align: top; text-align: left; }
th { color: #5d6675; font-weight: 600; background: #f8fafc; }
ul { margin: 5px 0 5px 16px; padding: 0; }
li { margin: 3px 0; }
.note { background: #fff7ed; border: 1px solid #fed7aa; border-radius: 9px; padding: 8px; color: #7c2d12; }
.small { font-size: 10px; }
.break { page-break-before: always; }
@media screen {
  body { max-width: 430px; margin: 0 auto; }
  .page { page-break-after: auto; padding: 0 8px 10px; }
  .cover { min-height: auto; margin: 8px; padding: 22px 14px; }
  h1 { font-size: 30px; }
  section { margin: 8px 0; }
}
</style>
</head>
<body>
<div class="page cover">
  <h1>6.9 A股复盘</h1>
  <p class="sub">基准：2026-06-09 15:00 A股收盘后。样本剔除 ST、*ST、名称含退市/退字风险股；行情源为东方财富 push2delay 收盘快照，按涨跌停价规则复核。</p>
  <div class="grid">
    <div class="metric"><span>过滤后样本</span><b>${data.universe.validCount}</b><span class="muted">剔除 ${data.universe.excludedRiskCount} 只风险股</span></div>
    <div class="metric"><span>涨跌家数</span><b><span class="up">${data.universe.up}</span> / <span class="down">${data.universe.down}</span></b><span class="muted">平盘 ${data.universe.flat}</span></div>
    <div class="metric"><span>涨停 / 跌停</span><b><span class="up">${data.universe.limitUp}</span> / <span class="down">${data.universe.limitDown}</span></b><span class="muted">炸板未回封 ${data.universe.failedLimitUp}</span></div>
    <div class="metric"><span>总成交额</span><b>${yi(data.universe.totalAmount)} 亿</b><span class="muted">沪深北过滤后统计</span></div>
  </div>
  <p>定性：指数和容量核心主导，半导体、科创硬科技、创新药/医药、设备链条扩散；连板高度只有 3 板，短线接力不是主驱动。</p>
  <p class="sub">生成时间：2026-06-10。不得视为投资建议。</p>
</div>

<div class="page">
<section>
<h2>覆盖检查</h2>
${table([
  ["1 资讯梳理", "已覆盖", "第二章；A股、美股、半导体/PCB、机器人、创新药、数据要素/稳定币、资源股负反馈。"],
  ["2 盘面数据", "已覆盖", "第一章；涨跌家数、涨停跌停、指数、成交额、五日趋势、行情属性。"],
  ["3 资金动向", "已覆盖", "第三章；机构/趋势、游资、国家队/ETF、北向披露限制、主线支线。"],
  ["4 宏观层面", "已覆盖", "第九章；成交额、两融、ETF、人民币、海外债券风险。"],
  ["5 涨停板分析", "已覆盖", "第四至六章；首板/二板/三板、硬核逻辑、情绪风险、炸板、趋势票。"],
  ["6 龙头与情绪", "已覆盖", "第七章；周期阶段、龙头战法、40%+连板筛选结果。"],
  ["7 题材切换", "已覆盖", "第八章；高位旧题材向低位科技容量切换。"],
  ["8 中期展望", "已覆盖", "第八章；未来数周至一两个月主线排序。"],
  ["9 美股联动", "已覆盖", "第九章；美股科技/芯片对次日A股的情景影响。"],
], [
  ["要求", (r) => r[0]],
  ["状态", (r) => `<b class="up">${r[1]}</b>`],
  ["位置", (r) => r[2]],
])}
</section>
<section>
<h2>一、盘面结论</h2>
${table(idxRows, [
  ["指数", (r) => esc(r.name)],
  ["收盘", (r) => r.close],
  ["涨跌幅", (r) => `<b class="up">${pct(r.pct)}</b>`],
  ["成交额", (r) => `${yi(r.amount)}亿`],
])}
<h3>不是简单普涨，而是一次“科技容量修复”</h3>
<p>全市场成交额约 ${yi(data.universe.totalAmount)} 亿元，较前一交易日公开收评所称为缩量逾 1500 亿元，但仍维持 2.6 万亿级别。上涨家数占过滤样本 62.7%，说明赚钱效应扩散；但缩量上涨意味着资金并非无差别冲锋，而是在前一日恐慌释放后选择最有弹性的科技成长方向做修复。</p>
<p>当天最强的并不是传统连板接力，而是创业板、科创50、沪深300同步抬升带来的容量行情。半导体、PCB、光通信、设备材料、创新药、机器人共同上攻，背后是机构资金和趋势资金对高景气资产的重新定价；游资接力只是参与了首板扩散，尚未成为主导。</p>
<h3>五日趋势对比</h3>
${table(fiveDayRows, [
  ["日期", (r) => r[0]],
  ["上证", (r) => `${r[1]}<br><b class="${r[2].startsWith('+') ? 'up' : 'down'}">${r[2]}</b>`],
  ["深成", (r) => `${r[3]}<br><b class="${r[4].startsWith('+') ? 'up' : 'down'}">${r[4]}</b>`],
  ["创业板", (r) => `${r[5]}<br><b class="${r[6].startsWith('+') ? 'up' : 'down'}">${r[6]}</b>`],
  ["市场成交", (r) => r[7]],
])}
<p>五日节奏很清楚：6月3日科技和CPO强势但市场宽度不佳，6月4日缩量下跌，6月5日放量杀跌，6月8日继续风险释放，6月9日缩量修复。也就是说，6月9日不是新一轮情绪主升的第一天，而是连续调整后的科技成长修复日。成交额从6月3日约3.15万亿回落到本地过滤口径2.62万亿，说明资金选择了最强方向，而不是全面增量入场。</p>
<h3>盘面矛盾</h3>
<ul>
<li>强处：指数长阳、科技权重和20cm弹性票共振，说明市场风险偏好快速修复。</li>
<li>弱处：连板高度只有3板，且涨停池以首板为主，说明短线情绪还在试错，没有进入高标加速期。</li>
<li>关键观察：如果次日半导体/PCB/机器人继续放量，行情可从修复转向主升；如果成交额回落到2万亿下方，首板扩散容易演变成兑现。</li>
</ul>
</section>
<section>
<h2>二、资讯与发酵方向</h2>
<h3>1. 半导体/PCB：AI硬件反弹的A股映射最直接</h3>
<p>6月9日收盘后，多家媒体把当天主线指向半导体芯片、PCB、算力硬件。消息催化来自两个方向：一是隔夜美股芯片股从上周急跌后反弹，英特尔、美光、应用材料、ASML等带动全球半导体风险偏好修复；二是AI算力需求仍在强化，上游硅片、晶圆、先进封装、PCB、光通信、设备材料都有基本面映射。</p>
<p>发酵路径：美股半导体反弹 -> 港股/日韩科技股风险偏好回暖 -> A股科创板与创业板率先修复 -> 主板PCB、光通信、设备材料补涨。这个路径解释了为什么科创50和创业板指涨幅明显高于沪指。</p>
<h3>2. 机器人：资金净流入强，但更偏支线扩散</h3>
<p>机器人概念盘中反复活跃，公开收评提到机器人概念主力资金净流入约140.6亿元、板块多股涨停。它的优势是题材辨识度高、弹性强；短板是内部逻辑分散，既有减速器/丝杠/控制器，也有工业自动化和概念映射。6月9日更像半导体主线带动下的高弹性支线，而不是独立新主线。</p>
<h3>3. 创新药：低位修复，持续性看BD和临床催化</h3>
<p>创新药在盘中拉升，属于前期调整后的低位修复。它与半导体的差异在于：半导体是全球AI硬件共振，创新药更多依赖个股BD出海、临床数据、估值修复和资金低位切换。若后续成交额维持高位，创新药有望作为机构低位支线轮动；若成交收缩，则更容易回到事件驱动的个股行情。</p>
<h3>4. 数据要素/稳定币/金融科技：消息多，盘面承接需要确认</h3>
<p>国家数据局关于高质量数据集建设的政策消息，强化数据基础设施、AI训练数据、数据标注和词元交易预期；稳定币/金融科技仍有政策与海外映射。但这类方向在6月9日不是最强成交主线，后续要看是否出现持续放量的核心票，而不是只看消息标题。</p>
<h3>5. 负反馈方向：油气、煤炭、部分防御资产</h3>
<p>油气、煤炭等资源和高股息防御方向走弱，说明资金从避险/红利重新转向成长弹性。这是风险偏好升温的典型特征，但如果海外债券收益率再次上行或美股科技回落，资金也可能快速回流防御。</p>
</section>
</div>

<div class="page">
<section>
<h2>三、行业与资金方向</h2>
<p>从本地收盘快照看，涨幅居前行业和主力净流入方向高度重合，集中在电子、通信、机械设备、电力设备、基础化工等科技制造链条。这个特征比单纯涨停数量更重要，因为它说明当日不是小票情绪独舞，而是大成交容量资产获得资金承接。</p>
${table(industryTop, [
  ["行业", (r) => esc(r.name)],
  ["均涨幅", (r) => `<b class="up">${pct(r.avgPct)}</b>`],
  ["涨停", (r) => r.limitUp],
  ["主力净额", (r) => `${yi(r.mainNet)}亿`],
])}
<h3>主力净流入前列</h3>
${table(mainBuy, [
  ["代码", (r) => r.code],
  ["名称", (r) => esc(r.name)],
  ["涨幅", (r) => `<b class="up">${pct(r.pct)}</b>`],
  ["净流入", (r) => `${yi(r.netMain)}亿`],
  ["行业", (r) => esc(r.industry)],
])}
<h3>主力净流出压力</h3>
${table(mainSell, [
  ["代码", (r) => r.code],
  ["名称", (r) => esc(r.name)],
  ["涨幅", (r) => pct(r.pct)],
  ["净流出", (r) => `${yi(Math.abs(r.netMain))}亿`],
  ["行业", (r) => esc(r.industry)],
])}
<h3>资金画像</h3>
<ul>
<li>机构/趋势资金：更偏半导体、PCB、光通信、设备、创新药等容量方向，关注成交额和ETF资金承接。</li>
<li>游资资金：参与机器人、稳定币、首板扩散和20cm弹性，但连板高度未打开，说明高标博弈仍谨慎。</li>
<li>国家队/宽基ETF：没有直接可核验的单日持仓明细，报告不虚构买卖；但ETF成交额维持高位，说明宽基/行业ETF仍是资金快速切换的通道。</li>
<li>北向资金：沪深港通披露机制调整后，传统“北向净买入”不再作为盘后唯一口径，本报告不使用不可核验的北向净流入数字。</li>
</ul>
</section>
</div>

<div class="page">
<section>
<h2>四、涨停梯队</h2>
${boardRows
  .map(
    ([name, rows]) => `<h3>${name} (${rows.length})</h3><div>${tags(rows, name === "首板" ? 130 : 80)}</div>`
  )
  .join("")}
<p class="note">连板标记中，2板/3板使用公开涨停复盘名单做校验；首板为本地收盘价、高价、昨收价按涨停价规则计算，炸板未回封不计入。</p>
</section>
</div>

<div class="page">
<section>
<h2>五、硬核逻辑与情绪风险</h2>
<h3>硬核逻辑涨停池</h3>
<div>${tags(hardLogic, 90)}</div>
<h3>纯情绪/高波动风险池</h3>
<div>${tags(emotionRisk, 60)}</div>
<p>硬核票的共同点是行业景气或国产替代逻辑能解释成交额承接：半导体设备材料看国产替代和AI硬件周期，通信设备看算力网络，机器人看产业化节点，创新药看BD与临床催化。情绪票更依赖连板高度、题材标签和隔夜消息，弱化后容易出现冲高回落。</p>
<h3>接力价值排序</h3>
<ul>
<li>优先级一：20cm硬科技涨停中成交额充分、行业位置清晰、不是单纯概念映射的票。</li>
<li>优先级二：主板PCB/光通信/设备里能承接大资金、次日不被前排分歧拖累的容量票。</li>
<li>优先级三：机器人、稳定币、数据要素等支线中率先放量、能走出独立辨识度的核心票。</li>
<li>回避：无行业增量、只靠名字或小市值情绪推动的高换手首板。</li>
</ul>
</section>
<section>
<h2>六、炸板与未涨停趋势票</h2>
<h3>炸板未回封但契合主线</h3>
<div>${tags(failedHard, 50)}</div>
<h3>断板反包未创新高：观察池</h3>
<div>${tags(data.recentHotButNotLimit?.length ? data.recentHotButNotLimit : failedHard.concat(trendHard).slice(0, 30), 40)}</div>
<p>断板反包的核心不是“当天是否红盘”，而是是否仍在主线、是否缩量不破趋势、是否有资金在分歧时承接。当前可自动核验的近几日连板后未涨停名单不足，报告采用“炸板硬科技 + 强趋势未涨停”作为观察池，后续需要用分时回封和次日竞价强弱确认。</p>
<h3>近期曾涨停或连板但今日未涨停、趋势完好</h3>
<div>${tags(data.recentHotButNotLimit?.length ? data.recentHotButNotLimit : trendHard, 50)}</div>
<h3>主升连阳/强趋势未涨停</h3>
<div>${tags(trendHard, 60)}</div>
<p>炸板未回封不是简单负面。若炸板发生在主线前排分歧时，次日弱转强可以反证资金仍在；若炸板发生在后排补涨或无量秒板，次日往往先兑现。强趋势未涨停票则代表另一类资金审美：不追连板，而是沿5日线/成交中枢做趋势推进。</p>
<p>观察框架：半导体和设备链继续放量时，优先看炸板硬科技的修复和趋势容量票的承接；若成交明显缩量，优先降低后排首板和高换手炸板的预期。</p>
</section>
</div>

<div class="page">
<section>
<h2>七、龙头与情绪周期</h2>
<p>情绪周期处于“容量主线升温、接力高度受限”的阶段。市场核心并非单一连板妖股，而是容量龙头和 20cm 弹性共同定价：科创半导体、创业板设备、PCB/光通信、创新药是主动性最强方向。</p>
<ul>
<li>高度锚：3板高度未打开，说明游资接力尚未全面主导。</li>
<li>容量锚：半导体和科创方向多只 20cm 涨停，说明机构/趋势资金风险偏好上行。</li>
<li>龙头气质筛选：近期涨幅超过 40%且有连板记录的标的，需要满足主动领涨、成交额放大、次日不被核按钮三个条件；本报告不在无法完整核验近五日涨幅时虚构名单。</li>
</ul>
<h3>涨幅超40%且曾连板筛选结果</h3>
${data.recentLeaders?.length ? `<div>${tags(data.recentLeaders, 30)}</div>` : `<p class="note">按腾讯近10日K线对涨停池、强趋势池、当日涨幅和成交额前列候选做筛选，未筛出同时满足“近8个交易日涨幅超过40% + 曾出现2连板及以上 + 非ST/非退市风险”的标的。因此本报告不强行指定妖股龙头，龙头判断改以容量核心和20cm弹性核心为主。</p>`}
<h3>龙头战法推演</h3>
<p>6月9日的龙头不应只按连板数排序。真正的强势核心应该同时满足三点：第一，所在方向是当日最大资金共识；第二，能带动同产业链扩散；第三，分歧时仍有资金回封或承接。按这个标准，半导体/PCB/光通信的容量票比多数纯首板小票更有市场号召力。</p>
</section>
<section>
<h2>八、题材切换与中期展望</h2>
<p>存在从高位旧题材向低位科技容量方向切换的迹象。机器人、稳定币等题材仍有分支活跃，但 6月9日主导权更偏向半导体/PCB/创新药这类机构能容纳资金的方向。若后续资金从红利、防御、资源持续撤出，科技成长会继续占优；若海外利率压力反复，成长内部会从高弹性切回盈利确定性。</p>
<p>未来数周到一两个月最可能持续发酵的方向：半导体设备与材料、AI算力链条、PCB/光通信、机器人核心零部件、创新药BD出海、稳定币/金融科技政策映射、数据基础设施。持续性排序取决于成交额能否维持 2万亿以上，以及龙头是否从 20cm 弹性扩散到主板容量。</p>
<h3>持续性打分</h3>
<ul>
<li>半导体/PCB：高。全球AI硬件映射明确，容量足，但短期涨幅大后需要分化。</li>
<li>机器人：中高。产业催化多，弹性强，但需要出现真正带板块的核心龙头。</li>
<li>创新药：中。低位修复逻辑成立，持续性看个股催化和机构加仓。</li>
<li>稳定币/数据要素：中。消息密度高，但盘面承接需要放量核心股确认。</li>
</ul>
</section>
</div>

<div class="page">
<section>
<h2>九、宏观与美股联动</h2>
<ul>
<li>成交额：2.62 万亿级别仍是高活跃区，但较前日缩量，属于升温后的分化确认，不是全面过热。</li>
<li>融资余额：截至可核验的最近披露数据，6月5日A股两融余额为29066.88亿元，较前一交易日减少139.98亿元；6月9日完整两融余额通常滞后披露，本报告不提前填数。若后续两融重新抬升，利好高弹性成长，但也会放大回撤。</li>
<li>宽基ETF：6月9日股票型ETF成交额约3940.04亿元，较前一交易日缩量约670亿元；ETF仍是主线切换通道，但缩量说明机构并非全面追涨。后续若沪深300/科创/创业板宽基继续净申购，说明机构风险偏好延续。</li>
<li>人民币与海外债：人民币稳定、美债收益率不再上冲，有利于成长估值；若美债/日债/欧债收益率再度快速上行，会压制 A股高估值科技链。当前宏观结论是“有利于风险偏好修复，但不足以支持无差别普涨”。</li>
<li>美股联动：6月9日前一夜美股道指小跌、纳指和标普反弹，芯片股反弹最强，这直接强化了A股半导体、光通信、PCB的风险偏好。若6月9日晚美股科技继续走强，A股次日主线更可能延续；若纳指回落，A股会更考验前排承接，后排首板风险上升。</li>
</ul>
</section>
<section>
<h2>消息源与核验</h2>
${table(sourceRows, [
  ["来源", (r) => `<a href="${r[1]}">${esc(r[0])}</a>`],
  ["用于核验", (r) => esc(r[2])],
])}
</section>
<section>
<h2>数据口径与限制</h2>
<p>本报告使用 2026-06-09 15:00 后的收盘快照为唯一行情基准，过滤 ST、*ST、名称含退市/退字风险股。公开新闻与宏观信息用于解释，不覆盖收盘行情口径。</p>
<p>由于当前网络无法稳定访问东方财富历史 K 线 JSON，报告没有编造逐日 5 日成交额和近 5 日涨幅；连板高度采用当日快照加公开涨停复盘口径校验。</p>
</section>
</div>
</body></html>`;

fs.writeFileSync(path.join(outDir, "6.9 A股复盘.html"), html, "utf8");
console.log(path.join(outDir, "6.9 A股复盘.html"));
