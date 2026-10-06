# 服務概覽分類索引 (Overview Index)

本分類介紹投標文件 RAG ETL 管道的用途、商業價值，以及它與 Google Cloud Agent Enterprise Platform 之間的服務邊界。

> 依照 SharePoint 文件庫的目錄規劃，`01-Overview` 採扁平結構，不再建立子資料夾；讀者可直接開啟本分類中的文件。

---

## 主題文件清單 (Overview Topics)

| 文件名稱 | 適用對象 | 核心內容說明 | 狀態 |
|---|---|---|---|
| [服務概覽與 Gcloud Agent 邊界 (Service-overview.md)](Service-overview.md) | 全體人員、業務主管、架構師 | 介紹 ETL 管道的用途、Word 與 PDF 處理方式，以及與 Google Cloud 平台的服務邊界 | 現行版本 |

---

## 核心重點摘要 (Key Takeaways)

1. **核心用途：** 預先處理大型工程投標文件（Word / PDF），使其符合後續平台處理所需的格式與規格。
2. **主要指標：** 輸出檔案須小於 **50.0 MB**、不超過 **500 頁**，並保留原生文字層。
3. **交付方式：** 輸出文件可依目錄結構交付至 GCS，供下游平台依其設定處理。

---

## 相關參考文件 (Related Links)

- [返回根目錄導覽](../README.md)
- [前往營運與作業指引](../02-ETL-and-operations/Index.md)
- [前往技術專題參考](../03-Technical-reference/Index.md)
