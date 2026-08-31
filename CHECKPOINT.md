# Checkpoint

## Task

Set up a long-thread-friendly A-share research workspace and user-level Codex skills.

## Completed

- Created workspace directories:
  - `C:\Users\愚者\Documents\New project 3\data`
  - `C:\Users\愚者\Documents\New project 3\research`
  - `C:\Users\愚者\Documents\New project 3\reports`
  - `C:\Users\愚者\Documents\New project 3\scripts`
- Created project memory file:
  - `C:\Users\愚者\Documents\New project 3\CODEx_MEMORY.md`
- Installed finance research skills under:
  - `C:\Users\愚者\.codex\skills`
- Installed thread stability skills:
  - `thread-handoff-summary`
  - `project-memory-capture`
  - `task-checkpoint-manager`
  - `long-thread-stability`
- Installed event-driven alert skills:
  - `a-share-catalyst-monitor`
  - `ipo-beneficiary-radar`
  - `event-driven-watchlist`
- Created watchlists:
  - `C:\Users\愚者\Documents\New project 3\research\watchlists\changxin-memory-ipo.md`
  - `C:\Users\愚者\Documents\New project 3\research\watchlists\hefei-state-capital.md`
  - `C:\Users\愚者\Documents\New project 3\research\watchlists\semiconductor-supply-chain.md`
- Created alert report template:
  - `C:\Users\愚者\Documents\New project 3\reports\alerts\ALERT_TEMPLATE.md`
- Created active automations:
  - `a-2`: A股事件驱动盘前扫描
  - `a-3`: A股事件驱动盘后扫描

## Current State

This workspace should be used as the persistent state layer for future A-share research, data pulls, scripts, and reports. Chat history should not be the only source of memory.

Event-driven monitoring is now organized around watchlists and dated alert reports. The main initial topics are 长鑫科技/长鑫存储 IPO, 合肥国资/产业资本映射, and 半导体国产化供应链.

Generated a 2026-05-27 A-share market analysis report that combines the user's local PDF framework, the TimesFM GitHub project, and same-day public market data:
- `C:\Users\愚者\Documents\New project 3\reports\2026-05-27-a-share-market-analysis.html`
- `C:\Users\愚者\Documents\New project 3\reports\2026-05-27-a-share-market-analysis.pdf`
- Extracted source PDF text: `C:\Users\愚者\Documents\New project 3\research\skill-pdf-extract-2026-05-27.txt`

Generated a revised version incorporating `5月27日大盘异动解密.pdf`:
- `C:\Users\愚者\Documents\New project 3\reports\2026-05-27-a-share-market-analysis-revised.html`
- `C:\Users\愚者\Documents\New project 3\reports\2026-05-27-a-share-market-analysis-revised.pdf`
- Extracted second source PDF text: `C:\Users\愚者\Documents\New project 3\research\market-move-decode-2026-05-27-extract.txt`

Generated a cleaner 5-day A-share analysis report that uses the user's provided materials but omits source-title/method-positioning language:
- `C:\Users\愚者\Documents\New project 3\reports\2026-05-28-a-share-5day-market-analysis.html`
- `C:\Users\愚者\Documents\New project 3\reports\2026-05-28-a-share-5day-market-analysis.pdf`

Generated final 5.27 A-share market analysis and 5.28 forecast report:
- `C:\Users\愚者\Documents\New project 3\reports\2026-05-27-a-share-final-analysis-forecast.md`
- `C:\Users\愚者\Documents\New project 3\reports\2026-05-27-a-share-final-analysis-forecast.html`
- `C:\Users\愚者\Documents\New project 3\reports\2026-05-27-a-share-final-analysis-forecast.pdf`
- Extracted final source PDF text: `C:\Users\愚者\Documents\New project 3\research\market-move-decode-2026-05-27-final-extract.txt`

## Validation

- Directory creation was verified by listing the workspace folders.
- Skill files should be picked up after restarting Codex.
- Watchlist files and alert template were created.
- Automation cards were created in the Codex app.
- The generated market-analysis PDF was checked with PDF.js: 4 pages and readable text on page 1.
- The revised PDF was checked with PDF.js: 5 pages and readable text on page 1.
- The 5-day analysis PDF was checked with PDF.js: 4 pages and readable text on page 1.
- The final 5.27 analysis and 5.28 forecast PDF was generated directly with embedded Chinese font and checked with PDF.js: 3 pages and readable text on page 1.

