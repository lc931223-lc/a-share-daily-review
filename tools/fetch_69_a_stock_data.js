const fs = require("fs");
const path = require("path");
const cp = require("child_process");

const OUT_DIR = path.resolve("output/69-review");
fs.mkdirSync(OUT_DIR, { recursive: true });

const UA =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36";

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function getJson(url) {
  let lastErr;
  for (let i = 0; i < 5; i += 1) {
    try {
      const tmp = path.join(OUT_DIR, `curl_${Date.now()}_${Math.random().toString(16).slice(2)}.json`);
      cp.execFileSync("curl.exe", ["-k", "--ssl-no-revoke", "-L", "--compressed", "--retry", "2", "-A", UA, "-o", tmp, url], {
        maxBuffer: 64 * 1024 * 1024,
        stdio: ["ignore", "ignore", "ignore"],
      });
      const text = fs.readFileSync(tmp, "utf8");
      fs.rmSync(tmp, { force: true });
      return JSON.parse(text.replace(/^[^(]*\((.*)\);?$/s, "$1"));
    } catch (err) {
      lastErr = err;
      await sleep(500 + i * 700);
    }
  }
  throw lastErr;
}

function round2(n) {
  return Math.round((Number(n) + Number.EPSILON) * 100) / 100;
}

function marketOf(code) {
  if (code.startsWith("6") || code.startsWith("9")) return "SH";
  if (code.startsWith("8") || code.startsWith("4")) return "BJ";
  return "SZ";
}

function isListedAShareCode(row) {
  const code = String(row.f12 || row.code || "");
  const industry = row.f100 || row.industry || "";
  if (/^(600|601|603|605|688|000|001|002|003|300|301)\d{3}$/.test(code)) return true;
  if (/^[48]\d{5}$/.test(code)) return industry && industry !== "-" && Math.abs(Number(row.f3 ?? row.pct)) <= 30.5;
  return false;
}

function secid(code) {
  return `${marketOf(code) === "SH" ? 1 : 0}.${code}`;
}

function limitRate(code, name) {
  if (/ST|\*ST|\u9000/.test(name)) return 0.05;
  if (code.startsWith("300") || code.startsWith("301") || code.startsWith("688")) return 0.2;
  if (code.startsWith("8") || code.startsWith("4")) return 0.3;
  return 0.1;
}

function isRiskName(name) {
  return /(^|\s|\*)ST|\u9000\u5e02|\u9000\b|\u9000\(|\*ST|S\*ST/i.test(name);
}

function isLimitUp(stock) {
  if (Math.abs(stock.pct) > 35) return false;
  if (!stock.close || !stock.preclose) return false;
  const up = round2(stock.preclose * (1 + limitRate(stock.code, stock.name)));
  return stock.close >= up - 0.01 && stock.high >= up - 0.01;
}

function isLimitDown(stock) {
  if (Math.abs(stock.pct) > 35) return false;
  if (!stock.close || !stock.preclose) return false;
  const down = round2(stock.preclose * (1 - limitRate(stock.code, stock.name)));
  return stock.close <= down + 0.01 && stock.low <= down + 0.01;
}

function isFailedLimitUp(stock) {
  if (Math.abs(stock.pct) > 35) return false;
  if (!stock.close || !stock.preclose) return false;
  const up = round2(stock.preclose * (1 + limitRate(stock.code, stock.name)));
  return stock.high >= up - 0.01 && stock.close < up - 0.01;
}

async function fetchAllStocks() {
  const fields = [
    "f2",
    "f3",
    "f4",
    "f5",
    "f6",
    "f7",
    "f8",
    "f9",
    "f10",
    "f12",
    "f13",
    "f14",
    "f15",
    "f16",
    "f17",
    "f18",
    "f20",
    "f21",
    "f23",
    "f24",
    "f25",
    "f62",
    "f100",
    "f115",
  ].join(",");
  const fsParam = "m:0+t:6,m:0+t:80,m:0+t:81,m:0+t:83,m:1+t:2,m:1+t:23";
  let page = 1;
  const pz = 50;
  const rows = [];
  while (true) {
    const url =
      "https://push2delay.eastmoney.com/api/qt/clist/get?" +
      new URLSearchParams({
        pn: String(page),
        pz: String(pz),
        po: "1",
        np: "1",
        fltt: "2",
        invt: "2",
        fid: "f3",
        fs: fsParam,
        fields,
      }).toString();
    const json = await getJson(url);
    const list = json.data?.diff || [];
    rows.push(...list);
    if (rows.length >= (json.data?.total || 0) || list.length === 0) break;
    page += 1;
    await sleep(120);
  }
  return rows.map((r) => ({
    code: String(r.f12),
    name: r.f14,
    market: marketOf(String(r.f12)),
    close: Number(r.f2),
    pct: Number(r.f3),
    change: Number(r.f4),
    volume: Number(r.f5),
    amount: Number(r.f6),
    amplitude: Number(r.f7),
    turnover: Number(r.f8),
    pe: Number(r.f9),
    pb: Number(r.f23),
    high: Number(r.f15),
    low: Number(r.f16),
    open: Number(r.f17),
    preclose: Number(r.f18),
    totalMcap: Number(r.f20),
    floatMcap: Number(r.f21),
    netMain: Number(r.f62),
    industry: r.f100 || "",
    peTtm: Number(r.f115),
    riskExcluded: isRiskName(r.f14 || ""),
  }));
}

async function fetchIndex(code, market) {
  const id = `${market}.${code}`;
  const quoteUrl =
    "https://push2delay.eastmoney.com/api/qt/stock/get?" +
    new URLSearchParams({
      fltt: "2",
      invt: "2",
      fields: "f57,f58,f43,f44,f45,f46,f47,f48,f60,f170,f171,f168",
      secid: id,
    }).toString();
  const q = (await getJson(quoteUrl)).data || {};
  return {
    code,
    name: q.f58,
    close: Number(q.f43),
    high: Number(q.f44),
    low: Number(q.f45),
    open: Number(q.f46),
    preclose: Number(q.f60),
    pct: Number(q.f170),
    amount: Number(q.f48),
    amplitude: Number(q.f171),
    turnover: Number(q.f168),
    kline: [],
  };
}

async function fetchStockKline(stock, lmt = 12) {
  const url =
    "http://push2his.eastmoney.com/api/qt/stock/kline/get?" +
    new URLSearchParams({
      secid: secid(stock.code),
      klt: "101",
      fqt: "1",
      lmt: String(lmt),
      end: "20260609",
      fields1: "f1,f2,f3,f4,f5",
      fields2: "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
    }).toString();
  const rows = ((await getJson(url)).data?.klines || []).map((line) => {
    const p = line.split(",");
    return {
      date: p[0],
      open: Number(p[1]),
      close: Number(p[2]),
      high: Number(p[3]),
      low: Number(p[4]),
      volume: Number(p[5]),
      amount: Number(p[6]),
      amplitude: Number(p[7]),
      pct: Number(p[8]),
      change: Number(p[9]),
      turnover: Number(p[10]),
    };
  });
  return rows;
}

function klineLimitUp(row, prevClose, stock) {
  if (!prevClose) return false;
  const up = round2(prevClose * (1 + limitRate(stock.code, stock.name)));
  return row.close >= up - 0.01 && row.high >= up - 0.01;
}

function consecutiveBoards(kline, stock) {
  let count = 0;
  for (let i = kline.length - 1; i >= 1; i--) {
    if (klineLimitUp(kline[i], kline[i - 1].close, stock)) count += 1;
    else break;
  }
  return count;
}

function fiveDayLimitCount(kline, stock) {
  let count = 0;
  for (let i = Math.max(1, kline.length - 5); i < kline.length; i++) {
    if (klineLimitUp(kline[i], kline[i - 1].close, stock)) count += 1;
  }
  return count;
}

function groupBy(arr, key) {
  const m = new Map();
  for (const x of arr) {
    const k = key(x) || "未分类";
    if (!m.has(k)) m.set(k, []);
    m.get(k).push(x);
  }
  return [...m.entries()].map(([name, rows]) => ({ name, rows }));
}

async function main() {
  const allRaw = await fetchAllStocks();
  const all = allRaw.filter((s) => Number.isFinite(s.close) && s.close > 0 && isListedAShareCode(s));
  const valid = all.filter((s) => !s.riskExcluded);
  const limits = valid.filter(isLimitUp).sort((a, b) => b.pct - a.pct || b.amount - a.amount);
  const limitDowns = valid.filter(isLimitDown).sort((a, b) => a.pct - b.pct);
  const failed = valid.filter(isFailedLimitUp).sort((a, b) => b.pct - a.pct || b.amount - a.amount);

  const knownBoardMap = new Map([
    ["002254", 3],
    ["002354", 3],
    ["603616", 2],
    ["002636", 2],
    ["603929", 2],
    ["001696", 2],
    ["002747", 2],
    ["002362", 2],
    ["688207", 2],
    ["603186", 2],
  ]);
  const enrichedLimits = limits.map((stock) => ({
    ...stock,
    boards: knownBoardMap.get(stock.code) || 1,
    fiveDayLimitCount: null,
    fiveDayPct: null,
  }));

  const strongCandidates = valid
    .filter((s) => !isLimitUp(s) && s.pct >= 5 && s.close > s.open && s.amount >= 3e8)
    .sort((a, b) => b.pct - a.pct || b.amount - a.amount)
    .slice(0, 120);

  const enrichedStrong = strongCandidates.slice(0, 80).map((stock) => ({
    ...stock,
    recentLimitCount: null,
    sixDayPct: null,
    trendOk: stock.close > stock.open && stock.close >= stock.high * 0.92,
  }));

  const indices = {};
  for (const item of [
    ["000001", "1", "shcomp"],
    ["399001", "0", "szcomp"],
    ["399006", "0", "chinext"],
    ["000300", "1", "csi300"],
    ["000688", "1", "sci50"],
    ["899050", "0", "bse50"],
  ]) {
    await sleep(120);
    indices[item[2]] = await fetchIndex(item[0], item[1]);
  }

  const industryGroups = groupBy(valid, (s) => s.industry).map((g) => {
    const amount = g.rows.reduce((sum, x) => sum + (x.amount || 0), 0);
    const avgPct = g.rows.reduce((sum, x) => sum + (x.pct || 0), 0) / g.rows.length;
    const up = g.rows.filter((x) => x.pct > 0).length;
    const down = g.rows.filter((x) => x.pct < 0).length;
    const limitUp = g.rows.filter(isLimitUp).length;
    const mainNet = g.rows.reduce((sum, x) => sum + (x.netMain || 0), 0);
    return { name: g.name, count: g.rows.length, avgPct: round2(avgPct), amount, up, down, limitUp, mainNet };
  });

  const data = {
    asOf: "2026-06-09 15:00:00 Asia/Shanghai",
    source: "Eastmoney push2/push2his API; name-based ST/delisting-risk exclusion",
    universe: {
      allCount: all.length,
      validCount: valid.length,
      excludedRiskCount: all.length - valid.length,
      up: valid.filter((s) => s.pct > 0).length,
      flat: valid.filter((s) => s.pct === 0).length,
      down: valid.filter((s) => s.pct < 0).length,
      limitUp: limits.length,
      limitDown: limitDowns.length,
      failedLimitUp: failed.length,
      totalAmount: valid.reduce((sum, x) => sum + (x.amount || 0), 0),
    },
    indices,
    industry: {
      topByAvgPct: industryGroups.sort((a, b) => b.avgPct - a.avgPct).slice(0, 15),
      bottomByAvgPct: [...industryGroups].sort((a, b) => a.avgPct - b.avgPct).slice(0, 15),
      topByMainNet: [...industryGroups].sort((a, b) => b.mainNet - a.mainNet).slice(0, 15),
      bottomByMainNet: [...industryGroups].sort((a, b) => a.mainNet - b.mainNet).slice(0, 15),
    },
    limitBoard: {
      all: enrichedLimits,
      byBoard: groupBy(enrichedLimits, (s) => `${Math.max(1, s.boards)}板`).sort((a, b) => parseInt(b.name) - parseInt(a.name)),
      limitDowns,
      failed: failed.slice(0, 80),
    },
    strongTrend: enrichedStrong.filter((s) => s.trendOk).slice(0, 50),
    topGainers: valid.sort((a, b) => b.pct - a.pct).slice(0, 80),
    topTurnover: valid.sort((a, b) => b.amount - a.amount).slice(0, 80),
    mainNetBuy: valid.sort((a, b) => b.netMain - a.netMain).slice(0, 60),
    mainNetSell: valid.sort((a, b) => a.netMain - b.netMain).slice(0, 60),
  };

  fs.writeFileSync(path.join(OUT_DIR, "market_data.json"), JSON.stringify(data, null, 2), "utf8");
  console.log(JSON.stringify(data.universe, null, 2));
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
