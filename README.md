

# Tender Document Pipeline — User Guide

A tool for preparing tender submission documents: converts Word files to PDF,
compresses all PDFs to meet a file-size limit, and automatically chunks any
files that are still too large.

---

## Before Starting: Filtering Files by Extension (`filter_extensions.py`)

The pipeline is designed for converting .docx and .doc to PDF, following by converting them. You should filter files under a folder and keep only the .doc(x) and .pdf files for the downstream pipeline.

And filter_extensions.py is a companion utility that copies files matching selected extensions while
preserving the original folder structure. Useful for extracting only the file
types you need (i.e. just the `.pdf`s, or just the `.doc(x)`s) from a large,
mixed tender folder before running the downstream pipeline.

### How it works

1. You provide either a **text file** of file paths (one per line) **or** a
   **directory** to scan recursively.
2. The script lists every file extension it found and prompts you to pick
   which ones to keep (comma-separated, with or without the leading dot).
3. Matching files are copied into the output folder, keeping their relative
   directory structure intact.

### Command-Line Flags

| Flag | Default | Description |
|------|---------|-------------|
| `-f`, `--file-list` | — | Path to a text file containing file paths (one per line). Mutually exclusive with `--input-dir`. |
| `-d`, `--input-dir` | — | Path to a directory to scan recursively for files. Mutually exclusive with `--file-list`. |
| `-o`, `--output-dir` | `output_files` | Target folder to copy selected files into. |

### Examples

**Scan a folder and keep only PDFs:**

```powershell
python filter_extensions.py -d /data/MyTender -o /data/MyTender_PDFs
# At the prompt, type: pdf
```

**Keep Word documents from a folder:**

```powershell
python filter_extensions.py -d /data/MyTender -o /data/MyTender_Docs
# At the prompt, type: docx, doc
```

**Filter from a pre-made file list:**

```powershell
python filter_extensions.py -f /data/file_list.txt -o /data/Selected
# At the prompt, type: .pdf, .dwg
```

> **Tip:** Run `filter_extensions.py` first to pull out only the file types
> you need, then point `pdf_tender_pipeline.py` at the filtered output with
> `--pdf-only` to compress and chunk them.

---

## Downstream Pipeline Quick Start (Docker — recommended)

### 1. Put your files in the `data` folder

Place your tender documents inside `data/` next to `docker-compose.yml`:

```
TenderConversion/
├── data/
│   └── MyTender/
│       ├── Volume 1/
│       │   ├── Section 1.docx
│       │   ├── Section 2.docx
│       │   └── drawings/
│       │       └── plan-01.pdf
│       └── Volume 2/
│           └── ...
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── pdf_tender_pipeline.py
```

### 2. Run the pipeline

```powershell
docker compose run --rm tender-pipeline -i /data/MyTender -o /data/MyTender_Final
```

That's it. The pipeline will:
1. Convert all `.doc`/`.docx` files to PDF (via LibreOffice)
2. Losslessly repack oversized PDFs, then downsample only high-DPI images if needed
3. Validate every PDF is under the size limit (default 50 MB)
4. Chunk any files still over the limit into smaller PDFs
5. Write the final output to `/data/MyTender_Final`

Compression preserves color, native text, vector drawings, page geometry, and
rotation. Completed runs are built in a fresh staging directory and replace the
previous output only after validation succeeds.

### 3. Collect your output

The finished files appear in `data/MyTender_Final/` on your Windows machine,
preserving the original folder structure.

---

## When to Use Which Flags

### I already have PDFs (no Word files)

Add `--pdf-only` to skip the Word-to-PDF conversion step:

```powershell
docker compose run --rm tender-pipeline -i /data/MyPdfs --pdf-only -o /data/MyPdfs_Final
```

### I have thousands of small files (slow WSL/network drives)

Add `--skip-copy` to avoid copying files that are already under the size limit.
Only compressed/chunked files are written to the output folder — everything
else stays in place. This is **dramatically faster** on slow filesystems:

```powershell
docker compose run --rm tender-pipeline -i /data/MyTender --pdf-only --skip-copy --silent -o /data/MyTender_Final
```

> **Note:** With `--skip-copy`, the output folder will only contain the files
> that were compressed or chunked. The under-limit files remain in the source
> folder. Use this when you only need the over-limit files split, and you'll
> merge the output back into your existing folder manually.

### I want less output (clean console)

Add `--quiet` to suppress per-file "skipped"/"compressed"/"PASS" lines.
You'll see only summary counts instead of hundreds of lines:

```powershell
docker compose run --rm tender-pipeline -i /data/MyTender --quiet --silent -o /data/MyTender_Final
```

### I want to run it non-interactively (CI/automation)

Add `--silent` to auto-proceed chunking without prompting:

```powershell
docker compose run --rm tender-pipeline -i /data/MyTender --silent -o /data/MyTender_Final
```

### I don't want any chunking

Add `--no-chunk` to disable chunking entirely. Files over the limit will be
flagged but not split:

```powershell
docker compose run --rm tender-pipeline -i /data/MyTender --no-chunk -o /data/MyTender_Final
```

