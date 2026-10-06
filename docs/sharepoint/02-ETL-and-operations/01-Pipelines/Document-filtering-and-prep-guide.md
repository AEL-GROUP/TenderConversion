# 投標原始文件篩選指引 (Document Filtering and Preparation Guide)

**適用對象：** 投標工程師 / 內容管理員 / 資料前置作業人員
**文件狀態：** 現行版本
**最後審核：** 2026-10-05

> 備註：以下篩選流程與指令，於 2026 年 10 月 05 日審閱本文件時仍然有效。

---

## 簡要說明 (Summary)

大型工程招標案的原始資料夾可能包含數千至數萬個檔案，例如 CAD 圖檔 `.dwg`、Excel 試算表 `.xlsx`、壓縮檔 `.zip`、相片及 Word 暫存檔 `~$*.docx`。本指引介紹如何使用 `filter_extensions.py` 掃描目錄，篩選出供後續處理的 `.doc`、`.docx` 與 `.pdf` 檔案，並保留原有資料夾階層，作為 ETL 管道的輸入資料。

---

## 對使用者或營運的影響 (Impact on Users & Operations)

- **減少無效處理：** 若未先篩選就將整個招標目錄交給轉換管道，程式可能花費時間掃描不相關檔案，也可能因處理暫存檔而產生錯誤。
- **保留文件脈絡：** 保留 `Volume 1/Section A/Contract.docx` 這類目錄結構，有助於 GCS 中的文件與原始冊別對應，方便追溯來源。
- **節省儲存空間：** 僅複製所需的文字文件與圖紙，減少本機及 Docker 容器所需的磁碟空間。

---

## 運作機制與指引 (Operational Workflow & Guidelines)

### 1. 運作流程圖解 (Workflow Diagram)

```text
[龐大招標目錄 MyTender/]
├── Volume 1/
│   ├── Contract.docx        ---> [選中保留]
│   ├── Cost_Estimate.xlsx   ---> [排除]
│   └── ~$Contract.docx      ---> [自動忽略暫存檔]
├── Volume 2/
│   ├── Specification.pdf    ---> [選中保留]
│   └── Site_Photo.jpg       ---> [排除]
└── Volume 3/
    └── Drawing.dwg          ---> [排除]
               │
               ▼ 執行 filter_extensions.py
               │
[純淨輸入目錄 MyTender_Filtered/]
├── Volume 1/
│   └── Contract.docx        (保持相對目錄)
└── Volume 2/
    └── Specification.pdf    (保持相對目錄)
```

### 2. 命令列旗標說明 (CLI Flags)

| 旗標名稱 | 縮寫 | 預設值 | 說明 |
|---|---|---|---|
| `--input-dir` | `-d` | 無 | 來源資料夾路徑，將遞迴掃描所有子目錄（與 `-f` 二選一）。 |
| `--file-list` | `-f` | 無 | 包含檔案路徑清單的文字檔（每行一筆，與 `-d` 二選一）。 |
| `--output-dir`| `-o` | `output_files` | 目標存放資料夾（自動建立不存在的目錄）。 |

### 3. 操作步驟範例 (Step-by-Step Instructions)

#### 情境 A：掃描資料夾並篩選 Word 與 PDF 檔案（建議做法）

開啟 Terminal 或 PowerShell，執行以下命令：

```powershell
python filter_extensions.py -d /data/Tender_Source -o /data/Tender_Prepared
```

程式會先列出來源目錄中找到的副檔名：
```text
Scanning directory recursively: /data/Tender_Source ...

--- Available Extensions Found ---
 1. .docx
 2. .dwg
 3. .pdf
 4. .xlsx
 5. .zip
----------------------------------

Enter extensions to keep (comma-separated, e.g., 'jpg, .png, pdf'):
```

在提示字元輸入要保留的副檔名（不區分大小寫，可輸入含點或不含點的格式）：
```text
docx, doc, pdf
```

程式會將符合條件的檔案複製到目標資料夾，並顯示處理進度與統計摘要：
```text
Copying files to '/data/Tender_Prepared'...

[COPIED] /data/Tender_Source/Volume 1/Contract.docx
[COPIED] /data/Tender_Source/Volume 2/Specification.pdf

--- Summary ---
Successfully copied: 128 file(s)
Files not found on disk: 0 file(s)
```

#### 情境 B：依預先整理的檔案清單篩選
若工務團隊已提供核准納入知識庫的檔案清單 `selected_files.txt`，可執行：
```powershell
python filter_extensions.py -f /data/selected_files.txt -o /data/Tender_Prepared
```

---

## 驗證檢查清單 (Validation Checklist)

將篩選結果交給下游轉換管道前，請確認以下事項：

- [ ] 輸出資料夾內的檔案僅包含 `.pdf`、`.docx` 與 `.doc` 檔案。
- [ ] 原始資料夾的層級（如 `Volume 1/`, `Addendum 01/`）完整保留。
- [ ] 未包含 Office 暫存隱藏檔（檔名以 `~$` 開頭）。
- [ ] 確認篩選後的檔案數量與預計納入知識庫的文件清單一致。

---

## 已知限制或待確認項目 (Pending Confirmations & Limitations)

- **待確認：** 是否需要將 `.rtf`、`.dotx` 等其他文件格式納入知識庫？目前管道預設支援 `.doc`、`.docx` 與 `.pdf`。
- **限制：** `filter_extensions.py` 會複製檔案，不會移動來源檔案。執行前請確認目標磁碟有足夠空間。

---

## 相關參考文件 (Related Topics)

- [返回營運分類索引](../Index.md)
- [ETL 管道執行與 Docker 操作手冊](Pipeline-execution-and-docker-guide.md)
- [Gcloud RAG Agent 限制規範](../02-RAG-spec-and-limits/Gcloud-rag-agent-constraints.md)
