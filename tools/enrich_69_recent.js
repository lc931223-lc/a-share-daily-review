const fs = require("fs");
const path = require("path");
const cp = require("child_process");

const outPath = "output/69-review/market_data.json";
const data = JSON.parse(fs.readFileSync(outPath, "utf8"));
const UA = "Mozilla/5.0";

function qPrefix(code) {
  if (code.startsWith("6")) return `sh${code}`;
  return `sz${code}`;
}
function limitRate(code, name) {
  if (/ST|\*ST|\u9000/.test(name)) return 0.05;
  if (code.startsWith("300") || code.startsWith("301") || code.startsWith("688")) return 0.2;
  if (code.startsWith("8") || code.startsWith("4")) return 0.3;
  return 0.1;
}
function round2(n) {
  return Math.round((Number(n) + Number.EPSILON) * 100) / 100;
}
function fetchJson(url) {
  const text = cp.execFileSync("curl.exe", ["-L", "--compressed", "--retry", "2", "-A", UA, url], {
    encoding: "utf8",
    maxBuffer: 4 * 1024 * 1024,
    stdio: ["ignore", "pipe", "ignore"],
  });
  return JSON.parse(text);
}
function fetchKline(code) {
  const q = qPrefix(code);
  const url = `https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=${q},day,,,10,qfq`;
  const j = fetchJson(url);
  return j.data?.[q]?.day?.map((r) => ({
    date: r[0],
    open: Number(r[1]),
    close: Number(r[2]),
    high: Number(r[3]),
    low: Number(r[4]),
    volume: Number(r[5]),
  })) || [];
}
function isLimit(row, prev, stock) {
  if (!prev) return false;
  const up = round2(prev.close * (1 + limitRate(stock.code, stock.name)));
  return row.close >= up - 0.01 && row.high >= up - 0.01;
}
function maxConsecutiveLimit(kline, stock) {
  let max = 0;
  let cur = 0;
  for (let i = 1; i < kline.length; i += 1) {
    if (isLimit(kline[i], kline[i - 1], stock)) {
      cur += 1;
      max = Math.max(max, cur);
    } else {
      cur = 0;
    }
  }
  return max;
}
function recentPct(kline, days) {
  if (kline.length < 2) return null;
  const end = kline[kline.length - 1];
  const start = kline[Math.max(0, kline.length - days)];
  return round2(((end.close - start.close) / start.close) * 100);
}

const candidatesMap = new Map();
for (const s of [
  ...data.limitBoard.all,
  ...data.strongTrend,
  ...data.topGainers.slice(0, 120),
  ...data.topTurnover.slice(0, 80),
]) {
  if (!s.code.startsWith("8") && !s.code.startsWith("4")) candidatesMap.set(s.code, s);
}

const enriched = [];
for (const stock of candidatesMap.values()) {
  try {
    const kline = fetchKline(stock.code);
    enriched.push({
      code: stock.code,
      name: stock.name,
      industry: stock.industry,
      pct: stock.pct,
      amount: stock.amount,
      recent5Pct: recentPct(kline, 5),
      recent8Pct: recentPct(kline, 8),
      maxConsecutiveLimit: maxConsecutiveLimit(kline, stock),
      lastClose: kline.at(-1)?.close,
    });
  } catch (_) {}
}

data.recentLeaders = enriched
  .filter((s) => (s.recent8Pct ?? 0) >= 40 && s.maxConsecutiveLimit >= 2)
  .sort((a, b) => b.recent8Pct - a.recent8Pct)
  .slice(0, 30);

data.recentHotButNotLimit = enriched
  .filter((s) => (s.recent5Pct ?? 0) >= 15 && s.maxConsecutiveLimit >= 1 && !data.limitBoard.all.some((x) => x.code === s.code))
  .sort((a, b) => b.recent5Pct - a.recent5Pct)
  .slice(0, 40);

fs.writeFileSync(outPath, JSON.stringify(data, null, 2), "utf8");
console.log(JSON.stringify({ recentLeaders: data.recentLeaders.length, recentHotButNotLimit: data.recentHotButNotLimit.length }, null, 2));