### I want to skip compression (just validate and chunk)

Add `--skip-compression` to copy all files as-is without re-encoding. Only
validation and chunking are performed — useful when your PDFs are already
optimized and you just need to split over-limit files:

```powershell
docker compose run --rm tender-pipeline -i /data/MyTender --pdf-only --skip-compression --silent -o /data/MyTender_Final
```

---

## All Command-Line Flags

| Flag | Default | Description |
|------|---------|-------------|
| `-i`, `--input` | `/data/my_tender_docs` | Path to the source folder containing raw tender documents. |
| `-o`, `--output` | `<source> compressed` | Output folder. A bare name (e.g. `FinalSubmission`) is created next to the source. A path (e.g. `/data/Final`) is used as-is. |
| `--dpi` | `200` | Target DPI for rewritten images. Document AI recommends at least 200 DPI for OCR; 300 DPI generally gives better results. |
| `--dpi-threshold` | `1.5 x --dpi` | Rewrite only images displayed above this effective DPI. Must be greater than `--dpi`. |
| `-q`, `--quality` | `80` | JPEG quality (1–100). Lower = smaller files but lower quality. |
| `--max-mb` | `50.0` | Maximum allowed file size in MB. Files over this are compressed, then chunked if still over. |
| `--workers` | `2` | Concurrent PDF compression processes. Use `1` for low-memory systems or slow shared mounts. |
| `--pdf-only` | off | Skip Word-to-PDF conversion. Compress existing PDFs directly. |
| `--silent` | off | Auto-proceed chunking without prompting. Use for automation/CI. |
| `--no-chunk` | off | Disable chunking entirely. Over-limit files are flagged but not split. |
| `--skip-copy` | off | Don't copy under-limit files to the output folder. Only compressed/chunked files are written. Much faster on slow filesystems. |
| `--skip-compression` | off | Skip the compression step entirely. All files are copied as-is. Only validation and chunking are performed. |
| `--quiet` | off | Suppress per-file output. Show only summary counts. |

---

## How Compression Works

Only PDFs at or above `--max-mb` enter compression. Smaller PDFs are copied
byte-for-byte unless `--skip-copy` is enabled.

1. **Lossless repack** — Unused and duplicate PDF objects are removed, and
   uncompressed streams and object definitions are compressed with standard
   Flate compression.
2. **DPI-aware image rewrite** — If the lossless result is still too large,
   PyMuPDF rewrites images whose effective displayed DPI exceeds
   `--dpi-threshold`, reducing them to `--dpi`. Color and grayscale images are
   both supported, but color is never intentionally converted to grayscale.
3. **Fidelity validation** — Each candidate must reopen and render while
   preserving page count, page boxes, rotation, and native extracted text.
4. **Smallest valid result** — The original, lossless result, and rewritten
   result are compared. The pipeline publishes only the smallest valid file,
   so compression cannot make an output larger.

Native text and vector objects are not rasterized during ordinary compression.
Only the existing oversized single-page rescue can rasterize a complete page.

### Parallel Compression

Oversized PDFs are compressed concurrently using separate worker processes.
Each worker handles one complete PDF, and receives another queued PDF as soon
as it finishes. Under-limit files are copied or skipped by the parent process
and never occupy compression workers.

The default is two workers. PyMuPDF does not support multithreaded processing,
so the pipeline uses processes and each process opens its own PDF. Increase the
worker count only after checking Docker memory and disk utilization:

```powershell
docker compose run --rm tender-pipeline -i /data/MyTender --pdf-only --workers 4 -o /data/MyTender_Final
```

Use `--workers 1` when processing very large scanned PDFs, when memory is
limited, or when the Windows-backed `/data` mount is the bottleneck. A single
oversized PDF still uses one worker; parallelism improves throughput when
multiple oversized PDFs are available.

---

## How Chunking Works

When a PDF is still over the size limit after compression, the pipeline splits
it into smaller PDFs using exact serialized byte sizes:

1. **Greedy page packing** — Pages are added in their original order. After
   each addition, the candidate chunk is serialized in memory using the same
   settings as the final PDF.

2. **Exact boundary** — When the next page would reach or exceed the limit,
   the last valid serialized bytes are written directly as the final chunk.
   Final chunks are therefore written once and are strictly below the limit.

3. **Oversized-page rescue** — If one page cannot fit by itself, only that page
   is rasterized at progressively lower DPI and JPEG quality until it fits.
   This can reduce quality and removes searchable text from that page.

4. **Transactional replacement** — Chunks are staged first. The original PDF
   and any stale chunks are replaced only after every page has a valid output.
   Names follow the original page order:
   ```
   MyDocument_chunk-1.pdf
   MyDocument_chunk-2.pdf
   MyDocument_chunk-3.pdf
   ```

Chunk files are placed in the same subfolder as the original file, preserving
the folder structure.

---

## Output Examples

### Typical run (with `--quiet`)

