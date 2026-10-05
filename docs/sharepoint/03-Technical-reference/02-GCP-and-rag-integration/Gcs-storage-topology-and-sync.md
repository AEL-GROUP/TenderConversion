# GCS 儲存拓撲與批次同步機制 (GCS Storage Topology and Synchronization)

**適用對象：** 雲端維運工程師 (Cloud DevOps) / 資料架構師 / 系統整合人員
**文件狀態：** 現行版本
**最後審核：** 2026-10-05

> 備註：以下 Google Cloud Storage (GCS) 設定規格與同步指令於 2026 年 10 月 05 日審核此文檔時仍然有效。

---

## 簡要說明 (Summary)

本文件定義投標文檔經過 ETL 處理後，在 **Google Cloud Storage (GCS)** 上的標準儲存拓撲結構（Bucket Topology）、物件命名命名空間規範，以及如何運用 `gcloud storage rsync` 或 `gsutil` 執行安全、具冪等性（Idempotent）的批次資料同步，以無縫對接 Google Cloud Agent Enterprise Platform 的文件索引排程。

---

## GCS 儲存庫結構拓撲 (Bucket Directory Topology)

為了讓下游的 Vertex AI Agent Builder 與 RAG Agent 能夠依據標案編號、冊別（Volume）進行精確的元數據過濾（Metadata / Facet Filtering），GCS 儲存庫必須維持嚴格的層級拓撲：

```text
gs://<PROJECT_ID>-tender-rag-corpus/                      # 核心知識庫儲存貯體 (Bucket Root)
└── tenders/                                              # 專案主目錄
    ├── tender-2026-de202412-mbbr/                        # 標案專屬標識 (Tender Slug)
    │   ├── metadata.json                                 # (選用) 標案全域元數據檔案
    │   ├── volume-01-contract/                           # 第一分冊：合約與投標須知
    │   │   ├── Contract_Conditions.pdf
    │   │   └── Special_Provisions.pdf
    │   ├── volume-02-specification/                      # 第二分冊：工程規範書
    │   │   ├── Technical_Spec_chunk-1.pdf                # 切分合規檔案
    │   │   └── Technical_Spec_chunk-2.pdf
    │   └── volume-03-drawings/                           # 第三分冊：工程圖紙
    │       ├── General_Arrangement_chunk-1.pdf
    │       └── General_Arrangement_chunk-2.pdf
    └── tender-2026-project-alpha/                        # 其他標案目錄...
```

### 拓撲優勢
1. **路徑語意對齊：** RAG Agent 在檢索到解答時，引用的 GCS URI 為 `gs://.../volume-01-contract/Contract_Conditions.pdf`，終端使用者一眼即可辨識解答出自合約分冊。
2. **多租戶與專案隔離：** 不同標案以專屬 slug 隔離，便於單獨設定存取權限與生命週期原則。

---

## 批次同步指令指引 (Synchronization Commands)

當本機 `data/MyTender_Final` 產出合規文件後，工程師可使用 Google Cloud SDK 執行同步：

### 推薦指令：使用現代 `gcloud storage rsync`
```powershell
# 1. 啟用多執行緒快速增量同步
gcloud storage rsync -r -d ./data/MyTender_Final gs://<PROJECT_ID>-tender-rag-corpus/tenders/<TENDER_SLUG>
```

### 傳統指令：使用 `gsutil -m rsync`
```powershell
gsutil -m rsync -r -d ./data/MyTender_Final gs://<PROJECT_ID>-tender-rag-corpus/tenders/<TENDER_SLUG>
```

### 關鍵參數解說：
- `-r` (Recursive)：遞迴同步所有子資料夾，確保分冊結構不被攤平。
- `-d` (Delete)：（選用，請謹慎使用）若來源目錄中已刪除某些檔案，同步刪除 GCS 上的過時物件，避免 RAG 索引殘留舊版雜訊。
- `-m` (Multi-threading)：並行上傳多個檔案，顯著縮短同步時間。

---

## 儲存類別與生命週期管理 (Storage Class & Lifecycle)

為兼顧 RAG Agent 的檢索效能與企業儲存預算，建議在 GCS 儲存貯體上配置以下生命週期規則（Lifecycle Policy）：

| 資料型態 | 建議儲存類別 (Storage Class) | 存取特性與考量 |
|---|---|---|
| **進行中標案 (Active Tenders)** | `Standard` (標準存儲) | 供 Agent Builder 建立索引與頻繁語意查詢，提供最低讀取延遲。 |
| **已截標/歷史標案 (> 180 天)** | `Nearline` | 查詢頻率降低，儲存費用減半，讀取延遲仍可接受。 |
| **封存檔案 (> 365 天)** | `Coldline` 或 `Archive` | 供法務稽核備查，大幅壓縮長期存儲開銷。 |

---

## 已知限制或待確認項目 (Pending Confirmations & Limitations)

- **待確認：** 正式 Google Cloud 專案 ID（`<PROJECT_ID>`）與 GCS Bucket 正式名稱。
- **待確認：** 是否已指派專用 Service Account（如 `sa-tender-rag-sync@<PROJECT_ID>.iam.gserviceaccount.com`）具備 `roles/storage.objectAdmin` 權限。
- **限制：** GCS 單一目錄若包含超過 1,000,000 個物件時可能影響列舉速度，本專案依標案分冊管理，單一資料夾規模通常在數百至數千份，完全符合最佳架構規範。

---

## 相關參考文件 (Related Topics)

- [返回技術分類索引](../Index.md)
- [Gcloud RAG Agent 限制規範](../../02-ETL-and-operations/02-RAG-spec-and-limits/Gcloud-rag-agent-constraints.md)
- [企業身分識別與 GCS 存取指引](../../02-ETL-and-operations/03-Access-and-costs/Enterprise-identity-and-gcs-access.md)
- [Agent Enterprise Platform / Search 整合規範](Vertex-agent-enterprise-search-setup.md)