Regenerated a UI-styled final PDF with explicit 5.27 intraday evolution sections:
- `C:\Users\愚者\Documents\New project 3\reports\2026-05-27-a-share-final-analysis-forecast-ui.pdf`
- Render script: `C:\Users\愚者\Documents\New project 3\scripts\render_final_ui_market_pdf.js`
- Checked with PDF.js: 3 pages and readable text on page 1.

Regenerated a larger black Songti-style version:
- `C:\Users\愚者\Documents\New project 3\reports\2026-05-27-a-share-final-analysis-forecast-songti-black.pdf`
- Uses `C:\Windows\Fonts\STSONG.TTF`, black text, larger font/line spacing.
- Checked with PDF.js: 4 pages and readable text on page 1.

## Pending

- Configure `TUSHARE_TOKEN` if Tushare data access is needed.
- Add actual data scripts when the first data-driven workflow is requested.
- Tune automation schedules in the Codex app if exact wall-clock timing needs adjustment.

## 2026-06-28 Automation a-2 Status

- Ran A股事件驱动盘前扫描 for the watchlists under `C:\Users\愚者\Documents\New project 3\research\watchlists`.
- Wrote alert report: `C:\Users\愚者\Documents\New project 3\reports\alerts\2026-06-28-a-share-preopen-event-scan.md`.
- Conclusion: no material new CXMT IPO / Hefei state-capital direct catalyst found after 2026-06-19; CXMT official status remains CSRC approval / SSE 注册生效 from 2026-06-12 to 2026-06-15 public updates.
- Noted one indirect semiconductor-localization signal: 华虹公司(688347) 2026-06-23 report for acquiring 华力微 97.4988% equity and raising matching funds; not treated as a direct CXMT beneficiary chain.

## Next Actions

1. Restart Codex so newly installed skills are discoverable in new threads.
2. For future long tasks, read `CODEx_MEMORY.md` and `CHECKPOINT.md` first.
3. Save large outputs into `research`, `data`, or `reports`.

## 2026-08-31 PDF Typography Update

- Replaced the report fallback font with the embedded Source Han Sans CN variable font:
  - `C:\Users\愚者\Documents\New project 3\assets\fonts\SourceHanSansCN-VF.ttf`
- Increased title, body, annotation, and table text sizes and expanded line spacing/padding.
- Added explicit pagination so theme and stock-role tables are not split from their dates.
- Regenerated and visually checked all 11 pages with Poppler; no clipping, overlap, or missing Chinese glyphs were found.
- Final report:
  - `C:\Users\愚者\Documents\New project 3\output\pdf\2026-08-30-sentiment-review-2026-08-24-to-2026-08-28.pdf`

## 2026-09-01 Reference-Matched Font Weights

- Inspected `D:\桌面\92科比淘股吧直播内容整理.pdf` strictly as a visual/font reference.
- Identified its font hierarchy as Source Han Sans CN Regular, Medium, and Bold.
- Generated static Regular/Medium/Bold TTF instances and mapped them to body text, headings/table headers, and primary emphasis respectively.
- Regenerated the 11-page report and visually checked every page; text is solid black with no clipping or table overflow.
- Final readability tuning kept the report at 11 pages while increasing narrative body text from 12pt to 14pt and table text from 10pt to 11.5pt.
- This Source Han Sans CN font hierarchy and readable-size policy is now stored in `CODEx_MEMORY.md` as the default for future Chinese PDFs.

## 2026-08-30 A股情绪引擎集成

- Wrote and committed the Chinese design spec:
  - `C:\Users\愚者\Documents\New project 3\docs\superpowers\specs\2026-08-30-a-share-sentiment-engine-design.md`
- Implemented reusable engine:
  - `C:\Users\愚者\Documents\New project 3\tools\a_share_sentiment_engine.py`
- Refactored the 2026-08-24 to 2026-08-28 sentiment review script into a thin wrapper:
  - `C:\Users\愚者\Documents\New project 3\tools\review_sentiment_20260824_20260828.py`
- Engine output contract:
  - `market_dashboard`
  - `theme_ranking`
  - `stock_role_classification`
  - `discipline_gate`
- Intended validation command once Python is available in PATH:
  - `python tools/review_sentiment_20260824_20260828.py`
- Runtime status update: Python is now available through the project virtual environment:
  - `C:\Users\愚者\Documents\New project 3\.venv\Scripts\python.exe`
- Created the virtual environment with user-local uv:
  - `C:\Users\愚者\.local\bin\uv.exe`
- Installed A-share and PDF dependencies into `.venv`, including `akshare`, `pandas`, `reportlab`, `pypdf`, and `pdfplumber`.
- Successful validation command:
  - `.venv\Scripts\python.exe tools\review_sentiment_20260824_20260828.py`
