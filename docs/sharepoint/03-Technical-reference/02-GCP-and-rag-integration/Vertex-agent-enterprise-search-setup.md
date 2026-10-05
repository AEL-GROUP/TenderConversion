# RAG 資料集交付規格與平台限制 (RAG Dataset Delivery Specifications and Platform Constraints)

**適用對象：** 資料工程師 / 系統架構師 / 雲端維護人員  
**文件狀態：** 現行版本  
**最後審核：** 2026-10-05  

> 備註：以下交付規格與平台輸入限制於 2026 年 10 月 05 日審核此文檔時仍然有效。

---

## 簡要說明 (Summary)

本文件定義 `TenderConversion` ETL 管道產出並存放於 Google Cloud Storage (GCS) 之標準資料集交付規範。**本專案專注於資料預處理與格式合規化（ETL）**，目標是產出符合 GCloud Agent Enterprise Platform 之 GCS 儲存與 RAG Agent 檢索庫硬性限制的標準文件；下游 RAG Engine 之切片策略、檢索模型與 Agent 應用配置均屬於平台端範疇，不在本 ETL 管道之處理邊界內。

---

## 服務職責劃分與邊界 (Boundary and Separation of Concerns)

```mermaid
flowchart LR
    subgraph InScope[ETL 管道職責範圍 (本專案)]
        Extract[過濾提取 .doc, .docx, .pdf]
        Convert[Word 轉高保真 PDF]
        Repack[無損重整與 200/300 DPI 降採樣]
        Chunk[嚴格 < 50MB 與 <= 500 頁分塊]
        Preserve[100% 保留原生文字層與目錄結構]
    end

    subgraph Storage[交付與介接層]
        GCSBucket[Google Cloud Storage 儲存貯體<br/>階層化目錄與合規 PDF]
    end

    subgraph DownstreamPlatform[下游 GCloud Agent Enterprise Platform]
        Ingest[GCS 資料集攝取]
        RAGEngine[平台 RAG Engine / 向量索引]
        RAGAgent[RAG Agent 問答與應用服務]
    end

    InScope -->|交付標準檔案| Storage
    Storage -->|資料來源| DownstreamPlatform
```

- **本專案責任：** 確保上傳至 GCS 的每一份文件，100% 通過檔案大小、頁數、文字層與格式之硬性校驗。
- **下游平台責任：** 自行讀取 GCS 資料集進行向量嵌入（Embedding）、建立索引、提示詞工程與終端問答業務邏輯。

---

## RAG 資料集硬性交付標準 (Core Ingestion Standards)

為確保交付至 GCS 的檔案能被 RAG Agent 順利取用，產出資料集必須嚴格遵守以下五大標準：

| 規範項目 | 交付標準門檻 | 平台端限制依據 | 驗收方式 |
|---|---|---|---|
| **單一檔案體積** | 嚴格 `< 50.0 MB` | GCloud 平台非結構化文件單檔攝取上限通常為 50MB；超標者易引發逾時或被略過。 | 執行管線 Step 3 驗證，確保無任何檔案大於或等於 50MB。 |
| **單一檔案頁數** | 嚴格 `<= 500 頁` | 平台文件版面配置解析器單檔上限為 500 頁；超標文件會被直接拒絕。 | 逐檔校驗頁數，超過 500 頁者強制切分。 |
| **文件檔案格式** | 標準 PDF（可攜式文件格式） | 平台無法直接對原始 Word 檔進行高精度版面剖析，必須標準化為 PDF。 | 所有 `.doc` 與 `.docx` 均經由 LibreOffice 轉為 PDF。 |
| **文字層可搜尋性** | 原生文字層 100% 保留 | 向量檢索模型高度依賴文字字串；純點陣圖片需額外 OCR 且召回精準度低。 | 透過語意不變性校驗比對文字 SHA-256 雜湊，禁止平白點陣化。 |
| **圖像顯示解析度** | 目標 200 DPI（建議最高 300 DPI） | 過低解析度影響後續圖紙識別，過高解析度（>450 DPI）徒增體積與傳輸成本。 | 針對顯示解析度高於閾值之點陣圖進行智慧重採樣。 |

---

## GCS 交付路徑與檔案命名規範 (Delivery Path and Naming)

1. **目錄同構性（Isomorphic Hierarchy）：**
   - 交付至 GCS 的檔案必須完整保留原始投標目錄結構（如分冊 `volume-01/`、`volume-02/`）。
   - 便於下游 RAG 系統讀取 GCS URI 前綴，進行分冊範圍限定（Facet Filtering）。
2. **分塊檔名連續性：**
   - 當文件因超過 50MB 或 500 頁而被切分時，檔名依序標註為：
     - `<原始檔名>_chunk-1.pdf`
     - `<原始檔名>_chunk-2.pdf`
     - `<原始檔名>_chunk-3.pdf`
   - 確保下游 Agent 引用時，來源檔案名稱具備可追溯性與可讀性。
3. **編碼安全：**
   - 檔名與路徑必須為合法的 UTF-8 字串，避免控制字元與換行符號。

---

## 異常檔案交付標記 (Handling Rescued Files)

- **超大單頁救援檔案：** 若原始文件存在單頁（如 A0 複雜圖紙）大於 50MB，管道會啟動點陣化救援將該頁壓入 50MB 內。
- **交付特性：** 該特定分塊檔案將由點陣圖構成，原生文字層在該單頁內會失效，需依賴下游平台的 OCR 模組進行辨識。

---

## 已知限制或待確認項目 (Pending Confirmations & Limitations)

- **待確認：** 企業正式環境之 GCS 儲存庫路徑（如 `gs://<bucket-name>/tenders/`）。
- **待確認：** 交付資料集之最終驗收簽核人員。

---

## 相關參考文件 (Related Topics)

- [返回技術分類索引](../Index.md)
- [Gcloud RAG Agent 限制規範](../../02-ETL-and-operations/02-RAG-spec-and-limits/Gcloud-rag-agent-constraints.md)
- [GCS 儲存拓撲與同步指引](Gcs-storage-topology-and-sync.md)
- [無損重整、圖像降採樣與貪婪分塊算法](../01-Architecture/Compression-and-chunking-algorithms.md)
