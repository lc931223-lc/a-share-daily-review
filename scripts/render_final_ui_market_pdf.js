const fs = require('fs');
const PDFLib = require('./pdf-lib.min.js');
const fontkit = require('./fontkit.umd.min.js');

const { PDFDocument, rgb } = PDFLib;

const output = process.argv[2];

function splitWords(text) {
  const out = [];
  let buf = '';
  for (const ch of text) {
    if (/[A-Za-z0-9._:%+\-\/()]/.test(ch)) buf += ch;
    else {
      if (buf) out.push(buf), (buf = '');
      out.push(ch);
    }
  }
  if (buf) out.push(buf);
  return out;
}

function wrapText(text, font, size, maxWidth) {
  const tokens = splitWords(String(text));
  const lines = [];
  let line = '';
  for (const token of tokens) {
    const next = line + token;
    if (!line || font.widthOfTextAtSize(next, size) <= maxWidth) line = next;
    else {
      lines.push(line);
      line = token.trimStart();
    }
  }
  if (line) lines.push(line);
  return lines;
}

function stripMd(s) {
  return String(s).replace(/\*\*/g, '');
}

async function main() {
  const pdfDoc = await PDFDocument.create();
  pdfDoc.registerFontkit(fontkit);
  const font = await pdfDoc.embedFont(fs.readFileSync('C:\\Windows\\Fonts\\STSONG.TTF'), { subset: true });

  const W = 595.28;
  const H = 841.89;
  const M = 40;
  const contentW = W - M * 2;
  let page = pdfDoc.addPage([W, H]);
  let y = H - 36;
  let pageNo = 1;

  const black = rgb(0, 0, 0);
  const navy = black;
  const blue = black;
  const lightBlue = rgb(0.91, 0.95, 0.99);
  const green = black;
  const lightGreen = rgb(0.92, 0.98, 0.95);
  const amber = black;
  const lightAmber = rgb(1, 0.97, 0.88);
  const red = black;
  const lightRed = rgb(1, 0.94, 0.92);
  const text = black;
  const muted = black;
  const border = rgb(0.82, 0.86, 0.91);

  function footer() {
    const s = `第 ${pageNo} 页`;
    page.drawText(s, { x: W - M - font.widthOfTextAtSize(s, 9), y: 20, size: 9, font, color: black });
  }

  function newPage() {
    footer();
    page = pdfDoc.addPage([W, H]);
    pageNo += 1;
    y = H - 36;
  }

  function ensure(h) {
    if (y - h < 42) newPage();
  }

  function drawLines(lines, x, startY, size, color, maxWidth, lineGap = 5) {
    let cy = startY;
    for (const raw of lines) {
      for (const ln of wrapText(stripMd(raw), font, size, maxWidth)) {
        page.drawText(ln, { x, y: cy, size, font, color });
        cy -= size + lineGap;
      }
    }
    return cy;
  }

  function title() {
    page.drawRectangle({ x: 0, y: H - 112, width: W, height: 112, color: navy });
    page.drawRectangle({ x: 0, y: H - 116, width: W, height: 4, color: rgb(0.24, 0.62, 0.95) });
    page.drawText('2026-05-27 A股市场分析', { x: M, y: H - 50, size: 24, font, color: black });
    page.drawText('以及 2026-05-28 盘前预测', { x: M, y: H - 80, size: 17, font, color: black });
    page.drawText('生成日期：2026-05-28｜视角：5月27日收盘后｜覆盖：大盘、板块、成交、涨跌停、日内演化', {
      x: M,
      y: H - 101,
      size: 9.2,
      font,
      color: black,
    });
    y = H - 142;
  }

  function section(name) {
    ensure(34);
    y -= 4;
    page.drawRectangle({ x: M, y: y - 4, width: 5, height: 20, color: blue });
    page.drawText(name, { x: M + 12, y, size: 16, font, color: navy });
    y -= 28;
  }

  function card(lines, options = {}) {
    const bg = options.bg || lightBlue;
    const accent = options.accent || blue;
    const size = options.size || 12.2;
    const wrapped = [];
    for (const line of lines) wrapped.push(...wrapText(stripMd(line), font, size, contentW - 28));
    const h = wrapped.length * (size + 5) + 26;
    ensure(h + 8);
    page.drawRectangle({ x: M, y: y - h + 4, width: contentW, height: h, color: bg, borderColor: border, borderWidth: 0.6 });
    page.drawRectangle({ x: M, y: y - h + 4, width: 5, height: h, color: accent });
    let cy = y - 16;
    for (const line of wrapped) {
      page.drawText(line, { x: M + 16, y: cy, size, font, color: text });
      cy -= size + 5;
    }
    y -= h + 10;
  }

  function bullets(items) {
    const rows = [];
    for (const item of items) rows.push(...wrapText('• ' + stripMd(item), font, 12.0, contentW - 8));
    const h = rows.length * 17.2 + 8;
    ensure(h);
    let cy = y;
    for (const row of rows) {
      page.drawText(row, { x: M + 4, y: cy, size: 12.0, font, color: text });
      cy -= 17.2;
    }
    y = cy - 8;
  }

  function table(headers, rows, widths) {
    const x0 = M;
    const colW = widths.map((w) => w * contentW);
    const headerH = 28;
    const rowPad = 8;
    const fontSize = 10.5;

    function drawRow(cells, isHeader) {
      const wrapped = cells.map((cell, i) => wrapText(stripMd(cell), font, isHeader ? 10.6 : fontSize, colW[i] - rowPad * 2));
      const maxLines = Math.max(...wrapped.map((v) => v.length));
      const h = Math.max(isHeader ? 31 : 30, maxLines * (fontSize + 4) + rowPad * 2);
      ensure(h + 2);
      let x = x0;
      for (let i = 0; i < cells.length; i++) {
        page.drawRectangle({
          x,
          y: y - h,
          width: colW[i],
          height: h,
          color: isHeader ? rgb(0.90, 0.93, 0.97) : rgb(1, 1, 1),
          borderColor: border,
          borderWidth: 0.6,
        });
        let cy = y - rowPad - (isHeader ? 10.5 : 10.2);
        for (const line of wrapped[i]) {
          page.drawText(line, { x: x + rowPad, y: cy, size: isHeader ? 10.6 : fontSize, font, color: isHeader ? navy : text });
          cy -= fontSize + 4;
        }
        x += colW[i];
      }
      y -= h;
    }

    drawRow(headers, true);
    for (const row of rows) drawRow(row, false);
    y -= 10;
  }

  title();

  card([
    '核心结论：5月27日不是单纯指数回调，而是近5日科技主线高成交、高拥挤后的第二次压力测试。成交额仍在3.2万亿元以上，说明流动性没有消失；但约4500股下跌、科创50大跌，说明赚钱效应和市场宽度明显恶化。',
    '5月28日更大概率是“指数弱修复 + 主线强分化”。关键不在沪指是否短暂翻红，而在科创50能否止跌、上涨家数能否恢复、AI硬件底座分支能否接力高位半导体。',
  ], { bg: lightBlue, accent: blue, size: 12.3 });

  section('一、5月27日大盘状态');
  table(
    ['项目', '表现', '结论'],
    [
      ['上证指数', '4093.73点，-1.25%', '跌破4100点，主板风险偏好转弱。'],
      ['深证成指', '15736.47点，-0.88%', '成长方向冲高回落，结构压力大于指数跌幅。'],
      ['创业板指', '4045.77点，+0.07%', '新能源和部分权重支撑，但并不代表个股情绪好。'],
      ['科创50', '-2.80%', '高位科技集中承压，是当天最重要的风险信号。'],
      ['成交额', '沪深两市约3.24万亿元，较前日基本持平或小幅缩量。', '资金仍活跃，问题不是流动性退潮，而是高位方向承接变差。'],
      ['市场宽度', '约4500股下跌，上涨家数约千家以内。', '亏钱效应明显扩散，不能只看指数和成交额。'],
      ['涨跌停', '公开复盘口径约47股涨停、21股炸板，封板率约69%。', '短线仍有局部活跃，但接力强度较5月22日至25日明显下降。'],
    ],
    [0.18, 0.34, 0.48],
  );

  section('二、近5日结构背景');
  bullets([
    '5月21日市场放量大跌，沪深北成交约3.51万亿元、近4800股下跌，是第一轮高位科技压力测试。',
    '5月22日至25日硬科技强修复，PCB、MLCC、CPO、存储、先进封装、半导体等方向带动市场恢复进攻。',
    '5月25日已出现指数强、个股跌多的背离；5月26日至27日，背离扩大为超4000股下跌、近4500股下跌。',
    '近5日不是系统性退潮，而是主线从“泛科技全面扩散”转向“少数确定性分支筛选”。成交额还在，说明市场仍有资金；宽度转弱，说明资金容错率下降。',
  ]);

  section('三、5月27日日内演化');
  table(
    ['阶段', '盘面线索', '交易含义'],
    [
      [
        '盘前背景',
        '海外存储和AI硬件情绪集中升温：美股存储龙头大涨、韩国存储链走强，AI服务器内存/HBM成本占比提升，强化“存储短缺 + AI算力硬件景气”的预期。',
        'A股存储、先进封装、AI硬件早盘高开有外部映射基础，但外盘强不等于A股一定能持续，核心看本土承接和成交质量。',
      ],
      [
        '早盘 09:30-11:30',
        '存储芯片、AI短剧出海、光通信新股、光伏反内卷、SiC、电力、储能、先进封装、AIDC电源设备、创新药、工业气体等多线轮动。',
        '资金仍在围绕“AI产业链 + 高景气事件”交易，但方向明显增多，说明主线开始从集中进攻转向轮动试错。',
      ],
      [
        '午后 13:00-15:00',
        '白酒、零售等低位方向逆势拉升；高位半导体设备继续调整；超级电容等算力配套分支走强。',
        '资金从高位科技撤出后，并未完全离场，而是在低位消费、防御资产和AI底座细分中寻找新承接。',
      ],
      [
        '尾盘含义',
        '指数跌幅扩大、个股下跌家数维持高位，科创50承压。',
        'AI主线未结束，但泛科技追涨失效；下一阶段重点看先进封装、AIDC电源、超级电容、存储链能否形成新接力。',
      ],
    ],
    [0.18, 0.42, 0.40],
  );

  section('四、板块结论');
  table(
    ['方向', '5月27日表现', '判断'],
    [
      ['存储/半导体', '受海外存储景气和AI服务器内存成本提升预期带动，早盘高开活跃，但随后明显分化。', '中期逻辑仍强，短线需要从“情绪映射”切换到“本土订单、业绩、供应链证据”。'],
      ['先进封装/AI硬件底座', '相对更有承接，部分标的延续强势。', '优先级高于泛半导体，属于AI主线内部资金迁移方向。'],
      ['AIDC电源/超级电容', '午后和尾盘资金挖掘明显，体现算力配套从芯片向供电、储能、基础设施扩散。', '可能成为新的细分接力方向，但需要5月28日验证持续性。'],
      ['电力/煤炭/高股息', '逆势走强，部分电力股涨停扩散。', '兼具防御和算力供给逻辑，指数弱时有承接价值。'],
      ['白酒/零售', '午后明显拉升，低位消费修复。', '更像资金从高位科技撤出后的低位再平衡，不宜直接判断为消费主线反转。'],
      ['机器人', '部分高位题材调整明显。', '短线降权，题材拥挤和业绩兑现压力开始显现。'],
    ],
    [0.22, 0.39, 0.39],
  );

  section('五、5月27日的真正含义');
  card([
    '不是流动性问题：成交额仍高，资金并未大规模离场。',
    '是结构问题：高位科技承接下降，低位防御和AI底座细分开始接力。',
    '是宽度问题：指数跌幅有限，但下跌家数过多，持仓体验明显变差。',
    '是节奏问题：5月22日至25日硬科技修复过快，5月26日至27日进入消化阶段。',
  ], { bg: lightAmber, accent: amber });

  section('六、5月28日预测');
  table(
    ['情景', '概率', '触发条件', '市场表现'],
    [
      [
        '基准：弱修复，强分化',
        '55%',
        '沪指围绕4070-4130震荡，成交额维持3万亿元附近；科创50止跌但不强反包。',
        '先进封装、AIDC电源、超级电容、电力等分支轮动；高位半导体继续分化；白酒/消费保持低位修复属性。',
      ],
      [
        '偏强：科技承接修复',
        '20%',
        '科创50放量止跌，上涨家数恢复至2500家以上，存储/先进封装不再高开低走。',
        '市场从防御切回进攻，AI硬件和半导体重新扩散，指数有望重新站上4100点并稳住。',
      ],
      [
        '偏弱：高位科技继续去拥挤',
        '25%',
        '科创50继续领跌，沪指反抽不过4100点，上涨家数继续低于1500家。',
        '资金继续流向高股息、电力、煤炭、白酒等防御方向；科技只剩低位补涨，亏钱效应扩大。',
      ],
    ],
    [0.24, 0.11, 0.33, 0.32],
  );

  section('七、5月28日观察指标');
  table(
    ['指标', '强势确认', '弱势确认'],
    [
      ['沪指4100点', '早盘站回并维持，尾盘不回落。', '反抽不过4100，午后继续走低。'],
      ['科创50', '止跌或放量修复，半导体高成交股不再破位。', '继续领跌，说明高位科技仍在去拥挤。'],
      ['市场宽度', '上涨家数恢复至2500家以上。', '上涨家数继续低于1500家。'],
      ['成交额', '3万亿元以上且上涨家数同步改善。', '放量下跌或缩量反抽。'],
      ['涨停/炸板', '涨停数量回升、炸板率下降、连板晋级改善。', '涨停数量低位、炸板率上升、首板接力失败。'],
      ['主线承接', '先进封装、AIDC电源、超级电容、存储链出现扩散。', '只有少数大票硬撑，板块没有跟随。'],
    ],
    [0.22, 0.39, 0.39],
  );

  section('八、最终结论');
  card([
    '5月27日可以概括为：成交额没有坏，但市场宽度坏了；AI产业链没有结束，但泛科技追涨失效；指数没有系统性破位，但高位科技正在消化拥挤。',
    '对5月28日，最合理的判断是弱修复和强分化。若科创50止跌、上涨家数修复、AI硬件底座继续扩散，则市场有机会从防御切回结构性进攻；若高位科技继续放量下跌，则短线仍应按防御和低位轮动处理。',
  ], { bg: lightGreen, accent: green, size: 12.2 });

  section('风险提示');
  card([
    '本报告为公开信息和用户提供资料的研究整理，不构成投资建议。涨跌停统计不同数据源存在口径差异，报告仅用于市场情绪判断。短线行情受政策、海外市场、成交结构、量化交易、监管公告和突发事件影响较大。',
  ], { bg: lightRed, accent: red, size: 11.6 });

  footer();
  const bytes = await pdfDoc.save();
  fs.writeFileSync(output, bytes);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
