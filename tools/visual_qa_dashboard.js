const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

const edgePath = "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe";
const outputDir = path.resolve("tmp");
const dashboardUrl = process.env.DASHBOARD_URL || "http://localhost:8501";
fs.mkdirSync(outputDir, { recursive: true });

(async () => {
  const browser = await chromium.launch({ headless: true, executablePath: edgePath });
  const viewports = [
    ["desktop", 1440, 900],
    ["mobile", 390, 844],
  ];
  const results = [];
  for (const [name, width, height] of viewports) {
    const page = await browser.newPage({ viewport: { width, height } });
    await page.goto(dashboardUrl, { waitUntil: "networkidle", timeout: 30000 });
    await page.getByRole("heading", { name: "A股市场复盘 Dashboard" }).waitFor({ timeout: 20000 });
    await page.getByText("正式真实数据", { exact: false }).waitFor({ timeout: 20000 });
    await page.waitForTimeout(1000);
    const body = await page.locator("body").innerText();
    const diagnostics = await page.evaluate(() => ({
      overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
      svgCount: document.querySelectorAll("svg").length,
      dataframeCount: document.querySelectorAll('[data-testid="stDataFrame"]').length,
    }));
    const result = {
      name,
      title: await page.title(),
      hasDashboard: body.includes("A股市场复盘 Dashboard"),
      hasMarket: body.includes("今日市场"),
      hasThemes: body.includes("今日主线 TOP5"),
      hasQuality: body.includes("正式真实数据"),
      hasException: body.includes("Traceback") || body.includes("Exception"),
      ...diagnostics,
    };
    results.push(result);
    await page.screenshot({ path: path.join(outputDir, `dashboard-${name}.png`), fullPage: true });
    await page.close();
  }
  await browser.close();
  console.log(JSON.stringify(results, null, 2));
  if (results.some((item) => !item.hasDashboard || !item.hasMarket || !item.hasThemes || !item.hasQuality || item.hasException || item.overflow > 2)) {
    process.exit(1);
  }
})();
