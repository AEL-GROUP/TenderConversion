# 投標文檔 RAG ETL 知識庫導覽地圖 (Tender Conversion RAG ETL Knowledge Base)

本知識庫專為企業投標文件轉換處理（Tender Conversion ETL Pipeline）及 **Google Cloud Agent Enterprise Platform**（GCS 儲存庫與 RAG Agent 檢索庫）整合所建立，遵循 SharePoint 現代文件庫三層架構規範，兼顧業務主管、投標團隊與技術維運人員之查閱需求。

> 備註：以下技術規格、架構設計與雲端限制於 2026 年 10 月 05 日審核此文檔時仍然有效。

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
│   ├── 01-Pipelines/                                     # 數據管道作業手冊
│   │   ├── Document-filtering-and-prep-guide.md          # 投標原始文檔篩選指引 (filter_extensions.py)
│   │   └── Pipeline-execution-and-docker-guide.md        # ETL 管道執行與 Docker 操作手冊
│   ├── 02-RAG-spec-and-limits/                           # RAG 規範與雲端限制
│   │   ├── Gcloud-rag-agent-constraints.md               # Gcloud Agent Platform GCS 與 RAG 限制規範
│   │   └── Document-quality-and-verification-checklist.md# 投標文件品質檢核與驗證清單
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
- 想了解本專案為何而建、能帶來什麼商業價值與 RAG 賦能？請閱讀 [服務概覽 (01-Overview/Service-overview.md)](01-Overview/Service-overview.md)。
- 想了解投標文件入庫 RAG 的檔案大小、頁數上限與格式限制？請閱讀 [Gcloud RAG Agent 限制規範 (02-ETL-and-operations/02-RAG-spec-and-limits/Gcloud-rag-agent-constraints.md)](02-ETL-and-operations/02-RAG-spec-and-limits/Gcloud-rag-agent-constraints.md)。
- 想了解雲端資源使用成本與授權費用？請閱讀 [雲端資源與運算成本分析 (02-ETL-and-operations/03-Access-and-costs/Cloud-resource-and-operating-costs.md)](02-ETL-and-operations/03-Access-and-costs/Cloud-resource-and-operating-costs.md)。

### 2. 投標工程師與內容管理員 (Tender Engineers & Operators)
- 如何從龐雜的招標目錄中提取 Word 與 PDF 檔案？請閱讀 [文檔篩選指引 (02-ETL-and-operations/01-Pipelines/Document-filtering-and-prep-guide.md)](02-ETL-and-operations/01-Pipelines/Document-filtering-and-prep-guide.md)。
- 如何在本機或伺服器執行 Docker 進行轉檔與自動分塊？請閱讀 [管道執行與 Docker 操作手冊 (02-ETL-and-operations/01-Pipelines/Pipeline-execution-and-docker-guide.md)](02-ETL-and-operations/01-Pipelines/Pipeline-execution-and-docker-guide.md)。
- 交付前有哪些品質指標必須確認？請閱讀 [投標文件品質檢核清單 (02-ETL-and-operations/02-RAG-spec-and-limits/Document-quality-and-verification-checklist.md)](02-ETL-and-operations/02-RAG-spec-and-limits/Document-quality-and-verification-checklist.md)。
- 如何申請 GCS 與 Agent 主控台權限？請閱讀 [企業身分識別與存取指引 (02-ETL-and-operations/03-Access-and-costs/Enterprise-identity-and-gcs-access.md)](02-ETL-and-operations/03-Access-and-costs/Enterprise-identity-and-gcs-access.md)。
- 遇到轉檔失敗、檔案過大或路徑錯誤時如何處理？請閱讀 [常見問題與故障排除 (02-ETL-and-operations/04-Support/Troubleshooting-and-faq.md)](02-ETL-and-operations/04-Support/Troubleshooting-and-faq.md)。

### 3. 架構師與 DevOps 工程師 (Architects & Cloud Engineers)
- 系統內部資料流與 GCS / Agent Builder 架構？請閱讀 [系統架構與 RAG 資料流 (03-Technical-reference/01-Architecture/System-architecture-and-data-flow.md)](03-Technical-reference/01-Architecture/System-architecture-and-data-flow.md)。
- 50MB 嚴格邊界壓縮與貪婪分塊算法？請閱讀 [壓縮與分塊演算法 (03-Technical-reference/01-Architecture/Compression-and-chunking-algorithms.md)](03-Technical-reference/01-Architecture/Compression-and-chunking-algorithms.md)。
- GCS 儲存拓撲、生命週期與 Agent 資料庫同步？請閱讀 [GCS 儲存拓撲與同步 (03-Technical-reference/02-GCP-and-rag-integration/Gcs-storage-topology-and-sync.md)](03-Technical-reference/02-GCP-and-rag-integration/Gcs-storage-topology-and-sync.md)。
- 單元測試套件與整合測試？請閱讀 [測試套件與驗證指引 (03-Technical-reference/03-Testing-and-deployment/Test-suite-and-validation-guide.md)](03-Technical-reference/03-Testing-and-deployment/Test-suite-and-validation-guide.md)。

---

## SharePoint 使用說明與相容性保證

1. **零外部依賴 (100% Self-Contained)：** 本文檔庫內所有超連結均使用相對路徑，完全閉環於 `docs/sharepoint/` 之內，保證整包上傳至 SharePoint 文件庫時絕不產生死連結。
2. **ASCII 檔案路徑：** 檔案名稱與目錄結構均為 ASCII 安全字元（連字號連接），避免微軟 SharePoint 網頁端或 Teams 分享時因中文跳脫編碼（`%E4%B8%AD`）導致排版中斷。
3. **原生預覽與雙欄編輯：** SharePoint 現代頁面支援直接點擊 `.md` 檔案查閱，並可切換為左側 Markdown 代碼、右側即時渲染視窗進行線上更新。
