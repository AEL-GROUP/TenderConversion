# 本機與 Docker 容器化配置指南 (Environment Setup and Dockerfile Guide)

**適用對象：** DevOps 工程師 / 系統管理員 / 後端開發人員
**文件狀態：** 現行版本
**最後審核：** 2026-10-05

> 備註：以下容器化規範與建置參數於 2026 年 10 月 05 日審核此文檔時仍然有效。

---

## 簡要說明 (Summary)

本文件深入解構 `TenderConversion` 專案之 `Dockerfile`、`docker-compose.yml` 架構設計，以及系統字型相依性管理。詳細說明本專案如何打造輕量化、具備字型代換穩定性且環境完全隔離的投標文檔處理容器，為不同作業系統環境提供一致的轉檔成果。

---

## Dockerfile 架構解構 (Dockerfile Architecture)

本專案使用官方輕量級 `python:3.12-slim` 作為基底映像檔，並實施分層快取（Layer Caching）最佳化：

```dockerfile
# syntax=docker/dockerfile:1
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1

# --- 1. 系統層相依性 (System Dependencies) -----------------------------------
# libreoffice-writer + libreoffice-core: 提供 headless Word 轉 PDF 能力
# fonts-dejavu-core / fonts-liberation: 關鍵替代字型庫，確保未安裝特定微軟字型時排版不崩潰
RUN apt-get update && apt-get install -y --no-install-recommends \
        libreoffice-writer \
        libreoffice-core \
        fonts-dejavu-core \
        fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# --- 2. Python 套件層 (Pip Dependencies with Cache Optimization) -------------
# 單獨複製 requirements.txt，使應用程式代碼更動時不會破壞 pip 快取層
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --- 3. 應用程式程式碼層 (Application Code) -----------------------------------
COPY pdf_tender_pipeline.py .

# --- 4. 執行進入點 (Runtime Entrypoint) ---------------------------------------
ENTRYPOINT ["python3", "pdf_tender_pipeline.py"]
CMD ["-i", "/data/my_tender_docs", "--dpi", "200", "-q", "80", "--max-mb", "50.0"]
```

### 設計亮點：
1. **字型穩定性保證：** 安裝 `fonts-dejavu-core` 與 `fonts-liberation`，當原始 Word 檔案使用 Arial、Times New Roman 或 Helvetica 時，系統能無縫進行公制相容字型代換（Metric-compatible font substitution），避免版面文字溢出或頁數暴增。
2. **輕量安全：** 使用 `--no-install-recommends` 並於建置完畢後清除 `/var/lib/apt/lists/*`，有效將最終映像檔體積控制在最小範圍，降低潛在漏洞風險。

---

## Docker Compose 磁碟掛載設計 (Volume Mount Strategy)

在 `docker-compose.yml` 中，預設透過 Volume 將主機磁碟掛載至容器 `/data`：

```yaml
services:
  tender-pipeline:
    build:
      context: .
      dockerfile: Dockerfile
    image: tender-pdf-pipeline:latest
    container_name: tender-pdf-pipeline

    volumes:
      # 選項 1（預設）：統一掛載專案下的 ./data 目錄
      - ./data:/data
      # 選項 2（獨立輸出）：亦可直接掛載 Windows 本機實體路徑
      # - "D:/Tenders/FinalOutput:/output"

    command:
      - "-i"
      - "/data/MyTender_Source"
      - "-o"
      - "/data/MyTender_Output"
      - "--pdf-only"
      - "--silent"
      - "--dpi"
      - "200"
      - "-q"
      - "80"
      - "--max-mb"
      - "50.0"
```

### 最佳實踐建議：
- **容器臨時性（Ephemeral）：** 務必搭配 `--rm` 參數執行（`docker compose run --rm tender-pipeline ...`），在執行完畢後立即回收容器實例，避免累積龐大且未釋放的停止容器。
- **寫入權限：** 容器以 root 身分執行於 `/app`，掛載的主機目錄在 Windows Docker Desktop 上會自動對應 NTFS 權限，無需額外執行 `chown`。

---

## 已知限制或待確認項目 (Pending Confirmations & Limitations)

- **待確認：** 企業生產環境是否有私有容器倉庫（如 Google Artifact Registry `asia-docker.pkg.dev/<PROJECT_ID>/...`），未來可直接拉取預建映像檔而無需在本地每次重新 Build。
- **限制：** 若 Word 檔案中包含極特殊的商用中文字型（如特殊造字或未授權書法字型），在 Linux 容器中會降階代換為標準黑體或思源字型。

---

## 相關參考文件 (Related Topics)

- [返回技術分類索引](../Index.md)
- [ETL 管道執行與 Docker 操作手冊](../../02-ETL-and-operations/01-Pipelines/Pipeline-execution-and-docker-guide.md)
- [自動化測試與回歸檢驗指引](Test-suite-and-validation-guide.md)
- [LibreOffice 無周邊 Word 轉換實作筆記](../04-Feature-notes/Libreoffice-headless-conversion.md)
