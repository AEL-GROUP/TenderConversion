# 營運與作業指引分類索引 (ETL and Operations Index)

本分類提供投標管理員、資料工程師及營運支援人員所需的作業指引，涵蓋資料前處理、ETL 管道執行、RAG 規格檢查及帳號權限管理。

---

## 目錄架構與主題索引 (Sub-Category Index)

### 01 - 資料管道作業手冊 (01-Pipelines)
說明如何篩選招標文件、轉換格式並執行批次處理：

| 文件名稱 | 適用對象 | 核心內容說明 | 狀態 |
|---|---|---|---|
| [投標原始文件篩選指引](01-Pipelines/Document-filtering-and-prep-guide.md) | 投標工程師、內容管理員 | 說明如何使用 `filter_extensions.py` 依副檔名篩選 `.doc`、`.docx`、`.pdf`，並保留原有目錄結構 | 現行版本 |
| [ETL 管道執行與 Docker 操作手冊](01-Pipelines/Pipeline-execution-and-docker-guide.md) | 營運維護、資料工程師 | 完整解說 Docker Compose 執行指令、參數組合應用場景與輸出收集流程 | 現行版本 |

### 02 - RAG 規範與雲端限制 (02-RAG-spec-and-limits)
整理 Google Cloud Agent Enterprise Platform 的技術限制及文件品質要求：

| 文件名稱 | 適用對象 | 核心內容說明 | 狀態 |
|---|---|---|---|
| [Gcloud RAG Agent 限制規範](02-RAG-spec-and-limits/Gcloud-rag-agent-constraints.md) | 專案經理、系統架構師 | 說明管道預設的檔案大小與頁數門檻，以及確認平台實際限制的方法 | 現行版本 |
| [投標文件品質檢核與驗證清單](02-RAG-spec-and-limits/Document-quality-and-verification-checklist.md) | 投標主管、品管人員 | 提供轉檔前、轉檔後及版面抽查所需的檢查項目 | 現行版本 |

### 03 - 權限與成本架構 (03-Access-and-costs)
說明企業身分驗證整合、GCS 存取權限及雲端資源成本：

| 文件名稱 | 適用對象 | 核心內容說明 | 狀態 |
|---|---|---|---|
| [企業身分識別與 GCS 存取指引](03-Access-and-costs/Enterprise-identity-and-gcs-access.md) | IT 管理員、資安主管 | 說明 Microsoft Entra ID 整合模式、GCP IAM 角色指派與管理人員授權直達路徑 | 現行版本 |
| [雲端資源與運算成本分析](03-Access-and-costs/Cloud-resource-and-operating-costs.md) | 財務審查、IT 主管 | 拆解 GCS 儲存、Document AI 解析、Vertex AI 檢索計費模式與優化節費效益 | 現行版本 |

### 04 - 支援與常見問題 (04-Support)
彙整常見維運問題、錯誤訊息及處理方式：

| 文件名稱 | 適用對象 | 核心內容說明 | 狀態 |
|---|---|---|---|
| [常見問題與故障排除手冊](04-Support/Troubleshooting-and-faq.md) | 全體操作人員、技術支援 | 針對 WSL 檔案鎖定、超大單頁、文字不可選、LibreOffice 崩潰等問題提供對照處置步驟 | 現行版本 |

---

## 相關參考文件 (Related Links)

- [返回根目錄導覽](../README.md)
- [前往服務概覽](../01-Overview/Service-overview.md)
- [前往技術專題參考](../03-Technical-reference/Index.md)
