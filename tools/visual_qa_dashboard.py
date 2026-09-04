import json
import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright


EDGE_PATH = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"


def main() -> int:
    output_dir = Path("tmp")
    output_dir.mkdir(parents=True, exist_ok=True)
    dashboard_url = os.environ.get("DASHBOARD_URL", "http://localhost:8501")
    results = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, executable_path=EDGE_PATH)
        for name, width, height in (("desktop", 1440, 900), ("mobile", 390, 844)):
            page = browser.new_page(viewport={"width": width, "height": height})
            page.goto(dashboard_url, wait_until="networkidle", timeout=30000)
            page.get_by_role("heading", name="A股市场复盘 Dashboard").wait_for(timeout=20000)
            page.get_by_text("正式真实数据", exact=False).wait_for(timeout=20000)
            page.wait_for_timeout(1000)
            for _ in range(8):
                page.mouse.wheel(0, height)
                page.wait_for_timeout(250)
            page.mouse.wheel(0, -height * 8)
            page.wait_for_timeout(500)
            body = page.locator("body").inner_text()
            diagnostics = page.evaluate(
                """() => ({
                    overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
                    svgCount: document.querySelectorAll("svg").length,
                    dataframeCount: document.querySelectorAll('[data-testid="stDataFrame"]').length
                })"""
            )
            result = {
                "name": name,
                "title": page.title(),
                "hasDashboard": "A股市场复盘 Dashboard" in body,
                "hasMarket": "今日市场" in body,
                "hasThemes": "今日主线 TOP5" in body,
                "hasQuality": "正式真实数据" in body,
                "hasException": "Traceback" in body or "Exception" in body,
                **diagnostics,
            }
            results.append(result)
            page.screenshot(path=str(output_dir / f"dashboard-{name}.png"), full_page=True)
            page.close()
        browser.close()
    print(json.dumps(results, ensure_ascii=False, indent=2))
    if any(
        not item["hasDashboard"]
        or not item["hasMarket"]
        or not item["hasThemes"]
        or not item["hasQuality"]
        or item["hasException"]
        or item["overflow"] > 2
        for item in results
    ):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
