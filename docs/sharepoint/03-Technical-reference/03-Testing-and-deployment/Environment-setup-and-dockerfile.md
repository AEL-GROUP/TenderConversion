# 本機與 Docker 容器化配置指南 (Environment Setup and Dockerfile Guide)

**適用對象：** DevOps 工程師 / 系統管理員 / 後端開發人員
**文件狀態：** 現行版本
**最後審核：** 2026-10-05

> 備註：以下容器化方式與建置參數，於 2026 年 10 月 05 日審閱本文件時仍然適用。

---

## 簡要說明 (Summary)

本文件說明 `TenderConversion` 專案的 `Dockerfile`、`docker-compose.yml` 及系統字型相依項目，並介紹如何使用容器執行投標文件處理管道。容器化有助於讓不同主機使用一致的執行環境；文件版面仍可能受來源字型及實際轉換結果影響。

---

## Dockerfile 架構解構 (Dockerfile Architecture)

本專案以 `python:3.12-slim` 作為基底映像檔，並將安裝相依套件與複製應用程式程式碼分開，以利重用建置快取：

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

### 設定說明
1. **字型相依項目：** 映像檔安裝 `fonts-dejavu-core` 與 `fonts-liberation`，供容器中的 LibreOffice 使用。來源文件若使用未安裝的字型，仍可能出現字型替代及版面差異。
2. **控制映像檔大小：** 建置時使用 `--no-install-recommends`，並在安裝後清除 `/var/lib/apt/lists/*`，避免保留不必要的套件索引資料。

---

## Docker Compose 磁碟掛載設計 (Volume Mount Strategy)

`docker-compose.yml` 預設會將主機的資料夾掛載至容器內的 `/data`：

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

### 使用建議
- **執行後移除容器：** 使用 `--rm` 執行一次性工作，例如 `docker compose run --rm tender-pipeline ...`，讓容器在工作結束後自動移除。
- **檢查掛載權限：** 請確認容器對掛載的主機目錄具有所需的讀寫權限；實際權限行為會因作業系統及 Docker 設定而異。

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
