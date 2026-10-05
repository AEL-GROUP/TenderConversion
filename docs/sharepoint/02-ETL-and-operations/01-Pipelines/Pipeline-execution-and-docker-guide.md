# ETL 管道執行與 Docker 操作手冊 (Pipeline Execution and Docker Guide)

**適用對象：** 營運維運人員 / 資料工程師 / 投標專案經理
**文件狀態：** 現行版本
**最後審核：** 2026-10-05

> 備註：以下 Docker 容器設定與參數指令於 2026 年 10 月 05 日審核此文檔時仍然有效。

---

## 簡要說明 (Summary)

本手冊提供執行投標文檔轉換核心管道（`pdf_tender_pipeline.py`）的標準指南。透過預先打包好的 Docker 映像檔，維運人員無需在本機配置複雜的 Python 3.12、LibreOffice 或字型環境，即可一鍵將招標 Word 檔高保真轉為 PDF、實施無損重整、DPI 圖像降採樣、並依據 **Google Cloud 50MB 與 500 頁限制** 實施精確分塊。

---

## 對使用者或營運的影響 (Impact on Users & Operations)

- **開箱即用與零環境依賴：** 封裝 headless LibreOffice 與完整中英文字型，徹底解決不同作業系統（Windows / macOS / Linux）字型缺失導致轉檔排版錯位之問題。
- **保證輸出合規：** 產出的所有 PDF 檔案百分之百保證小於 50.0 MB 且不超過 500 頁，可直接同步進入 Google Cloud Storage 供 RAG Agent 索引。
- **事務性安全機制：** 管道採暫存目錄雙重驗證後置換（Transactional Replacement），即使中途被強制中斷，亦不會破壞或污染原始來源目錄。

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

打開 PowerShell 或 Bash終端機，執行以下指令：

```powershell
docker compose run --rm tender-pipeline -i /data/MyTender_Input -o /data/MyTender_Final
```

執行過程中，管道將依序執行以下 5 個步驟：
1. **STEP 1: Word 轉 PDF：** 自動調用 LibreOffice 將所有 `.doc` 與 `.docx` 轉為對應結構的 `.pdf`。
2. **STEP 2: PDF 壓縮最佳化：** 對大於 50MB 之 PDF 實施物件重整與圖像 200 DPI 降採樣；小於 50MB 者直接快速複製。
3. **STEP 3: 規格合規驗證：** 逐一檢查所有 PDF 檔案之大小與頁數。
4. **STEP 3b: 嚴格分塊 (Exact Size Chunking)：** 超過 50MB 或 500 頁之文件，自動切分為符合規格之 `_chunk-1.pdf`, `_chunk-2.pdf`。
5. **STEP 4 & 5: 摘要報告與檔案完整性斷言：** 列印空間節省率與分塊總數，確保檔案未遺漏。

### 3. 收集成果 (Collect Output)
處理完成後，所有符合 RAG 規範的文件將自動輸出於本機 `data/MyTender_Final/`，原始目錄結構維持不變。

---

## 常用參數組合與應用場景 (Common Recipes)

管道支援豐富的命令列參數，可針對不同工作場景進行彈性切換：

### 場景 1：輸入目錄全為 PDF（無 Word 檔）
加上 `--pdf-only` 跳過 Word 偵測與 LibreOffice 初始化，大幅提升處理速度：
```powershell
docker compose run --rm tender-pipeline -i /data/MyTender_PDFs --pdf-only -o /data/MyTender_Final
```

### 場景 2：數千份檔案的快速批次模式（WSL / 共享網路磁碟專用）
若來源目錄有大量已小於 50MB 的合規檔案，加上 `--skip-copy` 可避免重複複製未超標檔案，僅針對超標檔案輸出分塊，大幅降低 I/O 等待時間：
```powershell
docker compose run --rm tender-pipeline -i /data/MyTender --pdf-only --skip-copy --quiet --silent -o /data/MyTender_Final
```
> **注意：** 使用 `--skip-copy` 時，輸出資料夾僅包含被壓縮或分塊的文件，未超標文件保留在來源目錄中。

### 場景 3：CI/CD 自動化批次執行（非交談模式）
在無人看守的排程工作或 CI/CD 流水線中，務必加上 `--silent`，當遇到超標檔案時自動分塊，不需等待使用者在終端機輸入確認：
```powershell
docker compose run --rm tender-pipeline -i /data/MyTender --silent -o /data/MyTender_Final
```

### 場景 4：僅驗證與分塊，完全不做圖像重編碼
若確認所有 PDF 的圖紙均已調適完成，僅需針對超長或超大頁數切分：
```powershell
docker compose run --rm tender-pipeline -i /data/MyTender --pdf-only --skip-compression --silent -o /data/MyTender_Final
```

### 場景 5：高解析度工程圖紙模式（更高 OCR 精確度）
對於細小工程文字標註為主的圖紙，可將目標 DPI 提升至 300，JPEG 品質設為 85：
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
| `--dpi` | `200` | 圖像重編碼之目標解析度。建議 200~300 DPI。 |
| `--dpi-threshold`| `1.5 x --dpi` | 觸發降採樣的有效 DPI 門檻（必須大於 `--dpi`）。 |
| `-q`, `--quality` | `80` | JPEG 壓縮品質係數（1~100）。80 為視覺品質與體積的最佳平衡。 |
| `--workers` | `2` | 並行壓縮程序數。高核心數機器可適度調大，但需留意記憶體上限。 |
| `--pdf-only` | `關閉` | 跳過 Word 轉 PDF 步驟，直接對既有 PDF 實施處理。 |
| `--silent` | `關閉` | 自動執行分塊，無需交談式輸入確認（自動化排程必備）。 |
| `--no-chunk` | `關閉` | 停用自動分塊功能。超標文件會被標記警告但不會切分。 |
| `--skip-copy` | `關閉` | 不複製合規小檔案，僅輸出處理過之超標文件（適用於慢速檔案系統）。 |
| `--skip-compression` | `關閉` | 跳過圖像壓縮步驟，僅進行規格檢驗與切分。 |
| `--quiet` | `關閉` | 簡潔輸出模式，僅顯示進度摘要與統計，隱藏逐檔 PASS 訊息。 |

---

## 本機無 Docker 執行方式 (Local Python Setup)

若環境未安裝 Docker，可於本機 Python 環境直接執行：

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

- **待確認：** 企業生產環境的 Docker 主機規格（CPU 核心數與記憶體大小），以便決定 `--workers` 的最佳設定值（建議每 Worker 保留 2GB RAM）。
- **限制：** LibreOffice 在 Windows 平台之執行路徑可能與 Linux 容器不同，強烈建議統一採用 Docker 方式執行以獲取最高的排版一致性。

---

## 相關參考文件 (Related Topics)

- [返回營運分類索引](../Index.md)
- [Gcloud RAG Agent 限制規範](../02-RAG-spec-and-limits/Gcloud-rag-agent-constraints.md)
- [常見問題與故障排除手冊](../04-Support/Troubleshooting-and-faq.md)
- [壓縮與分塊演算法技術細節](../../03-Technical-reference/01-Architecture/Compression-and-chunking-algorithms.md)
