# 無損重整、圖像降採樣與貪婪分塊算法 (Compression and Chunking Algorithms)

**適用對象：** 演算法工程師 / 後端開發人員 / 系統架構師
**文件狀態：** 現行版本
**最後審核：** 2026-10-05

> 備註：以下演算法邏輯與邊界處理，於 2026 年 10 月 05 日審閱本文件時仍然有效。

---

## 簡要說明 (Summary)

本文件介紹 `TenderConversion` 管道中的三項主要演算法：**文件不變性檢查（Document Invariants Validation）**、**依 DPI 重編碼圖像（DPI-Aware Image Rewrite）**，以及**透過指數探測與二分搜尋進行精確位元組分塊（Exact Byte Greedy Chunking）**。內容說明這些機制如何檢查文字與頁面幾何資訊，並依大小及頁數門檻處理 PDF。

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

- **檢查方式：** 每個重編碼候選檔都會重新計算不變性資料，並與原始檔比較。若頁數、頁面邊界、旋轉角度或文字雜湊不同，候選檔便不會通過此項檢查。

---

## 演算法二：雙階段壓縮與最小有效結果選擇 (Two-Phase Compression)

對超過設定大小門檻的 PDF，管道會依序嘗試下列處理方式：

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

- **候選檔比較：** 原始檔也會納入候選結果比較；若重整後的檔案較大，則保留體積較小的有效版本。

---

## 演算法三：精確位元組貪婪分塊 (Exact Byte Greedy Chunking)

當 PDF 經過處理後仍超出設定的大小或頁數門檻時，管道會依頁面範圍進行分塊。

### 以平均頁面大小估算的限制
若僅以「總大小 ÷ 頁數」估算每頁大小，可能無法反映不同頁面的實際差異。例如，前幾頁合約文字量很小，後續的彩色配置圖卻可能占用大量空間，因此平均估算不一定能確保分塊後符合大小限制。

### 本管道的分塊策略：指數探測與二分搜尋

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
   偵測到候選範圍超出大小門檻後，演算法會在「最後成功點」與「首次失敗點」之間以二分搜尋收斂，在 $O(\log N)$ 次探測內找出符合門檻的最大頁面範圍。
4. **避免重複序列化：**
   搜尋完成後，記憶體中已保留符合條件的序列化資料，可直接使用 `chunk_path.write_bytes(accepted_bytes)` 寫入磁碟，避免再次序列化同一個分塊。

---

## 演算法邊界條件與應急機制

| 邊界情況 | 演算法行為 |
|---|---|
| **單頁超出大小門檻** | `accepted_bytes` 維持 `None` 時，啟動 `_rescue_oversized_page`，以六組灰階 JPEG 設定（180 至 50 DPI、品質 75 至 30）依序嘗試處理該頁。成功後會將它寫成獨立分塊；若全部失敗，則依管道的錯誤處理方式保留原始檔案。 |
| **頁數超出設定值但檔案很小** | `maximum_end_page = min(start_page + 500, total_pages)` 限制每個分塊的頁數；即使檔案體積不大，也會在頁數上限處分段。 |

---

## 相關參考文件 (Related Topics)

- [返回技術分類索引](../Index.md)
- [系統架構與 RAG 資料流設計](System-architecture-and-data-flow.md)
- [Gcloud RAG Agent 限制規範](../../02-ETL-and-operations/02-RAG-spec-and-limits/Gcloud-rag-agent-constraints.md)
- [超大單頁應急點陣化救援機制筆記](../04-Feature-notes/Oversized-page-rescue-mechanism.md)
