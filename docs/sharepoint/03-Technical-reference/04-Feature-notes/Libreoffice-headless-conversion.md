# LibreOffice 無周邊 Word 轉換實作筆記 (LibreOffice Headless Conversion Notes)

**適用對象：** 核心開發人員 / 系統架構師
**文件狀態：** 現行版本
**最後審核：** 2026-10-05

> 備註：以下 LibreOffice CLI 呼叫細節與子程序處置機制於 2026 年 10 月 05 日審核此文檔時仍然有效。

---

## 簡要說明 (Summary)

本筆記記錄 `pdf_tender_pipeline.py` 在 `STEP 1` 中調用 **LibreOffice Headless Mode** 進行大量 `.doc` 與 `.docx` 轉檔時的實作考量、例外處理機制、以及與微軟原生 Office 轉檔相較之下的架構取捨。

---

## 核心調用實作剖析 (Core Implementation)

在 `pdf_tender_pipeline.py` 中，轉換 Word 檔案的核心函式如下：

```python
cmd = [
    "libreoffice",
    "--headless",        # 1. 啟用無視窗背景模式
    "--convert-to",
    "pdf",               # 2. 指定目標格式為標準 PDF
    str(doc_path),       # 3. 來源 Word 檔案路徑
    "--outdir",
    str(output_dir),     # 4. 輸出資料夾路徑
]

try:
    subprocess.run(
        cmd,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE
    )
    if expected_output.exists():
        print(f"  • Converted: {rel_path} -> {expected_output.relative_to(converted_root)}")
    else:
        print(f"  ❌ LibreOffice reported success but no output file found for {rel_path}")
except FileNotFoundError:
    print("\n[Error] LibreOffice is not installed or not in system PATH.")
    sys.exit(1)
except subprocess.CalledProcessError as e:
    stderr_text = e.stderr.decode(errors="replace") if e.stderr else "(no stderr)"
    print(f"  ❌ Failed to convert {doc_path.name}: {stderr_text}")
```

---

## 關鍵技術要點與踩坑記錄 (Key Insights & Gotchas)

### 1. 為什麼採用 headless LibreOffice 而非 python-docx / docx2pdf？
- **跨平台與免微軟 Office 授權：** `docx2pdf` 在後台依賴 Windows 的 COM 物件（Win32 COM Automation）啟動微軟 Word，在 Linux 伺服器與 Docker 容器中完全無法運作。
- **舊版格式支援：** 許多歷史投標檔案為二進位二進制檔案 `.doc`（Word 97-2003 格式），純 Python 函式庫（如 `python-docx`）完全無法讀取 `.doc`，而 LibreOffice 具備深厚的向下相容解析能力。
- **向量與複雜排版渲染：** 投標規範書包含複雜的頁首頁尾、目錄階層、嵌入表格與雙欄編排，LibreOffice 的排版渲染引擎成熟度遠高於簡易輕量開源套件。

### 2. 子程序異常與假性成功防禦 (False Positive Defense)
- **現象：** LibreOffice 在極端損毀的 Word 檔案上，有時回傳 Exit Code `0`，但實際上並未在輸出目錄產生目標 `.pdf`。
- **管道防禦機制：** 管道不單純相信子程序的結束狀態碼，而是在子程序結束後強制執行 `if expected_output.exists():` 檔案實體確認，確保下游步驟不會因缺失檔案而拋出空指標例外。

### 3. 字型代換與頁碼變動保護
- 在轉檔過程中，若來源 Word 所使用之字型在主機環境不存在，LibreOffice 會自動啟用字型代換。本專案之 Docker 映像檔預先安裝 `fonts-liberation`，其字元寬度與微軟 Arial / Times New Roman 完全公制一致，大幅避免了因字型代換導致段落換行、進而引發整份文件頁碼錯位的問題。

---

## 相關參考文件 (Related Topics)

- [返回技術分類索引](../Index.md)
- [本機與 Docker 容器化配置指南](../03-Testing-and-deployment/Environment-setup-and-dockerfile.md)
- [ETL 管道執行與 Docker 操作手冊](../../02-ETL-and-operations/01-Pipelines/Pipeline-execution-and-docker-guide.md)
