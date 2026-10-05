# 企業身分識別與 GCS 存取授權指引 (Enterprise Identity and GCS Access Guide)

**適用對象：** 企業 IT 管理員 / 資安主管 / 投標專案負責人 / 雲端維運工程師
**文件狀態：** 現行版本
**最後審核：** 2026-10-05

> 備註：以下身分驗證整合架構與管理員指派路徑於 2026 年 10 月 05 日審核此文檔時仍然有效。

---

## 簡要說明 (Summary)

本指引說明大型企業混合雲架構下，**Microsoft Entra ID（前 Azure AD）** 身分目錄與 **Google Cloud Platform (GCP)** 之間的單一簽入（SSO）及權限指派機制。當業務部門或投標團隊需要新增同仁存取 Google Cloud Storage (GCS) 儲存庫或登入 Google Cloud Agent Enterprise Platform 主控台時，**90% 以上的管理操作均是在 Microsoft Entra admin center 完成**，而非要求管理員手動進入 GCP Console 新增個人 IAM 帳號。

---

## 核心身分架構：Entra ID 與 Google Cloud 聯盟模式 (Identity Architecture)

在現代企業資安架構中，Google Cloud 不直接存放員工帳號密碼，而是透過 **Workforce Identity Federation (WIF)** 或 SAML 2.0 / OIDC 與企業的核心目錄 **Microsoft Entra ID** 進行聯邦身分驗證：

```mermaid
flowchart LR
    subgraph EnterpriseIdentity[Microsoft Entra ID (Azure AD)]
        Admin[IT / 業務管理人員]
        EntraApp[企業應用程式<br/>Tender RAG Agent Platform]
        UserGroup[使用者與安全群組<br/>Tender-Engineers-Group]
    end

    subgraph GoogleCloud[Google Cloud Platform]
        WIF[Workforce Identity Federation / IAP]
        GCS[Google Cloud Storage<br/>gs://tender-rag-corpus/]
        AgentBuilder[Agent Enterprise Platform<br/>Search & RAG Engine]
    end

    Admin -->|1. 在 Entra ID 指派人員/群組| EntraApp
    EntraApp --> UserGroup
    UserGroup -->|2. SSO 企業登入 / 憑證轉譯| WIF
    WIF -->|3. 映射 IAM 角色| GCS
    WIF -->|3. 映射 IAM 角色| AgentBuilder
```

### 關鍵認知：為什麼切勿「只找 GCP 管理員」？
- **實務盲點：** 許多工程文件僅撰寫「聯絡 GCP 管理員開通權限」，導致業務主管無所適從。
- **真實維運：** 當新進投標工程師需存取知識庫時，由企業內部擁有 Entra ID 應用程式管理員（Application Administrator）權限之主管，直接在 Entra 主控台將該同仁加入對應群組即可立即生效。

---

## 管理員授權直達路徑 (Entra ID User Assignment Quick Link)

為省去在複雜主控台中多層翻找的困擾，授權管理人員可直接點擊以下專屬直達連結：

> 🔗 **Entra ID 使用者與群組名單直達連結（ManagedApp Users Blade）：**
> `https://entra.microsoft.com/#view/Microsoft_AAD_IAM/ManagedAppMenuBlade/~/Users/objectId/<SERVICE_PRINCIPAL_OBJECT_ID>/appId/<APP_ID>/`
> *(請將 `<SERVICE_PRINCIPAL_OBJECT_ID>` 與 `<APP_ID>` 替換為企業實際指派值，文檔中切勿填寫 Tenant ID 或 Client Secret)*

### 標準開通五步 SOP (Step-by-Step Assignment)

1. **登入入口：** 瀏覽並登入 [Microsoft Entra admin center](https://entra.microsoft.com/)。
2. **進入企業應用程式：** 於左側導覽列展開 **Identity (身分)** > **Applications (應用程式)** > **Enterprise applications (企業應用程式)**。
3. **搜尋專案應用：** 在搜尋框輸入專案專屬名稱（例如：`Tender RAG Agent Platform` 或 `待確認`）。
4. **進入使用者清單：** 點擊進入該應用程式，點選左側選單的 **Users and groups (使用者與群組)**。
5. **指派成員：**
   - 點選上方 **+ Add user/group (新增使用者/群組)**。
   - 搜尋同仁姓名或企業群組（建議優先以安全群組如 `SG-Tender-RAG-Editors` 指派）。
   - 選擇對應角色（如 `RAG-Knowledge-Manager` 或 `RAG-Viewer`），點選 **Assign (指派)**。

---

## Google Cloud IAM 角色映射對照表 (GCP IAM Role Mapping)

當使用者通過 Entra ID 驗證登入後，Google Cloud IAM 會自動依據 Entra ID Claim 映射至對應的雲端資源存取權限：

| 業務角色 | Entra ID 應用角色 | Google Cloud IAM 角色 | 具備之存取能力 |
|---|---|---|---|
| **投標資料管理員** | `RAG-Data-Admin` | `roles/storage.objectAdmin`<br/>`roles/discoveryengine.admin` | 可上傳、覆蓋 GCS 中的投標文件，觸發 Agent 重新索引，調整 RAG 提示詞與資料庫設定。 |
| **投標工程師 (維運)** | `RAG-Operator` | `roles/storage.objectViewer`<br/>`roles/discoveryengine.editor` | 可檢視 GCS 檔案內容，於 Agent 主控台測試問答、調整檢索過濾器。 |
| **一般終端使用者** | `RAG-User` | `roles/discoveryengine.viewer` | 僅能透過內部問答介面查詢投標文件，無法直接存取底層 GCS 原始檔。 |
| **自動化同步服務** | `Service Account` | `roles/storage.objectAdmin`<br/>`roles/discoveryengine.dataEditor` | 本機/CI 管道使用之專用服務帳號，執行 `gsutil rsync` 批次寫入檔案。 |

---

## 本機同步工具憑證指引 (Service Account Credentials for CLI Sync)

當工程師需使用 `gcloud` 或 `gsutil` 將處理後的資料夾同步至 GCS 時：

1. **優先採用個人短期憑證 (ADC)：**
   ```powershell
   gcloud auth login --update-adc
   ```
2. **自動化批次腳本採用無金鑰（Keyless）或環境變數：**
   在正式排程中，使用具備工作負載身分（Workload Identity）之服務帳號，避免在本地硬編碼 JSON 密鑰檔案。

---

## 已知限制或待確認項目 (Pending Confirmations & Limitations)

- **待確認：** 企業 Microsoft Entra ID 專屬 Enterprise Application 的正式名稱與 Application ID (`<APP_ID>`)。
- **待確認：** 企業負責審批新增 RAG 知識庫存取人員之 IT 窗口電子郵件。
- **待確認：** Google Cloud 接收端 GCS Bucket 的確切路徑（例如：`gs://corp-tender-rag-production/`）。
- **資安注意事項：** **嚴禁在任何 SharePoint 文檔或程式碼中記錄企業目錄租戶 ID (Tenant ID) 或任何私密金鑰 (Private Key)**，確保多方瀏覽安全。

---

## 相關參考文件 (Related Topics)

- [返回營運分類索引](../Index.md)
- [雲端資源與運算成本分析](Cloud-resource-and-operating-costs.md)
- [GCS 儲存拓撲與同步指引](../../03-Technical-reference/02-GCP-and-rag-integration/Gcs-storage-topology-and-sync.md)
- [Vertex Agent Enterprise Search 整合規範](../../03-Technical-reference/02-GCP-and-rag-integration/Vertex-agent-enterprise-search-setup.md)
