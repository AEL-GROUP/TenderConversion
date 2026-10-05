# 投標原始文檔篩選作業指引 (Document Filtering and Preparation Guide)

**適用對象：** 投標工程師 / 內容管理員 / 資料前置作業人員
**文件狀態：** 現行版本
**最後審核：** 2026-10-05

> 備註：以下篩選流程與工具命令於 2026 年 10 月 05 日審核此文檔時仍然有效。

---

## 簡要說明 (Summary)

大型工程招標案的原始資料夾通常包含數千至數萬個混雜檔案（包含 CAD 工程圖 `.dwg`、Excel 試算表 `.xlsx`、壓縮包 `.zip`、相片與 Word 暫存檔 `~$*.docx`）。本指引說明如何利用輔助工具 `filter_extensions.py` 快速掃描目錄，**僅精確提取需要進入 RAG 知識庫的 `.doc`, `.docx` 與 `.pdf` 檔案**，同時 **100% 保持原本的資料夾階層結構**，作為下游 ETL 轉換管道的純淨輸入源。

---

## 對使用者或營運的影響 (Impact on Users & Operations)

- **避免無效運算與轉換失敗：** 若將整個招標目錄未經篩選直接丟入轉換管道，管線會耗費大量時間掃描無關的二進位檔案或在暫存檔上報錯。
- **維護 RAG 檢索語意層級：** 保持如 `Volume 1/Section A/Contract.docx` 的層級結構，能確保輸出至 GCS 時路徑階層不被打亂，維持 RAG Agent 的來源文件追溯力。
- **磁碟空間有效利用：** 僅複製關鍵文本與圖紙文檔，節省本機與 Docker 容器內的磁碟開銷。

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

#### 情境 A：掃描資料夾並提取 Word 與 PDF 檔案（最推薦做法）

開啟 Terminal 或 PowerShell，執行以下指令：

```powershell
python filter_extensions.py -d /data/Tender_Source -o /data/Tender_Prepared
```

執行後程式會先列出該目錄下所發現的所有副檔名清單：
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

在提示字元輸入欲保留的項目（大小寫不敏感，可帶或不帶點）：
```text
docx, doc, pdf
```

系統即會自動將符合條件的檔案複製至目標資料夾，並顯示處理進度與摘要統計：
```text
Copying files to '/data/Tender_Prepared'...

[COPIED] /data/Tender_Source/Volume 1/Contract.docx
[COPIED] /data/Tender_Source/Volume 2/Specification.pdf

--- Summary ---
Successfully copied: 128 file(s)
Files not found on disk: 0 file(s)
```

#### 情境 B：從預先整理的清單檔案篩選
若工務團隊已提供核可納入知識庫的檔案清單 `selected_files.txt`：
```powershell
python filter_extensions.py -f /data/selected_files.txt -o /data/Tender_Prepared
```

---

## 驗證檢查清單 (Validation Checklist)

在將篩選後的資料夾送入下游轉換管道前，請核對以下事項：

- [ ] 輸出資料夾內的檔案僅包含 `.pdf`、`.docx` 與 `.doc` 檔案。
- [ ] 原始資料夾的層級（如 `Volume 1/`, `Addendum 01/`）完整保留。
- [ ] 未包含 Office 暫存隱藏檔（檔名以 `~$` 開頭）。
- [ ] 確認篩選後的資料夾總檔案數與預期納入知識庫之文件清單一致。

---

## 已知限制或待確認項目 (Pending Confirmations & Limitations)

- **待確認：** 是否有非標準 Word 副檔名（如 `.rtf`、`.dotx`）需要納入 RAG 知識庫？現行管道預設支援 `.doc`、`.docx` 與 `.pdf`。
- **限制：** `filter_extensions.py` 執行的是「複製（Copy）」而非「移動（Move）」，請確保目標磁碟有充足的剩餘空間。

---

## 相關參考文件 (Related Topics)

- [返回營運分類索引](../Index.md)
- [ETL 管道執行與 Docker 操作手冊](Pipeline-execution-and-docker-guide.md)
- [Gcloud RAG Agent 限制規範](../02-RAG-spec-and-limits/Gcloud-rag-agent-constraints.md)
