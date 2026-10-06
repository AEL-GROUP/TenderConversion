# RAG 資料集交付規格與平台限制 (RAG Dataset Delivery Specifications and Platform Constraints)

**適用對象：** 資料工程師 / 系統架構師 / 雲端維護人員  
**文件狀態：** 現行版本  
**最後審核：** 2026-10-05  

> 備註：以下 ETL 交付規格於 2026 年 10 月 05 日審閱本文件時仍然適用；平台端規格請依目標環境確認。

---

## 簡要說明 (Summary)

本文件說明 `TenderConversion` ETL 管道的資料交付範圍與輸出規格。**本專案負責資料前處理與格式轉換**；下游平台如何接收資料、建立索引或設定 Agent，則不在本管道的處理範圍內。請在交付前，依實際使用的 GCS 與平台設定確認其輸入限制。

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

- **本專案責任：** 依管道設定處理文件，並檢查輸出檔案大小、頁數、文字層與格式。
- **下游平台責任：** 如何接收文件、解析、建立索引及提供檢索服務，須依實際平台部署與設定處理。

---

## RAG 資料集輸出規格 (Core Ingestion Standards)

以下列出本管道的預設輸出要求。各項設定可依目標環境的規格調整；正式交付前應再次核對平台要求：

| 規範項目 | 交付標準門檻 | 平台端限制依據 | 驗收方式 |
|---|---|---|---|
| **單一檔案大小** | 預設門檻為 `< 50.0 MB` | 平台實際限制依服務與設定而異，請先確認目標環境。 | 執行管線 Step 3 檢查；超出設定門檻時依管道流程處理。 |
| **單一檔案頁數** | 預設門檻為 `<= 500 頁` | 平台實際限制依服務與設定而異，請先確認目標環境。 | 逐檔檢查頁數，並依設定分塊。 |
| **文件格式** | 管道輸出 PDF | 是否符合目標平台要求，須依該平台支援的格式確認。 | `.doc` 與 `.docx` 由 LibreOffice 轉為 PDF。 |
| **文字層** | 一般處理流程保留原生文字層 | 單頁救援會將該頁轉為點陣圖，因此不再保有可搜尋的原生文字。 | 管道透過文字 SHA-256 雜湊等不變性檢查一般處理結果。 |
| **圖像解析度** | 預設目標為 200 DPI | 最適設定取決於來源文件與下游用途。 | 對符合條件的高解析度點陣圖進行重採樣。 |

---

## GCS 交付路徑與檔案命名規範 (Delivery Path and Naming)

1. **保留目錄結構：**
   - 管道輸出會保留來源文件的相對路徑，例如 `volume-01/`、`volume-02/`。
   - 下游是否依路徑進行篩選，須以平台的實際設定為準。
2. **分塊檔名連續性：**
   - 當文件因超過 50MB 或 500 頁而被切分時，檔名依序標註為：
     - `<原始檔名>_chunk-1.pdf`
     - `<原始檔名>_chunk-2.pdf`
     - `<原始檔名>_chunk-3.pdf`
   - 以連續序號標示分塊，方便管理者辨識及追溯來源。
3. **編碼安全：**
   - 檔名與路徑必須為合法的 UTF-8 字串，避免控制字元與換行符號。

---

## 異常檔案交付標記 (Handling Rescued Files)

- **超大單頁救援：** 若單頁超過管道設定的大小門檻，管道會嘗試將該頁點陣化，以符合門檻。
- **輸出特性：** 救援頁面以點陣圖表示，不含原生文字層。後續是否以 OCR 處理，取決於下游環境設定。

---

## 已知限制或待確認項目 (Pending Confirmations & Limitations)

- **待確認：** 正式環境的 GCS 目的地路徑（例如 `gs://<bucket-name>/tenders/`）。
- **待確認：** 資料集的最終驗收人員。

---

## 相關參考文件 (Related Topics)

- [返回技術分類索引](../Index.md)
- [Gcloud RAG Agent 限制規範](../../02-ETL-and-operations/02-RAG-spec-and-limits/Gcloud-rag-agent-constraints.md)
- [GCS 儲存拓撲與同步指引](Gcs-storage-topology-and-sync.md)
- [無損重整、圖像降採樣與貪婪分塊算法](../01-Architecture/Compression-and-chunking-algorithms.md)
