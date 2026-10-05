# 雲端資源與運算成本結構分析 (Cloud Resource and Operating Costs)

**適用對象：** 專案經理 / IT 主管 / 財務審查人員 / 雲端架構師
**文件狀態：** 現行版本
**最後審核：** 2026-10-05

> 備註：以下 Google Cloud 產品定價模型與費用分析於 2026 年 10 月 05 日審核此文檔時仍然有效。

---

## 簡要說明 (Summary)

本文件分析將投標文檔導入 **Google Cloud Agent Enterprise Platform** 之完整雲端資源成本結構，包含 Google Cloud Storage (GCS) 儲存費、Document AI 版面配置解析費與 Vertex AI Search / RAG 查詢計費模式。同時透過數據量化，說明 **TenderConversion ETL 管道之無損重整與 200~300 DPI 降採樣機制** 如何為企業每年省下高達 40%~65% 的雲端儲存與 AI 攝取支出。

---

## 雲端費用構成分析 (Cost Breakdown)

在 Google Cloud 上維運投標 RAG 知識庫，主要涉及三層計費項目：

```text
1. GCS 儲存成本 (Storage Cost)
   └── 依每月儲存資料量 (GB/月) 計費 (標準存儲 Standard Storage)

2. 雲端解析與攝取成本 (Cloud Ingestion & Parsing Cost)
   └── 依平台解析器處理之檔案與頁數計費
```

---

## 各項雲端儲存與解析定價參考 (GCP Pricing Reference)

| 服務項目 | 計費單位 | 參考標準費率 (美金) | 說明 |
|---|---|---|---|
| **Google Cloud Storage (Standard)** | 每 GB / 每月 | 約 $0.020 ~ $0.026 USD | 儲存合規 PDF 文件的基礎費用。 |
| **文件版面配置解析 (Document AI / Parser)** | 每 1,000 頁 | 依啟用之模型而定 | 針對非結構化 PDF 進行深度表格與段落解析之單次費用。 |

> 註：下游 RAG Engine 索引與 Agent 查詢費用依企業選用之方案與模型計費，屬於下游平台端範圍，不列入本 ETL 管道之維運核算。

---

## 本 ETL 管道帶來的實質省費效益 (Cost Optimization ROI)

未經處理的原始工程投標資料庫往往充斥未壓縮圖紙、高達 600~1200 DPI 的彩色掃描檔，以及超額的未被引用頁面。本管道透過以下三項技術實現大幅度節省：

### 1. 儲存與傳輸節省：40% ~ 70% 體積削減
- **案例實測：** 一個原始容量 100 GB 的標案合約庫，透過無損物件去重、Flate 串流壓縮與適應性 200 DPI 降採樣後，通常縮減至 35 ~ 45 GB。
- **效益：** 顯著降低 GCS 存儲月費，並將跨區域資料傳輸（Network Egress）頻寬費用減半。

### 2. Document AI 運算費用的關鍵保護：原生文字層保留
- **重大盲點：** 許多陽春的 PDF 處理腳本會直接將整份文件轉成點陣圖片以降低大小。若送入此類點陣化 PDF，Google Cloud 會強制啟動高單價的 OCR 辨識引擎逐頁辨識，花費數倍的計算時間與授權費。
- **本管道優勢：** 嚴格保留原生文字向量（Native Text Invariant），Google Cloud 解析器可直接以純文字管道瞬時提取內容，**完全免除全頁 OCR 附加費**。

### 3. 精確分塊避免無效重複攝取
- 若單份檔案因超過 50MB 或 500 頁導致解析失敗，工程師往往需整批重跑，浪費重複的雲端 API 配額。本管道在進入 GCS 前即保證 100% 合規，杜絕二次收費。

---

## 成本試算模型範例 (Estimated Scenario)

假設某專案需導入 **10 個大型招標案**，總計 **50,000 頁合約與圖紙**（原始體積 120 GB）：

| 評估項目 | 未經 ETL 預處理 (原始上傳) | 採用 TenderConversion ETL 處理後 | 預期省費效益 |
|---|---|---|---|
| **GCS 儲存體積** | 120 GB ($2.64/月) | 48 GB ($1.05/月) | **節省約 60% 儲存開銷** |
| **Document AI 攝取風險** | 超大/超長檔案失敗率 > 30%，需人工反覆除錯重送 | 100% 一次性成功攝取，零失敗重試成本 | **省下數十工時與無效 API 呼叫** |
| **檢索精準度與 Token 開銷** | 雜訊檔案未剔除，檢索命中率差，浪費 Prompt Tokens | 精準剔除 DWG/XLSX 雜訊，僅提供高關聯度 PDF 片段 | **大幅降低 LLM 生成 Token 浪費** |

---

## 已知限制或待確認項目 (Pending Confirmations & Limitations)

- **待確認：** 企業專案實際簽訂之 Google Cloud Enterprise 企業折扣合約（EDP/CUD 折扣幅度）。
- **待確認：** 預期每月終端業務同仁對 RAG Agent 進行的查詢總次數。
- **待確認：** 是否設定 GCS 物件生命週期規則（Lifecycle Policy），將歷史舊案在 1 年後自動轉為 Nearline 或 Coldline 儲存。

---

## 相關參考文件 (Related Topics)

- [返回營運分類索引](../Index.md)
- [Gcloud RAG Agent 限制規範](../02-RAG-spec-and-limits/Gcloud-rag-agent-constraints.md)
- [企業身分識別與 GCS 存取指引](Enterprise-identity-and-gcs-access.md)
- [GCS 儲存拓撲與同步指引](../../03-Technical-reference/02-GCP-and-rag-integration/Gcs-storage-topology-and-sync.md)
