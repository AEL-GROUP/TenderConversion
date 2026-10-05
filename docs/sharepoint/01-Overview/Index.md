# 服務概覽分類索引 (Overview Index)

本分類為讀者提供投標文檔 RAG ETL 管道與 Google Cloud Agent Enterprise Platform 之宏觀概念、商業價值與系統邊界說明。

> 依據 SharePoint 文件庫最佳實踐規範，`01-Overview` 採用**扁平結構不進行子資料夾嵌套**，讀者可直接閱覽文件。

---

## 主題文件清單 (Overview Topics)

| 文件名稱 | 適用對象 | 核心內容說明 | 狀態 |
|---|---|---|---|
| [服務概覽與 Gcloud Agent 邊界 (Service-overview.md)](Service-overview.md) | 全體人員、業務主管、架構師 | 介紹 ETL 管道之核心價值、為什麼要轉換 Word 與 PDF、Google Cloud RAG Agent 邊界與限制 | 現行版本 |

---

## 核心重點摘要 (Key Takeaways)

1. **核心使命：** 專門解決大型工程投標文件（Word / PDF）難以被 Google Cloud Agent Enterprise Platform 順利索引與 RAG 檢索的問題。
2. **關鍵指標：** 檔案體積嚴格限制在 **< 50.0 MB**，頁數限制在 **<= 500 頁**，文字層百分之百保真。
3. **無縫接軌：** 輸出成果直接相容於 GCS Bucket 階層結構，支援下游 Document AI Layout Parser 與 Agent 語意檢索。

---

## 相關參考文件 (Related Links)

- [返回根目錄導覽](../README.md)
- [前往營運與作業指引](../02-ETL-and-operations/Index.md)
- [前往技術專題參考](../03-Technical-reference/Index.md)
