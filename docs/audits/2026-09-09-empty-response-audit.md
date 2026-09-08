# Empty Response Semantics

An HTTP success or empty DataFrame does not prove a valid empty financial dataset.
Every source now reports NOT_EMPTY, EMPTY_VALID, EMPTY_UNVERIFIED, or SOURCE_FAILURE.

| Dataset | Evidence needed for EMPTY_VALID | Current treatment |
| --- | --- | --- |
| Limit-down | Complete same-date daily universe, valid prices, no security at any possible lower band; exact daily bands preferred | Independent verifier. Unresolved instrument bands/exemptions mean UNAVAILABLE and a hard-gate failure. |
| Limit-up | Date/coverage receipt or independent full-universe upper-band verification | Empty response stays unverified; never silently zero. |
| Failed limit-up | Intraday high/close and applicable upper bands, or authoritative complete dated pool | Daily closing return alone cannot prove no failed boards. |
| Dragon-tiger | Successful complete dated disclosure response with explicit total=0 | Unqualified adapter empty stays unverified. |
| Announcements | Existing official collector confirms covered core pool and successful empty query | Existing EMPTY_VALID contract retained. Failed/partial coverage remains degraded. |
| Policy | Existing official collector confirms all required source scans and date filters | Zero accepted records with failed sources is PARTIAL, not verified no policy. |
| Margin financing | Complete exchange dated report with reported numeric zero | Empty report is unavailable, not zero financing. |

## 2026-09-08 Verification

5,549 daily rows were checked. The exact Tushare stk_limit endpoint is unavailable under the configured account's permissions. Conservative possible lower bands identify 21 unresolved securities. In particular, 002743.SZ closes exactly at the rounded 10-percent lower band. Therefore the existing Eastmoney empty response cannot establish zero limit-down stocks. The packet remains FAIL/69 and the pool remains UNAVAILABLE; support must inherit PARTIAL_WITH_UPSTREAM_FAILURE.

No absence claim is inferred from price gains. Historical ST designations, listing exemptions, and corporate-action effects are not reconstructed from current names.

Rule references: [SSE 2026 trading rules](https://www.sse.com.cn/lawandrules/sselawsrules2025/stocks/exchange/c/c_20260424_10816482.shtml), [SSE STAR listing exemptions](https://edu.sse.com.cn/tib/qa/), [BSE trading rules](https://www.bse.cn/uploads/6/file/public/202109/20210909101516_y5wn2y3ft9.pdf). The conservative 5/10-percent main-board possibilities intentionally avoid assuming historical ST status or rule effective dates.
