# 技術專題參考分類索引 (Technical Reference Index)

本分類提供系統架構師、後端與 DevOps 工程師及雲端維護人員所需的技術參考，內容涵蓋演算法、Google Cloud 交付、容器環境、測試及功能設計。

---

## 子目錄與主題清單 (Technical Reference Topics)

### 01 - 核心架構與演算法 (01-Architecture)
說明 ETL 管道的程序模型、資料流程及最佳化演算法：

| 文件名稱 | 適用對象 | 核心內容說明 | 狀態 |
|---|---|---|---|
| [系統架構與 RAG 資料流設計](01-Architecture/System-architecture-and-data-flow.md) | 系統架構師、後端工程師 | 解析多程序並行模型 (ProcessPoolExecutor)、暫存目錄生命週期與交易性置換機制 | 現行版本 |
| [無損重整、圖像降採樣與貪婪分塊算法](01-Architecture/Compression-and-chunking-algorithms.md) | 演算法工程師、開發人員 | 剖析幾何/語意不變性校驗、指數倍增與二分搜尋精確位元組貪婪分塊演算法 | 現行版本 |

### 02 - Google Cloud 整合技術 (02-GCP-and-rag-integration)
整理 GCS 儲存結構、資料同步方式及資料集交付規格：

| 文件名稱 | 適用對象 | 核心內容說明 | 狀態 |
|---|---|---|---|
| [GCS 儲存拓撲與批次同步機制](02-GCP-and-rag-integration/Gcs-storage-topology-and-sync.md) | 雲端工程師、DevOps | 規劃 GCS 儲存貯體階層、`gsutil rsync` 同步指令與生命週期管理 | 現行版本 |
| [RAG 資料集交付規格與平台限制](02-GCP-and-rag-integration/Vertex-agent-enterprise-search-setup.md) | 資料工程師、系統架構師 | 說明 ETL 輸出規格、分塊命名方式，以及需向目標平台確認的項目 | 現行版本 |

### 03 - 部署與驗證 (03-Testing-and-deployment)
說明容器執行環境及自動化測試方式：

| 文件名稱 | 適用對象 | 核心內容說明 | 狀態 |
|---|---|---|---|
| [本機與 Docker 容器化配置指南](03-Testing-and-deployment/Environment-setup-and-dockerfile.md) | DevOps、系統管理員 | 解析 Dockerfile 輕量多層建置、LibreOffice  headless 依賴與 Volume 掛載機制 | 現行版本 |
| [自動化測試與回歸檢驗指引](03-Testing-and-deployment/Test-suite-and-validation-guide.md) | QA 工程師、開發者 | 說明 `test_pipeline.py` 單元測試、記憶體內合成 PDF 測試與斷言規則 | 現行版本 |

### 04 - 專題深入技術筆記 (04-Feature-notes)
記錄特定工程問題的處理方式及設計考量：

| 文件名稱 | 適用對象 | 核心內容說明 | 狀態 |
|---|---|---|---|
| [LibreOffice 無周邊 Word 轉換實作筆記](04-Feature-notes/Libreoffice-headless-conversion.md) | 核心開發者 | 深入探討 headless 轉換參數、子程序隔離、中英文字型代換策略 | 現行版本 |
| [超大單頁應急點陣化救援機制筆記](04-Feature-notes/Oversized-page-rescue-mechanism.md) | 演算法工程師 | 說明單頁超出大小門檻時的六組救援設定、輸出方式及失敗處理 | 現行版本 |

---

## 相關參考文件 (Related Links)

- [返回根目錄導覽](../README.md)
- [前往服務概覽](../01-Overview/Service-overview.md)
- [前往營運與作業指引](../02-ETL-and-operations/Index.md)