```
==================================================================
🚀 STARTING TENDER DOCUMENT PIPELINE FOR: 2.0 Tender Doc
==================================================================

--- STEP 1: SKIPPED (--pdf-only: compressing existing PDFs directly) ---

--- STEP 2: COMPRESSING ALL PDFS ---
  Found 1733 PDF file(s) to process (threshold: 50.0 MB)...
  ℹ️ Processed 1733 file(s): 1731 skipped, 2 compressed, 0 failed.

--- STEP 3: VALIDATING FINAL FILE SIZES ---
  ℹ️ Validated 2 file(s): 0 passed, 2 over limit.

🚨 VALIDATION FAILED: 2 file(s) at/over 50.0 MB!

--- STEP 3b: EXACT SIZE CHUNKING (2 over-limit file(s)) ---
  📄 Chunking: V3_02 - SCOPE (Drawings) - GENERAL ARRANGEMENT (GA)_Combined.pdf (126.52 MB)
     • Produced: V3_02_..._chunk-1.pdf (pp. 1-24, 48.72 MB)
     • Produced: V3_02_..._chunk-2.pdf (pp. 25-41, 47.91 MB)
     • Produced: V3_02_..._chunk-3.pdf (pp. 42-60, 29.89 MB)
  📄 Chunking: V3_12 - SCOPE (Drawings) - BUILDING SERVICES (BS)_Combined.pdf (60.48 MB)
     • Produced: V3_12_..._chunk-1.pdf (pp. 1-87, 49.26 MB)
     • Produced: V3_12_..._chunk-2.pdf (pp. 88-110, 11.22 MB)

  ✅ All chunks are under 50.0 MB.

--- STEP 3b: RE-VALIDATING AFTER CHUNKING ---
  ℹ️ Validated 6 file(s): 6 passed, 0 over limit.

🎉 ALL CLEAR: All files are verified strictly under 50.0 MB.

==================================================================
📊 SUMMARY STATISTICS
==================================================================
  PDFs compressed        : 1733  (failed: 0, skipped: 1731)
  Total size before      : 1307.53 MB
  Total size after       : 1307.53 MB
  Files validated        : 6
  ✅ Passed (< 50.0 MB)     : 6
  ❌ Failed (>= 50.0 MB)    : 0
  Files chunked          : 2
   Chunks produced        : 5
   Oversized pages rescued : 0
  Chunks still over limit : 0
==================================================================

✅ PIPELINE COMPLETED SUCCESSFULLY! Documents ready for submission.
📁 Final files location: /data/test_chunk_output_p02
```

---

## Common Recipes

### Full pipeline (Word + PDF → compressed output)

```powershell
docker compose run --rm tender-pipeline `
    -i /data/MyTender `
    -o /data/MyTender_Final `
    --dpi 200 -q 80 --max-mb 50
```

### PDF-only, fast (skip-copy, quiet, silent)

```powershell
docker compose run --rm tender-pipeline `
    -i /data/MyTender `
    -o /data/MyTender_Final `
    --pdf-only --skip-copy --quiet --silent
```

### Aggressive compression (smaller files, lower quality)

```powershell
docker compose run --rm tender-pipeline `
    -i /data/MyTender `
    -o /data/MyTender_Final `
    --dpi 150 -q 50 --max-mb 30
```

### No chunking (just compress and validate)

```powershell
docker compose run --rm tender-pipeline `
    -i /data/MyTender `
    -o /data/MyTender_Final `
    --no-chunk
```

---

## Running Without Docker (local Python)

### Prerequisites

- Python 3.12+
- LibreOffice (for Word-to-PDF conversion; not needed with `--pdf-only`)

### Install dependencies

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
```

### Run

```bash
python pdf_tender_pipeline.py -i /path/to/tender -o /path/to/output
```

All flags work the same as the Docker version.

---

## Troubleshooting

### "File exists" error on WSL/Docker shared mounts

This is a known WSL filesystem caching issue. The pipeline handles it
automatically, but if it persists, manually delete the output folder first:

```powershell
docker run --rm -v "${PWD}/data:/data" python:3.12-slim python -c "import shutil; shutil.rmtree('/data/YourOutputFolder', ignore_errors=True)"
```

### Files still over the limit after chunking

The pipeline automatically rasterizes an individually oversized page at
progressively lower DPI and JPEG quality. If the page still cannot fit at the
lowest fallback setting, the original PDF is preserved and flagged for manual
intervention. Options:
- Re-scan the source at a lower DPI
- Use a lower `--dpi` and `-q` value to compress more aggressively
- Use a higher `--max-mb` if your submission system allows it

### Compression didn't reduce file size

Some PDFs are already highly optimized (e.g. scanned at low DPI with JPEG
compression). Re-encoding them can sometimes produce a larger file. The
pipeline only compresses files that exceed the threshold; under-limit files
are copied as-is (or skipped with `--skip-copy`).

### Output folder is nearly empty (with `--skip-copy`)

This is expected. With `--skip-copy`, only files that were compressed or
chunked are written to the output folder. All under-limit files stay in the
source folder. Merge the output back into your source folder manually, or
re-run without `--skip-copy` to get a complete copy of everything.
