# A股每日自动复盘系统（Codex 项目脚手架）

目标：每天收盘后自动完成 A 股市场复盘，并长期积累“主线—个股—证据—评分—阶段—次日验证点”的历史数据库。

核心链路：

数据采集
→ 数据标准化
→ 市场总览
→ 主线识别
→ 41类上涨因素归因
→ 逻辑评分
→ 核心个股评分
→ 昨日/今日变化检测
→ 明日验证清单
→ Markdown 报告
→ JSON 结构化归档
→ SQLite 历史数据库

---

## 一、推荐目录

```text
a_share_daily_review_codex/
├─ README.md
├─ requirements.txt
├─ .env.example
├─ prompts/
│  ├─ SYSTEM_PROMPT.md
│  └─ DAILY_TASK_PROMPT.md
├─ config/
│  ├─ scoring.json
│  └─ sources.example.json
├─ schemas/
│  ├─ daily_review.schema.json
│  └─ stock_review.schema.json
├─ sql/
│  └─ schema.sql
├─ src/
│  ├─ main.py
│  ├─ adapters/
│  │  ├─ base.py
│  │  ├─ market_data.py
│  │  ├─ disclosure.py
│  │  ├─ policy_news.py
│  │  └─ industry_data.py
│  ├─ core/
│  │  ├─ classify.py
│  │  ├─ score.py
│  │  ├─ lifecycle.py
│  │  └─ compare.py
│  ├─ storage/
│  │  ├─ db.py
│  │  └─ files.py
│  └─ reporting/
│     ├─ markdown.py
│     └─ json_report.py
├─ data/
│  ├─ daily/
│  ├─ json/
│  └─ cache/
├─ logs/
├─ tests/
└─ docs/
   ├─ DATA_SOURCE_DESIGN.md
   └─ DATABASE_FIELDS.md
```

---

## 二、每天的自动运行顺序

建议交易日 15:30 后执行：

1. 检查是否为 A 股交易日
2. 获取当日指数、成交额、涨跌家数、涨停/跌停、连板高度
3. 获取行业/概念板块涨跌、成交额、领涨股
4. 获取个股行情、涨停原因、异动信息
5. 获取公司公告、业绩预告、订单、投资者关系记录
6. 获取官方政策、政府文件、行业协会与权威媒体信息
7. 标准化所有数据
8. 识别主线 TOP5
9. 将每条主线映射到 41 类上涨因素
10. 生成因果链
11. 进行 100 分评分
12. 筛选核心个股 TOP10
13. 读取上一交易日结果
14. 标记新增 / 强化 / 弱化 / 扩散 / 兑现 / 证伪
15. 生成次日验证点
16. 写入 Markdown
17. 写入 JSON
18. 写入 SQLite
19. 保存评分变化原因
20. 若为周五或月末，再生成周报/月报

---

## 三、运行

开发阶段：

```bash
python -m src.main --date 2026-09-01
```

自动模式：

```bash
python -m src.main --date auto
```

---

## 四、重要原则

- 不允许“股价涨了以后再倒推理由”
- D级传闻不能作为高兑现分依据
- 多个题材不能机械叠加
- 必须区分：题材催化、产业逻辑、财务兑现、资金确认
- 所有调分必须记录 delta_reason
- 不允许修改历史评分，只允许新增后续评分记录
- 数据缺失时必须输出“证据不足 / 暂不评分”
- 评分不构成投资建议
