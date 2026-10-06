# GCS 儲存拓撲與批次同步機制 (GCS Storage Topology and Synchronization)

**適用對象：** 雲端維運工程師 (Cloud DevOps) / 資料架構師 / 系統整合人員
**文件狀態：** 現行版本
**最後審核：** 2026-10-05

> 備註：以下 GCS 目錄範例與同步指令，於 2026 年 10 月 05 日審閱本文件時仍然適用；實際 Bucket、路徑及同步方式待確認。

---

## 簡要說明 (Summary)

本文件提供投標文件經 ETL 處理後存放於 **Google Cloud Storage（GCS）** 的目錄範例，以及使用 `gcloud storage rsync` 或 `gsutil` 進行批次同步的參考方式。文中的 Bucket 名稱與路徑均為示例，不代表本專案已採用特定 GCS 結構或平台索引流程；正式環境的設定仍待確認。

---

## GCS 儲存庫結構拓撲 (Bucket Directory Topology)

以下為保留標案與冊別目錄結構的示例。實際 GCS 路徑及下游使用方式，應依專案部署設定確認：

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

### 保留目錄結構的用途
1. **方便辨識來源：** 以標案及冊別分類，可協助維護人員理解文件所在位置。
2. **支援後續管理：** 不同標案可分別整理；是否另行設定存取權限或生命週期規則，須依實際環境規劃。

---

## 批次同步指令指引 (Synchronization Commands)

若已確認本機輸出資料夾及 GCS 目的地，工程師可參考以下方式使用 Google Cloud SDK 執行同步：

### 推薦指令：使用現代 `gcloud storage rsync`
```powershell
gcloud storage rsync -r ./data/MyTender_Final gs://<BUCKET_NAME>/<TENDER_PATH>
```

### 傳統指令：使用 `gsutil -m rsync`
```powershell
gsutil -m rsync -r ./data/MyTender_Final gs://<BUCKET_NAME>/<TENDER_PATH>
```

### 關鍵參數解說：
- `-r` (Recursive)：遞迴同步所有子資料夾，確保分冊結構不被攤平。
- `-d` (Delete)：若來源目錄中已刪除某些檔案，會同步刪除 GCS 上的對應物件。此選項具有刪除效果；請先確認來源、目的地及刪除範圍，否則不要使用。
- `-m` (Multi-threading)：並行上傳多個檔案，顯著縮短同步時間。

---

## 儲存類別與生命週期管理 (Storage Class & Lifecycle)

如需設定 GCS 儲存類別或生命週期規則，請由雲端管理人員依資料存取需求及保留政策評估。下表僅供規劃時參考：

| 資料型態 | 建議儲存類別 (Storage Class) | 存取特性與考量 |
|---|---|---|
| **進行中標案 (Active Tenders)** | `Standard`（標準儲存） | 適用於存取較頻繁的資料；實際選擇請依平台讀取需求評估。 |
| **已截標/歷史標案 (> 180 天)** | `Nearline` | 查詢頻率降低，儲存費用減半，讀取延遲仍可接受。 |
| **封存檔案 (> 365 天)** | `Coldline` 或 `Archive` | 適用於較少存取的資料；選用前請確認存取頻率及相關費用。 |

---

## 已知限制或待確認項目 (Pending Confirmations & Limitations)

- **待確認：** 正式 Google Cloud 專案 ID（`<PROJECT_ID>`）與 GCS Bucket 正式名稱。
- **待確認：** 實際使用的同步身分及其所需 GCS 權限。
- **待確認：** 目標 Bucket 的物件數量及目錄規模；請依實際用量評估管理方式。

---

## 相關參考文件 (Related Topics)

- [返回技術分類索引](../Index.md)
- [Gcloud RAG Agent 限制規範](../../02-ETL-and-operations/02-RAG-spec-and-limits/Gcloud-rag-agent-constraints.md)
- [企業身分識別與 GCS 存取指引](../../02-ETL-and-operations/03-Access-and-costs/Enterprise-identity-and-gcs-access.md)
- [Agent Enterprise Platform / Search 整合規範](Vertex-agent-enterprise-search-setup.md)
