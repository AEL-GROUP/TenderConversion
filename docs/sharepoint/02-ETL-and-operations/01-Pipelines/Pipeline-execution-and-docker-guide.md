# ETL 管道執行與 Docker 操作手冊 (Pipeline Execution and Docker Guide)

**適用對象：** 營運維運人員 / 資料工程師 / 投標專案經理
**文件狀態：** 現行版本
**最後審核：** 2026-10-05

> 備註：以下 Docker 設定與參數指令，於 2026 年 10 月 05 日審閱本文件時仍然有效。

---

## 簡要說明 (Summary)

本手冊說明如何執行投標文件轉換管道（`pdf_tender_pipeline.py`）。使用 Docker 映像檔可避免在本機分別安裝 Python、LibreOffice 及字型相依項目，並批次執行 Word 轉 PDF、PDF 重整、圖像降採樣及文件分塊。大小與頁數門檻由 `--max-mb` 和 `--max-pages` 參數控制。

---

## 對使用者或營運的影響 (Impact on Users & Operations)

- **簡化環境準備：** Docker 映像檔包含 headless LibreOffice 與所需字型，減少不同主機環境造成的差異。
- **依參數控制輸出規格：** 管道會檢查檔案大小與頁數，並依設定進行分塊；無法處理的例外會記錄於執行結果中。
- **降低處理中斷的影響：** 管道先寫入暫存位置，驗證後再置換輸出檔案，避免未完成的結果直接覆蓋已存在的檔案。

---

## Docker 快速開始 (Docker Quick Start)

### 1. 檔案放置 (Data Directory Setup)
專案目錄已配置好 `docker-compose.yml`。將待處理的投標資料夾置於本機的 `data/` 目錄中：

```text
TenderConversion/
├── data/
│   └── MyTender_Input/                # 放置待處理資料夾
│       ├── Volume 1/
│       │   └── Conditions.docx
│       └── Volume 2/
│           └── Oversized_Drawings.pdf
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── pdf_tender_pipeline.py
```

### 2. 標準執行指令 (Standard Execution Command)

開啟 PowerShell 或 Bash 終端機，執行以下命令：

```powershell
docker compose run --rm tender-pipeline -i /data/MyTender_Input -o /data/MyTender_Final
```

執行時，管道會依序進行以下處理：
1. **STEP 1: Word 轉 PDF：** 使用 LibreOffice 將 `.doc` 與 `.docx` 轉成 PDF，並保留來源目錄結構。
2. **STEP 2: PDF 壓縮與最佳化：** 依參數處理 PDF 物件與高解析度圖像；已符合大小限制的檔案則依管道設定複製。
3. **STEP 3: 規格檢查：** 逐一檢查 PDF 的檔案大小與頁數。
4. **STEP 3b: 精確分塊 (Exact Size Chunking)：** 超出 `--max-mb` 或 `--max-pages` 設定的文件會嘗試切分為 `_chunk-1.pdf`、`_chunk-2.pdf` 等檔案。
5. **STEP 4 & 5: 摘要報告與檔案完整性檢查：** 顯示處理統計，並檢查輸出檔案數量。

### 3. 收集成果 (Collect Output)
處理完成後，輸出文件會存放在本機 `data/MyTender_Final/`，並保留來源目錄結構。

---

## 常用參數組合與應用場景 (Common Recipes)

管道支援豐富的命令列參數，可針對不同工作場景進行彈性切換：

### 場景 1：輸入目錄全為 PDF（無 Word 檔）
加上 `--pdf-only` 可略過 Word 轉檔步驟：
```powershell
docker compose run --rm tender-pipeline -i /data/MyTender_PDFs --pdf-only -o /data/MyTender_Final
```

### 場景 2：數千份檔案的快速批次模式（WSL / 共享網路磁碟專用）
若來源目錄含有大量已符合限制的檔案，可加上 `--skip-copy` 略過這些檔案的複製，只將需要處理的超標檔案輸出，以減少磁碟 I/O：
```powershell
docker compose run --rm tender-pipeline -i /data/MyTender --pdf-only --skip-copy --quiet --silent -o /data/MyTender_Final
```
> **注意：** 使用 `--skip-copy` 時，輸出資料夾只會包含經壓縮或分塊處理的文件；已符合限制的文件仍留在來源目錄。

