# 投標文件 RAG ETL 知識庫導覽 (Tender Conversion RAG ETL Knowledge Base)

本知識庫說明企業投標文件轉換管道（Tender Conversion ETL Pipeline），以及與 **Google Cloud Agent Enterprise Platform**（GCS 儲存空間與 RAG Agent 檢索庫）的交付關係。文件依 SharePoint 文件庫的三層架構整理，供業務主管、投標團隊及技術維運人員查閱。

> 備註：以下技術規格、架構設計與雲端限制，於 2026 年 10 月 05 日審閱本文件時仍然有效。

---

## 知識庫核心架構與目錄樹 (Documentation Hierarchy)

```text
docs/sharepoint/
├── README.md                                             # 本導覽地圖 (KB Navigation Map)
├── _Topic-template.md                                    # SharePoint 專題標準範本
├── 01-Overview/                                          # [大分類] 服務概覽 (扁平不分子層)
│   ├── Index.md                                          # 概覽模組索引
│   └── Service-overview.md                               # 服務綜覽與 Gcloud Agent 邊界說明
├── 02-ETL-and-operations/                                # [大分類] 營運與作業指引 (子分類嵌套)
│   ├── Index.md                                          # 營運分類索引
│   ├── 01-Pipelines/                                     # 資料管道作業手冊
│   │   ├── Document-filtering-and-prep-guide.md          # 投標原始文件篩選指引 (filter_extensions.py)
│   │   └── Pipeline-execution-and-docker-guide.md        # ETL 管道執行與 Docker 操作手冊
│   ├── 02-RAG-spec-and-limits/                           # RAG 規範與雲端限制
│   │   ├── Gcloud-rag-agent-constraints.md               # Gcloud Agent Platform GCS 與 RAG 限制規範
│   │   └── Document-quality-and-verification-checklist.md # 投標文件品質檢核與驗證清單
│   ├── 03-Access-and-costs/                              # 權限與成本架構
│   │   ├── Enterprise-identity-and-gcs-access.md         # 企業身分識別 (Entra ID) 與 GCS 存取指引
│   │   └── Cloud-resource-and-operating-costs.md         # 雲端儲存與運算成本分析
│   └── 04-Support/                                       # 支援與常見問題
│       └── Troubleshooting-and-faq.md                    # 故障排除手冊與常見問題解答
└── 03-Technical-reference/                               # [大分類] 技術專題參考 (子分類嵌套)
    ├── Index.md                                          # 技術專題索引
    ├── 01-Architecture/                                  # 核心架構與演算法
    │   ├── System-architecture-and-data-flow.md          # 系統架構與 RAG 資料流設計
    │   └── Compression-and-chunking-algorithms.md        # 無失真重整、圖像降採樣與貪婪分塊算法
    ├── 02-GCP-and-rag-integration/                       # Google Cloud 整合技術
    │   ├── Gcs-storage-topology-and-sync.md              # GCS 儲存拓撲與批次同步機制
    │   └── Vertex-agent-enterprise-search-setup.md       # RAG 資料集交付規格與平台限制
    ├── 03-Testing-and-deployment/                        # 部署與驗證
    │   ├── Environment-setup-and-dockerfile.md           # 本機與 Docker 容器化配置指南
    │   └── Test-suite-and-validation-guide.md            # 自動化測試與回歸檢驗指引
    └── 04-Feature-notes/                                 # 專題深入技術筆記
        ├── Libreoffice-headless-conversion.md            # LibreOffice 無周邊 Word 轉換實作筆記
        └── Oversized-page-rescue-mechanism.md            # 超大單頁應急點陣化救援機制筆記
```

---

## 快速跳轉指引 (Quick Navigation)

### 1. 管理層與業務使用者 (Management & Business Users)
- 若想了解本專案的目的、商業價值及服務範圍，請閱讀[服務概覽](01-Overview/Service-overview.md)。
- 若想了解投標文件匯入 RAG 前須符合的檔案大小、頁數及格式限制，請閱讀 [Gcloud RAG Agent 限制規範](02-ETL-and-operations/02-RAG-spec-and-limits/Gcloud-rag-agent-constraints.md)。
- 若想了解雲端資源的成本結構，請閱讀[雲端資源與運算成本分析](02-ETL-and-operations/03-Access-and-costs/Cloud-resource-and-operating-costs.md)。

### 2. 投標工程師與內容管理員 (Tender Engineers & Operators)
- 若要從招標資料夾中篩選 Word 與 PDF 檔案，請閱讀[文件篩選指引](02-ETL-and-operations/01-Pipelines/Document-filtering-and-prep-guide.md)。
- 若要在本機或伺服器上執行 Docker，進行轉檔與分塊，請閱讀[管道執行與 Docker 操作手冊](02-ETL-and-operations/01-Pipelines/Pipeline-execution-and-docker-guide.md)。
- 若要確認交付前的品質要求，請閱讀[投標文件品質檢核清單](02-ETL-and-operations/02-RAG-spec-and-limits/Document-quality-and-verification-checklist.md)。
- 若要了解 GCS 與 Agent 平台的存取權限，請閱讀[企業身分識別與存取指引](02-ETL-and-operations/03-Access-and-costs/Enterprise-identity-and-gcs-access.md)。
- 若遇到轉檔失敗、檔案過大或路徑錯誤，請參閱[常見問題與故障排除](02-ETL-and-operations/04-Support/Troubleshooting-and-faq.md)。

### 3. 架構師與 DevOps 工程師 (Architects & Cloud Engineers)
- 若要了解系統內部資料流程及 GCS 交付邊界，請閱讀[系統架構與資料流](03-Technical-reference/01-Architecture/System-architecture-and-data-flow.md)。
- 若要了解 50 MB 與 500 頁限制下的壓縮和分塊演算法，請閱讀[壓縮與分塊演算法](03-Technical-reference/01-Architecture/Compression-and-chunking-algorithms.md)。
- 若要了解 GCS 儲存結構與同步方式，請閱讀[GCS 儲存拓撲與同步](03-Technical-reference/02-GCP-and-rag-integration/Gcs-storage-topology-and-sync.md)。
- 若要了解測試套件及其驗證範圍，請閱讀[測試套件與驗證指引](03-Technical-reference/03-Testing-and-deployment/Test-suite-and-validation-guide.md)。

---

## SharePoint 使用說明與相容性注意事項

1. **不依賴文件庫外部連結：** 本知識庫的內部連結均使用相對路徑，目標位於 `docs/sharepoint/` 範圍內，整個資料夾可獨立上傳至 SharePoint。
2. **ASCII 路徑：** 檔案與資料夾名稱使用 ASCII 字元及連字號，降低 SharePoint 或 Teams 處理路徑編碼時造成連結問題的風險。
3. **Markdown 預覽與編輯：** 可在 SharePoint 支援的介面中預覽及編輯 `.md` 文件；實際功能取決於租用戶設定與目前使用的 SharePoint 介面。
