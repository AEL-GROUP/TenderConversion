# LibreOffice 無周邊 Word 轉換實作筆記 (LibreOffice Headless Conversion Notes)

**適用對象：** 核心開發人員 / 系統架構師
**文件狀態：** 現行版本
**最後審核：** 2026-10-05

> 備註：以下 LibreOffice 命令列呼叫方式與子程序處理，於 2026 年 10 月 05 日審閱本文件時仍然適用。

---

## 簡要說明 (Summary)

本筆記說明 `pdf_tender_pipeline.py` 在 `STEP 1` 使用 **LibreOffice Headless Mode** 將 `.doc` 與 `.docx` 轉換為 PDF 時的實作方式、例外處理及設計考量。

---

## 核心呼叫方式 (Core Implementation)

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

### 1. 為什麼使用 headless LibreOffice？
- **可在容器環境執行：** 無周邊模式不需要圖形介面，適合在伺服器或 Docker 容器中執行。
- **支援舊版 `.doc` 格式：** LibreOffice 可處理舊版 Word 文件；僅支援 `.docx` 的 Python 套件則無法涵蓋此格式。
- **處理複雜版面：** Word 文件可能包含頁首頁尾、表格及多欄排版；轉換結果仍應抽樣檢查，以確認版面符合需求。

### 2. 檢查轉換輸出是否存在
- **可能情況：** 即使 LibreOffice 程序回傳成功狀態，輸出資料夾中仍可能沒有預期的 PDF。
- **管道處理方式：** 子程序結束後，管道會檢查 `expected_output.exists()`，確認預期輸出檔案確實存在，再繼續後續處理。

### 3. 字型替代與版面差異
- 若來源 Word 使用的字型未安裝於執行環境，LibreOffice 可能以其他字型替代。Docker 映像檔包含 `fonts-liberation`，但仍建議檢查轉換後的換行、頁數及版面，尤其是使用特殊字型的文件。

---

## 相關參考文件 (Related Topics)

- [返回技術分類索引](../Index.md)
- [本機與 Docker 容器化配置指南](../03-Testing-and-deployment/Environment-setup-and-dockerfile.md)
- [ETL 管道執行與 Docker 操作手冊](../../02-ETL-and-operations/01-Pipelines/Pipeline-execution-and-docker-guide.md)
