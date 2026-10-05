# 無損重整、圖像降採樣與貪婪分塊算法 (Compression and Chunking Algorithms)

**適用對象：** 演算法工程師 / 後端開發人員 / 系統架構師
**文件狀態：** 現行版本
**最後審核：** 2026-10-05

> 備註：以下演算法邏輯與數學邊界處理於 2026 年 10 月 05 日審核此文檔時仍然有效。

---

## 簡要說明 (Summary)

本文件詳細剖析 `TenderConversion` 管道中的三大核心演算法：**文件不變性校驗（Document Invariants Validation）**、**DPI 智慧重編碼（DPI-Aware Image Rewrite）**、以及**指數倍增與二分搜尋精確位元組貪婪分塊演算法（Exact Byte Greedy Chunking）**。說明系統如何在嚴格符合 Google Cloud 50MB 與 500 頁限制的前提下，將文字層與向量幾何圖形的保真度維持在 100%。

---

## 演算法一：文件不變性校驗 (Document Invariants Validation)

為防止任何壓縮或優化動作破壞 PDF 的版面排版或文字內容，管道在處理前會先提取原始文件的幾何與語意特徵值（Invariant Tuple）：

```python
def _document_invariants(pdf_path: Path, render_check: bool = False) -> tuple:
    with pymupdf.open(pdf_path) as doc:
        pages = []
        for page in doc:
            # 1. 提取頁面純文字並計算 SHA-256 雜湊
            text_hash = hashlib.sha256(page.get_text("text").encode("utf-8")).hexdigest()
            pages.append((
                tuple(page.mediabox),  # 2. 頁面實體邊界 (Mediabox)
                tuple(page.cropbox),   # 3. 頁面裁剪邊界 (Cropbox)
                page.rotation,         # 4. 旋轉角度 (Rotation)
                text_hash,             # 5. 語意文字雜湊 (Text Hash)
            ))
            if render_check:
                # 6. 36 DPI 快速彩現測試，確保無底層崩潰
                page.get_pixmap(dpi=36, colorspace=pymupdf.csRGB, alpha=False)
        return doc.page_count, tuple(pages)
```

- **安全保證：** 任何重編碼候選檔案（Candidate）必須重新提取不變性數值，並與原始檔進行 `==` 嚴格全等比較。若頁數改變、邊界座標微移、旋轉偏差或任何一個字元發生變異，該候選檔將被立即拋棄。

---

## 演算法二：雙階段壓縮與最小有效結果選擇 (Two-Phase Compression)

針對超過 50MB 的 PDF 檔案，管道採取階梯式漸進處理：

```text
[原始 PDF (Candidate 1)]
       │
       ▼ 階段一：無損重整 (Lossless Repack)
       │ 去除孤立物件、重複串流，以 Flate 演算法壓縮物件表
       │ doc.save(..., garbage=4, deflate=1, use_objstms=True)
       ▼
   產生 lossless.pdf (Candidate 2)
       │
       ├─► 若已有效且小於 50MB ──► [選用並發佈]
       │
       ▼ 階段二：圖像重編碼 (DPI-Aware Rewrite)
       │ 僅針對有效顯示解析度 > dpi_threshold (如 300 DPI) 的點陣圖降採樣至 200 DPI
       │ 保持原始色彩空間 (set_to_gray=False)，保證工程圖紙管線顏色清晰
       ▼
   產生 rewritten.pdf (Candidate 3)
       │
       ▼ 候選檔案擇優 (Smallest Valid Candidate)
       selected = min(valid_candidates, key=lambda p: p.stat().st_size)
```

- **不膨脹保證：** 系統始終將原始檔案也納入候選池中比較，如果重整後檔案反而變大，演算法會自動回退並選用原始檔案。

---

## 演算法三：精確位元組貪婪分塊 (Exact Byte Greedy Chunking)

當 PDF 經過壓縮後依然超過 50.0 MB 或超過 500 頁時，必須進行分塊切分。

### 傳統估算法的致命缺陷
許多開源腳本會依據「總大小 ÷ 頁數」平均估算每頁大小來決定切分點。然而工程標案中，前 5 頁合約可能只有 200 KB，第 6 頁全區彩色配置圖卻高達 40 MB。平均估算法極易導致切分後的檔案依然超出 50MB。

### 本管道的創新解法：指數倍增探測 + 二分搜尋收斂

```mermaid
graph TD
    Start[起始頁 start_page] --> Probe[指數倍增探測 probe_end_page]
    Probe -->|序列化大小 < 50MB 且未達 500 頁| Accept[接受頁面，探測步長翻倍]
    Accept --> Probe
    Probe -->|序列化大小 >= 50MB| Bracket[鎖定邊界範圍 (low, high)]
    Bracket --> BinarySearch[二分搜尋 probe = (low + high) // 2]
    BinarySearch -->|候選大小 < 50MB| MoveLow[low = probe + 1, 更新合格切分點]
    BinarySearch -->|候選大小 >= 50MB| MoveHigh[high = probe - 1]
    MoveLow & MoveHigh --> IsDone{low > high?}
    IsDone -->|否| BinarySearch
    IsDone -->|是| DirectWrite[直接將已序列化 Bytes 寫入 chunk-N.pdf]
```

### 演算法核心步驟解析
1. **即時序列化（In-Memory Serialization）：**
   使用 `_serialize_pdf_range(doc, start_page, end_page)` 將指定頁面範圍在記憶體中以最終儲存規格（`garbage=3, deflate=True`）完整序列化，以獲取**真實位元組長度**。
2. **指數倍增探測（Exponential Probing）：**
   從 `start_page + 1` 開始，每次將步長翻倍（1 -> 2 -> 4 -> 8 -> 16 頁...）。避免一開始就建立 500 頁的巨大記憶體物件，大幅降低記憶體開銷。
3. **二分搜尋精確收斂（Binary Search Refinement）：**
   一旦探測到超越 50MB 門檻，立即鎖定在「最後成功點」與「首次失敗點」之間的區間，以二分搜尋在 $O(\log N)$ 次數內找到能塞入 `< 50.0 MB` 的最大頁數。
4. **零二次磁碟開銷：**
   收斂完成時，記憶體中已經持有該範圍的合法位元組資料，直接以 `chunk_path.write_bytes(accepted_bytes)` 寫入磁碟，完全不需要二次開啟檔案存檔。

---

## 演算法邊界條件與應急機制

| 邊界情況 | 演算法行為 |
|---|---|
| **單頁即超標 (`start_page` 單頁序列化 >= 50MB)** | `accepted_bytes` 維持 `None`，立即啟動 `_rescue_oversized_page`，以 6 階灰階 JPEG 階梯（180->50 DPI，Q=75->30）降階彩現該單頁，成功壓入 50MB 後封裝為獨立單頁分塊。若 6 階全失敗則保留原始檔案於輸出目錄供人工審查。 |
| **頁數超標但體積極小 (如 600 頁，共 10MB)** | 觸發 `maximum_end_page = min(start_page + 500, total_pages)`，在第 500 頁強制切斷，產出符合 Document AI 上限之分塊。 |

---

## 相關參考文件 (Related Topics)

- [返回技術分類索引](../Index.md)
- [系統架構與 RAG 資料流設計](System-architecture-and-data-flow.md)
- [Gcloud RAG Agent 限制規範](../../02-ETL-and-operations/02-RAG-spec-and-limits/Gcloud-rag-agent-constraints.md)
- [超大單頁應急點陣化救援機制筆記](../04-Feature-notes/Oversized-page-rescue-mechanism.md)