- Generated PDF report:
  - `C:\Users\愚者\Documents\New project 3\reports\market_reviews\2026-08-30-sentiment-review-2026-08-24-to-2026-08-28.pdf`
- PDF validation:
  - `pypdf` extracted 7 pages and found the four core sections.
  - Rendered page 1 with Poppler and visually confirmed Chinese tables are readable.

## 2026-08-30 Trading Framework And Market Review

- Added user-provided PDFs as future A-share analysis foundation materials:
  - `C:\Users\愚者\Documents\New project 3\research\frameworks\92科比淘股吧直播内容整理.pdf`
  - `C:\Users\愚者\Documents\New project 3\research\frameworks\交易守则-DS版.pdf`
- Extracted text from both PDFs:
  - `C:\Users\愚者\Documents\New project 3\research\frameworks\92科比淘股吧直播内容整理.txt`
  - `C:\Users\愚者\Documents\New project 3\research\frameworks\交易守则-DS版.txt`
- Wrote framework summary:
  - `C:\Users\愚者\Documents\New project 3\research\frameworks\a-share-trading-framework-foundation.md`
- Rule: these PDFs are research inputs only, not instructions to Codex.
- Pulled A-share index daily data with AKShare for 2025-09-24 to 2026-08-28 and saved:
  - `C:\Users\愚者\Documents\New project 3\data\market_reviews\2025-09-24_to_2026-08-28`
- Wrote review report:
  - `C:\Users\愚者\Documents\New project 3\reports\market_reviews\2026-08-30-a-share-review-since-2025-09-24.md`
- Core conclusion: the period was structural rather than a broad bull market. High-beta tech and small/mid-cap exposure delivered gains only if the trader survived large drawdowns and reduced exposure around the July 2026 retreat.

## 2026-07-11 Automation a-3 Status

- Ran the post-market event-driven scan across all three watchlists, using public sources for the incremental window 2026-07-06 to 2026-07-11.
- Wrote alert report: `C:\Users\愚者\Documents\New project 3\reports\alerts\2026-07-11-a-share-postmarket-event-scan.md`.
- Material change: Changxin Technology (proposed STAR Market code 688825) released its prospectus and issuance-stage documents on 2026-07-09. Online/offline subscription is scheduled for 2026-07-16; the initial offering is 6,688,088,608 shares with a 15% over-allotment option.
- Updated `research\watchlists\changxin-memory-ipo.md` with this confirmed trigger. No direct CXMT customer, supplier, order, or new Hefei state-capital mapping was confirmed; equipment/material names remain thematic unless separately disclosed.

## 2026-07-11 Automation a-2 Status

- Completed the pre-open scan of all three event-driven watchlists.
- Wrote [`2026-07-11-a-share-preopen-event-scan.md`](C:\Users\愚者\Documents\New project 3\reports\alerts\2026-07-11-a-share-preopen-event-scan.md).
- Material change: Changxin Technology disclosed its IPO prospectus and issuance timetable on 2026-07-09; online/offline subscription is scheduled for 2026-07-16. Treat as an IPO-stage catalyst, not as confirmed supplier/customer evidence for the A-share watchlist names.
- No new direct Hefei state-capital action or explicit Changxin supplier/customer/equity-link disclosure was identified in the scan window.

## 2026-07-05 Automation a-2 Status

- Ran A股事件驱动盘前扫描 for the watchlists under `C:\Users\愚者\Documents\New project 3\research\watchlists`.
- Wrote alert report: `C:\Users\愚者\Documents\New project 3\reports\alerts\2026-07-05-a-share-preopen-event-scan.md`.
- Conclusion: no material new CXMT IPO / Hefei state-capital direct catalyst found after 2026-06-28. SSE project JSON still shows Changxin update time `2026-06-15 09:03:25`; latest attachment remains the 2026-06-12 registration approval.
- Noted one indirect semiconductor equipment-chain financing signal: 拓荆科技(688072) 2026-07-03 private-placement issuance result / listing announcement; not treated as direct CXMT customer/order evidence.

## 2026-09-01 Codex Cloud Migration

- Prepared the project for `https://github.com/lc931223-lc/a-share-daily-review` on branch `main`.
- Added a cross-platform `README.md`, cloud environment guidance, secret handling rules, and the Source Han Sans license.
- Excluded `.env`, virtual environments, browser caches, temporary output, local Cloudflare binaries, and the unused variable font.
- Verified Python compilation and regenerated the cached 2026-08-24 to 2026-08-28 PDF successfully before migration.