### 場景 3：CI/CD 自動化批次執行（非交談模式）
在無人看守的排程或 CI/CD 流程中，可使用 `--silent` 自動繼續分塊，不必等待終端機輸入確認：
```powershell
docker compose run --rm tender-pipeline -i /data/MyTender --silent -o /data/MyTender_Final
```

### 場景 4：僅驗證與分塊，完全不做圖像重編碼
若不需要重新編碼圖像，只想檢查規格並切分超限文件，可使用以下命令：
```powershell
docker compose run --rm tender-pipeline -i /data/MyTender --pdf-only --skip-compression --silent -o /data/MyTender_Final
```

### 場景 5：高解析度工程圖紙模式（更高 OCR 精確度）
若圖紙包含細小文字標註，可將目標 DPI 設為 300，並將 JPEG 品質設為 85：
```powershell
docker compose run --rm tender-pipeline -i /data/MyTender -o /data/MyTender_Final --dpi 300 -q 85 --max-mb 50.0
```

---

## 完整參數速查表 (CLI Flags Reference)

| 旗標名稱 | 預設值 | 說明與最佳實踐 |
|---|---|---|
| `-i`, `--input` | `/data/my_tender_docs` | 來源文件目錄路徑。 |
| `-o`, `--output` | `<source> compressed` | 輸出目標目錄路徑。 |
| `--max-mb` | `50.0` | 嚴格單檔體積上限 (MB)。預設 50.0 MB 符合 GCloud Agent Platform 限制。 |
| `--max-pages` | `500` | 嚴格單檔頁數上限。預設 500 頁符合 Document AI 解析上限。 |
| `--dpi` | `200` | 圖像重編碼的目標解析度；請依文件內容檢查輸出效果。 |
| `--dpi-threshold`| `1.5 x --dpi` | 觸發降採樣的有效 DPI 門檻（必須大於 `--dpi`）。 |
| `-q`, `--quality` | `80` | JPEG 壓縮品質係數（1~100）。請抽查輸出圖像是否清晰。 |
| `--workers` | `2` | 並行壓縮程序數。高核心數機器可適度調大，但需留意記憶體上限。 |
| `--pdf-only` | `關閉` | 跳過 Word 轉 PDF 步驟，直接對既有 PDF 實施處理。 |
| `--silent` | `關閉` | 自動執行分塊，無需交談式輸入確認（自動化排程必備）。 |
| `--no-chunk` | `關閉` | 停用自動分塊功能。超標文件會被標記警告但不會切分。 |
| `--skip-copy` | `關閉` | 略過符合限制檔案的複製，只輸出經處理的超標文件（適用於較慢的檔案系統）。 |
| `--skip-compression` | `關閉` | 跳過圖像壓縮步驟，僅進行規格檢驗與切分。 |
| `--quiet` | `關閉` | 簡潔輸出模式，僅顯示進度摘要與統計，隱藏逐檔 PASS 訊息。 |

---

## 本機無 Docker 執行方式 (Local Python Setup)

若未使用 Docker，也可以在已安裝必要相依項目的本機 Python 環境執行：

### 前置需求
1. Python 3.12 以上。
2. 作業系統安裝 LibreOffice 並加入 PATH（若僅使用 `--pdf-only` 則非必要）。

### 安裝相依套件與執行
```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
python pdf_tender_pipeline.py -i ./data/MyTender -o ./data/MyTender_Final --pdf-only
```

---

## 已知限制或待確認項目 (Pending Confirmations & Limitations)

- **待確認：** 生產環境 Docker 主機的 CPU 與記憶體規格，據此調整 `--workers`。
- **限制：** LibreOffice 在不同作業系統上的執行環境可能有所差異。若需統一執行環境，可使用 Docker；轉檔結果仍應抽樣檢查。

---

## 相關參考文件 (Related Topics)

- [返回營運分類索引](../Index.md)
- [Gcloud RAG Agent 限制規範](../02-RAG-spec-and-limits/Gcloud-rag-agent-constraints.md)
- [常見問題與故障排除手冊](../04-Support/Troubleshooting-and-faq.md)
- [壓縮與分塊演算法技術細節](../../03-Technical-reference/01-Architecture/Compression-and-chunking-algorithms.md)
