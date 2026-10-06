# 常見問題與故障排除手冊 (Troubleshooting and FAQ Guide)

**適用對象：** 全體操作人員 / 投標工程師 / 技術支援團隊 / 營運管理員
**文件狀態：** 現行版本
**最後審核：** 2026-10-05

> 備註：以下問題現象、錯誤訊息及排查方式，於 2026 年 10 月 05 日審閱本文件時仍然有效。

---

## 簡要說明 (Summary)

本文件整理執行投標文件 ETL、Docker 容器作業及交付處理成果時可能遇到的問題，並提供相應的排查方向。雲端平台的索引及 Agent 設定不屬於本管道範圍；如遇到平台端錯誤，請依目標環境的操作流程處理。

---

## 快速故障排查決策樹 (Troubleshooting Decision Tree)

```mermaid
graph TD
    Issue[發生作業異常] --> IsDocker{是否為 Docker 執行問題?}
    IsDocker -->|是| CheckDocker[檢查 Docker 記憶體 / WSL 檔案鎖定]
    IsDocker -->|否| IsPipeline{是否為 ETL 管道報錯?}
    IsPipeline -->|是| CheckPipeline[檢查 LibreOffice / 超大單頁 / 檔案大小限制]
    IsPipeline -->|否| CheckCloud[依目標環境排查雲端交付或平台問題]
```

---

## 常見問題與故障排除矩陣 (Troubleshooting Matrix)

### 1. Docker 與本機檔案系統問題 (Docker & Filesystem Issues)

#### Q1：在 Windows / WSL 執行 Docker 時出現 `File exists` 錯誤，或無法刪除目錄，該如何處理？
- **可能原因：** 掛載磁碟的檔案同步延遲，或有其他程式正在使用該目錄中的檔案。
- **處置步驟：**
  1. 確認目標路徑正確，並備份仍需保留的內容。以下命令會刪除指定的輸出資料夾：
     ```powershell
     docker run --rm -v "${PWD}/data:/data" python:3.12-slim python -c "import shutil; shutil.rmtree('/data/MyTender_Final', ignore_errors=True)"
     ```
  2. 若仍被鎖定，確認本機未有任何 Adobe Acrobat、Word 或檔案總管開啟該目標資料夾中的檔案。

#### Q2：使用 `--skip-copy` 後，輸出資料夾是空的或只包含少量檔案，這是否正常？
- **說明：** 這是 `--skip-copy` 的預期行為。此選項會略過已符合大小與頁數限制的檔案，因此輸出資料夾只包含經壓縮或分塊處理的檔案；其他檔案仍留在來源目錄。
- **處置步驟：**
  - 若需要完整的投標成果目錄，請移除 `--skip-copy` 後重新執行。
  - 或者將輸出目錄中切分好的分塊檔案，手動覆蓋回原本的來源資料夾中。

---

### 2. 轉檔與分塊運算問題 (Pipeline & Chunking Issues)

#### Q3：為什麼壓縮後的檔案反而稍微變大？
- **可能原因：** 已高度最佳化的 PDF 在重新整理後，可能因中繼資料或物件結構改變而略為增加檔案大小。
- **處置機制：**
  - 管道會比較原始檔與處理後的有效候選檔，並選用體積較小的結果。
  - 未超過設定大小門檻的檔案，預設不會進入壓縮流程。

#### Q4：日誌出現 `Oversized pages rescued`，代表什麼？
- **說明：** 某份文件的單一頁面超出設定的大小門檻，無法再依頁數切分，因此管道啟動單頁救援流程。
- **處置機制：**
  - 管道會啟動超大單頁救援機制（`_rescue_oversized_page`），依序嘗試 180、150、120、96、72 及 50 DPI 的點陣化設定，直到符合大小門檻或所有設定都嘗試完畢。
  - **注意事項：** 救援後的頁面會轉為點陣圖，因此該頁的原生文字搜尋能力會受限。請確認救援結果仍可辨識，並依交付規格決定是否使用。

#### Q5：本機執行 Python 時出現 `LibreOffice is not installed or not in system PATH`，該如何處理？
- **處置步驟：**
  - 強烈建議直接改用 Docker Compose 執行（容器內已包含完整 LibreOffice 環境）。
  - 若堅持本機執行且輸入資料夾全是 PDF，請務必加上 `--pdf-only` 旗標以跳過 Word 轉換階段。

---

### 3. Google Cloud 與 RAG Agent 整合問題 (Cloud & RAG Issues)

#### Q6：文件交付至 GCS 後，平台顯示解析警告或失敗，該如何處理？
- **處置步驟：**
  1. **檢查大小：** 確認檔案是否超過目標環境的大小限制。
  2. **檢查頁數：** 確認文件是否超過目標環境的頁數限制。
  3. **檢查密碼：** 確認該 PDF 是否被來源機關加蓋唯讀密碼，導致 Document AI 無法剖析。
  4. **檢查路徑：** 確認 GCS 物件路徑及檔名符合目標環境的要求。

#### Q7：下游檢索服務找不到某個分冊的資訊，該如何處理？
- **處置步驟：**
  1. 檢查原始目錄在執行 `filter_extensions.py` 時，該分冊是否因為副檔名非 `.pdf` / `.docx`（例如被打包在 `.zip` 內）而被過濾掉。
  2. 確認文件已交付至預期位置，並向平台管理者確認後續處理或索引狀態。

---

## 異常回報與技術支援升級路徑 (Escalation Path)

若無法自行排除管線問題，請整理以下資訊後聯絡技術維護團隊：

1. **收集日誌：** 保留終端機的完整輸出（從 `STARTING PIPELINE` 到 `SUMMARY STATISTICS`）。
2. **記錄問題檔案：** 記下發生錯誤的檔名、原始檔案大小及頁數。
3. **聯繫內部窗口：**
   - **投標業務支援負責人：** 待確認
   - **DevOps / 雲端維運團隊：** 待確認
   - **問題通報郵箱：** 待確認

---

## 相關參考文件 (Related Topics)

- [返回營運分類索引](../Index.md)
- [ETL 管道執行與 Docker 操作手冊](../01-Pipelines/Pipeline-execution-and-docker-guide.md)
- [Gcloud RAG Agent 限制規範](../02-RAG-spec-and-limits/Gcloud-rag-agent-constraints.md)
- [投標文件品質檢核與驗證清單](../02-RAG-spec-and-limits/Document-quality-and-verification-checklist.md)
