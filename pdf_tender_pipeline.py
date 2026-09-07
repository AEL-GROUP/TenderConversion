"""
pdf_tender_pipeline.py
======================
Master pipeline for preparing tender submission documents.

Steps
-----
  STEP 1: Convert Word documents (.doc AND .docx) to PDF via LibreOffice.
          (Skipped when --pdf-only is passed; existing PDFs are compressed directly.)
  STEP 2: Losslessly repack PDFs, then downsample oversized images while
      preserving color via PyMuPDF.
          Files already under the size threshold are copied as-is.
  STEP 3: Validate every compressed PDF is strictly under a size threshold
          (default 50 MB).
  STEP 3b: Chunk any files still over the limit into smaller PDFs using
      exact serialized byte sizes. Oversized individual pages are
      adaptively rasterized. Skipped when --no-chunk is passed or the user
      declines the interactive prompt (unless --silent auto-proceeds).
  STEP 4: Print aggregate summary statistics for the whole run.
  STEP 5: Assert the output file count matches the source document count.

Usage
-----
  Full pipeline (Word -> PDF -> Compress -> Validate -> Chunk):

      python pdf_tender_pipeline.py -i /data/my_tender_docs

  PDF-only mode (compress existing PDFs directly):

      python pdf_tender_pipeline.py -i /data/my_pdfs --pdf-only

  Custom output location, DPI, quality, and size limit:

      python pdf_tender_pipeline.py -i /data/tender -o /mnt/d/Final \\
          --dpi 150 -q 60 --max-mb 30

  Silent mode (auto-proceed chunking without prompting):

      python pdf_tender_pipeline.py -i /data/tender --silent

  Skip copying under-limit files (fast on slow filesystems):

      python pdf_tender_pipeline.py -i /data/tender --pdf-only --skip-copy
"""

import argparse
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
import hashlib
import io
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pymupdf  # PyMuPDF
from PIL import Image

# File extensions LibreOffice will convert to PDF
WORD_EXTENSIONS = ("*.doc", "*.docx")
_PIPELINE_TEMP_DIR_MARKERS = ("_compress_", "_chunks_", ".run_", ".backup_")


def _is_pipeline_temp_dir_name(name: str) -> bool:
    """Returns whether a directory belongs to pipeline staging."""
    return name.startswith(".") and any(
        marker in name for marker in _PIPELINE_TEMP_DIR_MARKERS
    )


def _discover_pdfs(root: Path) -> list[Path]:
    """Finds PDFs while pruning pipeline-owned temporary directories."""
    pdf_files = []

    for current_root, directory_names, file_names in os.walk(root):
        directory_names[:] = [
            name
            for name in directory_names
            if not _is_pipeline_temp_dir_name(name)
        ]
        current_path = Path(current_root)
        pdf_files.extend(
            current_path / file_name
            for file_name in file_names
            if not file_name.startswith("~$")
            and Path(file_name).suffix.lower() == ".pdf"
        )

    return sorted(
        pdf_files,
        key=lambda path: path.relative_to(root).as_posix().lower(),
    )


# ==============================================================================
# STEP 1: CONVERT WORD DOCS (.doc / .docx) TO PDF
# ==============================================================================
def convert_docx_step(source_root: Path, converted_root: Path):
    """Recursively converts all .doc/.docx files to .pdf using LibreOffice."""
    word_files = []
    for pattern in WORD_EXTENSIONS:
        word_files.extend(
            f for f in source_root.rglob(pattern) if not f.name.startswith("~$")
        )
    word_files = sorted(set(word_files))

    if not word_files:
        print("  \u2139\ufe0f No .doc/.docx files found. Skipping Word conversion.")
        return

    print(f"  Found {len(word_files)} Word file(s) to convert...")

    for doc_path in word_files:
        rel_path = doc_path.relative_to(source_root)
        output_dir = converted_root / rel_path.parent
        output_dir.mkdir(parents=True, exist_ok=True)
        expected_output = output_dir / (doc_path.stem + ".pdf")

        cmd = [
            "libreoffice",
            "--headless",
            "--convert-to",
            "pdf",
            str(doc_path),
            "--outdir",
            str(output_dir),
        ]

        try:
            subprocess.run(
                cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
            )
            if expected_output.exists():
                print(f"  \u2022 Converted: {rel_path} -> {expected_output.relative_to(converted_root)}")
            else:
                print(f"  \u274c LibreOffice reported success but no output file found for {rel_path}")
        except FileNotFoundError:
            print("\n[Error] LibreOffice is not installed or not in system PATH.")
            sys.exit(1)
        except subprocess.CalledProcessError as e:
            stderr_text = e.stderr.decode(errors="replace") if e.stderr else "(no stderr)"
            print(f"  \u274c Failed to convert {doc_path.name}: {stderr_text}")


# ==============================================================================
# STEP 2: COMPRESS PDFS
# ==============================================================================
def _document_invariants(pdf_path: Path, render_check: bool = False) -> tuple:
    """Returns semantic and geometric invariants used to reject bad rewrites."""
    with pymupdf.open(pdf_path) as doc:
        pages = []
        for page in doc:
            text_hash = hashlib.sha256(page.get_text("text").encode("utf-8")).hexdigest()
            pages.append((
                tuple(page.mediabox),
                tuple(page.cropbox),
                page.rotation,
                text_hash,
            ))
            if render_check:
                page.get_pixmap(dpi=36, colorspace=pymupdf.csRGB, alpha=False)
        return doc.page_count, tuple(pages)


def _valid_compression_candidate(candidate: Path, expected_invariants: tuple) -> bool:
    """Checks that a staged PDF can be read, rendered, and still exposes its text."""
    try:
        return _document_invariants(candidate, render_check=True) == expected_invariants
    except Exception:
        return False


def _save_compressed_document(doc, output_path: Path) -> None:
    doc.save(output_path, garbage=4, deflate=1, use_objstms=True)


def compress_single_pdf(
    input_path: Path,
    output_path: Path,
    target_dpi=200,
    jpeg_quality=80,
    max_bytes: float | None = None,
    dpi_threshold: int | None = None,
):
    """Creates and atomically publishes the smallest validated PDF candidate."""
    if target_dpi <= 0:
        raise ValueError("target_dpi must be positive")
    if not 1 <= jpeg_quality <= 100:
        raise ValueError("jpeg_quality must be between 1 and 100")

    resolved_threshold = dpi_threshold or max(target_dpi + 1, round(target_dpi * 1.5))
    if resolved_threshold <= target_dpi:
        raise ValueError("dpi_threshold must be greater than target_dpi")

    expected_invariants = _document_invariants(input_path, render_check=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(
        prefix=f".{output_path.stem}_compress_",
        dir=output_path.parent,
    ) as temporary_dir:
        stage_dir = Path(temporary_dir)
        candidates = [input_path]
        lossless_path = stage_dir / "lossless.pdf"

        with pymupdf.open(input_path) as doc:
            _save_compressed_document(doc, lossless_path)
        if _valid_compression_candidate(lossless_path, expected_invariants):
            candidates.append(lossless_path)

        best_path = min(candidates, key=lambda path: path.stat().st_size)
        needs_image_rewrite = max_bytes is None or best_path.stat().st_size >= max_bytes
        if needs_image_rewrite:
            rewritten_path = stage_dir / "rewritten.pdf"
            with pymupdf.open(best_path) as doc:
                doc.rewrite_images(
                    dpi_threshold=resolved_threshold,
                    dpi_target=target_dpi,
                    quality=jpeg_quality,
                    lossy=True,
                    lossless=True,
                    bitonal=True,
                    color=True,
                    gray=True,
                    set_to_gray=False,
                )
                _save_compressed_document(doc, rewritten_path)
            if _valid_compression_candidate(rewritten_path, expected_invariants):
                candidates.append(rewritten_path)

        selected_path = min(candidates, key=lambda path: path.stat().st_size)
        publish_path = stage_dir / "publish.pdf"
        shutil.copy2(selected_path, publish_path)
        os.replace(publish_path, output_path)


def _compress_pdf_worker(job: dict) -> dict:
    """Compresses one PDF in an isolated process and returns a small result."""
    started_at = time.perf_counter()
    try:
        compress_single_pdf(
            Path(job["input_path"]),
            Path(job["output_path"]),
            target_dpi=job["target_dpi"],
            jpeg_quality=job["jpeg_quality"],
            max_bytes=job["max_bytes"],
            dpi_threshold=job["dpi_threshold"],
        )
        return {
            **job,
            "new_bytes": Path(job["output_path"]).stat().st_size,
            "elapsed_seconds": time.perf_counter() - started_at,
            "error": None,
        }
    except Exception as error:
        return {
            **job,
            "new_bytes": 0,
            "elapsed_seconds": time.perf_counter() - started_at,
            "error": str(error),
        }


def _record_compression_result(
    result: dict,
    stats: dict,
    completed: int,
    total: int,
    quiet: bool,
) -> None:
    """Updates parent-owned statistics and reports one completed worker job."""
    stats["count"] += 1
    stats["orig_bytes"] += result["orig_bytes"]

    if result["error"] is not None:
        stats["failed"] += 1
        print(
            f"  [FAIL {completed}/{total}] {result['rel_path']} after "
            f"{result['elapsed_seconds']:.1f}s: {result['error']}",
            flush=True,
        )
        return

    stats["new_bytes"] += result["new_bytes"]
    if quiet:
        return

    orig_mb = result["orig_bytes"] / (1024 * 1024)
    new_mb = result["new_bytes"] / (1024 * 1024)
    savings = (((orig_mb - new_mb) / orig_mb) * 100) if orig_mb > 0 else 0
    print(
        f"  [DONE {completed}/{total}] {result['rel_path']} "
        f"({orig_mb:.2f}MB -> {new_mb:.2f}MB, -{savings:.1f}%, "
        f"{result['elapsed_seconds']:.1f}s)",
        flush=True,
    )


def compress_step(
    converted_root: Path,
    compressed_root: Path,
    target_dpi=200,
    jpeg_quality=80,
    max_mb=50.0,
    skip_copy=False,
    quiet=False,
    skip_compression=False,
    dpi_threshold: int | None = None,
    workers: int | None = None,
    max_pages: int = 500,
):
    """Recursively compresses all PDFs found in converted_root.

    Only files LARGER than ``max_mb`` are compressed; smaller files are copied
    as-is because compression can occasionally increase the size of an already
    small PDF.

    When ``skip_copy`` is True, under-limit files are NOT copied to the output
    folder — only compressed/chunked files are written. This dramatically speeds
    up runs with many small files on slow filesystems (e.g. WSL shared mounts).

    When ``skip_compression`` is True, NO files are compressed — every file is
    copied as-is to the output folder. Useful when you only want to validate
    and chunk without re-encoding.

    When ``quiet`` is True, per-file "skipped"/"compressed" lines are
    suppressed and only a summary count is printed at the end.
    """
    if workers is None:
        workers = min(2, os.cpu_count() or 1)
    if workers < 1:
        raise ValueError("workers must be at least 1")
    if max_pages < 1:
        raise ValueError("max_pages must be at least 1")

    stats = {"count": 0, "failed": 0, "orig_bytes": 0, "new_bytes": 0, "skipped": 0}

    pdf_files = _discover_pdfs(converted_root)

    if not pdf_files:
        print("  \u2139\ufe0f No .pdf files found to compress.")
        return stats

    max_bytes = max_mb * 1024 * 1024
    if skip_compression:
        print(f"  Found {len(pdf_files)} PDF file(s) to process (--skip-compression: copying all as-is)...")
    else:
        print(f"  Found {len(pdf_files)} PDF file(s) to process (threshold: {max_mb} MB)...")

    compression_jobs = []
    for pdf_path in pdf_files:
        rel_path = pdf_path.relative_to(converted_root)
        output_pdf_path = compressed_root / rel_path

        orig_bytes = pdf_path.stat().st_size
        orig_mb = orig_bytes / (1024 * 1024)

        # When --skip-compression is set, copy every file as-is without re-encoding.
        if skip_compression:
            if skip_copy:
                stats["skipped"] += 1
                stats["count"] += 1
                stats["orig_bytes"] += orig_bytes
                stats["new_bytes"] += orig_bytes
                continue
            output_pdf_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(pdf_path, output_pdf_path)
            if not quiet:
                print(f"  \u23ed\ufe0f Skipped (--skip-compression): {rel_path} ({orig_mb:.2f} MB) -> copied as-is")
            stats["skipped"] += 1
            stats["count"] += 1
            stats["orig_bytes"] += orig_bytes
            stats["new_bytes"] += orig_bytes
            continue

        # Only compress files that exceed the threshold; copy smaller files as-is
        # because re-encoding them can sometimes produce a larger output.
        if orig_bytes <= max_bytes:
            if skip_copy:
                try:
                    with pymupdf.open(pdf_path) as doc:
                        page_count = doc.page_count
                except Exception:
                    page_count = max_pages + 1
                if page_count <= max_pages:
                    stats["skipped"] += 1
                    stats["count"] += 1
                    stats["orig_bytes"] += orig_bytes
                    stats["new_bytes"] += orig_bytes
                    continue
                if not quiet:
                    print(
                        f"  \u26a0\ufe0f Page limit exceeded: {rel_path} "
                        f"({page_count} pages > {max_pages}) -> copied for chunking"
                    )
            output_pdf_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(pdf_path, output_pdf_path)
            if not quiet:
                print(f"  \u23ed\ufe0f Skipped (under {max_mb} MB): {rel_path} ({orig_mb:.2f} MB) -> copied as-is")
            stats["skipped"] += 1
            stats["count"] += 1
            stats["orig_bytes"] += orig_bytes
            stats["new_bytes"] += orig_bytes
            continue

        compression_jobs.append({
            "input_path": str(pdf_path),
            "output_path": str(output_pdf_path),
            "rel_path": str(rel_path),
            "orig_bytes": orig_bytes,
            "target_dpi": target_dpi,
            "jpeg_quality": jpeg_quality,
            "max_bytes": max_bytes,
            "dpi_threshold": dpi_threshold,
        })

    if compression_jobs:
        effective_workers = min(workers, len(compression_jobs), os.cpu_count() or 1)
        total_jobs = len(compression_jobs)
        print(
            f"  Using {effective_workers} compression worker process(es) for "
            f"{total_jobs} oversized PDF(s).",
            flush=True,
        )

        if effective_workers == 1:
            for job_number, job in enumerate(compression_jobs, start=1):
                if not quiet:
                    print(
                        f"  [START {job_number}/{total_jobs}] {job['rel_path']} "
                        f"({job['orig_bytes'] / (1024 * 1024):.2f} MB)",
                        flush=True,
                    )
                result = _compress_pdf_worker(job)
                _record_compression_result(
                    result, stats, job_number, total_jobs, quiet
                )
        else:
            completed = 0
            next_job = 0
            with ProcessPoolExecutor(max_workers=effective_workers) as executor:
                pending = {}
                while next_job < total_jobs and len(pending) < effective_workers:
                    job = compression_jobs[next_job]
                    next_job += 1
                    if not quiet:
                        print(
                            f"  [START {next_job}/{total_jobs}] {job['rel_path']} "
                            f"({job['orig_bytes'] / (1024 * 1024):.2f} MB)",
                            flush=True,
                        )
                    pending[executor.submit(_compress_pdf_worker, job)] = job

                while pending:
                    done, _ = wait(pending, return_when=FIRST_COMPLETED)
                    for future in done:
                        job = pending.pop(future)
                        try:
                            result = future.result()
                        except Exception as error:
                            result = {
                                **job,
                                "new_bytes": 0,
                                "elapsed_seconds": 0.0,
                                "error": f"worker process failed: {error}",
                            }
                        completed += 1
                        _record_compression_result(
                            result, stats, completed, total_jobs, quiet
                        )

                        if next_job < total_jobs:
                            next_job += 1
                            next_item = compression_jobs[next_job - 1]
                            if not quiet:
                                print(
                                    f"  [START {next_job}/{total_jobs}] "
                                    f"{next_item['rel_path']} "
                                    f"({next_item['orig_bytes'] / (1024 * 1024):.2f} MB)",
                                    flush=True,
                                )
                            pending[
                                executor.submit(_compress_pdf_worker, next_item)
                            ] = next_item

    if quiet:
        print(f"  \u2139\ufe0f Processed {stats['count']} file(s): "
              f"{stats['skipped']} skipped, {stats['count'] - stats['skipped'] - stats['failed']} compressed, "
              f"{stats['failed']} failed.")

    return stats


# ==============================================================================
# STEP 3: VALIDATE FILE SIZES (strictly under the limit)
# ==============================================================================
def validate_step(
    compressed_root: Path,
    max_mb: float = 50.0,
    max_pages: int = 500,
    pdf_files=None,
    quiet=False,
):
    """Validates that PDFs are under the byte limit and within the page limit.

    When ``quiet`` is True, per-file PASS/FAIL lines are suppressed and only
    a summary count is printed.
    """
    if max_pages < 1:
        raise ValueError("The maximum PDF page count must be at least one.")

    stats = {
        "count": 0, "passed": 0, "failed": 0,
        "largest_mb": 0.0, "largest_file": None,
        "largest_pages": 0, "largest_page_file": None,
        "size_overlimit": 0, "page_overlimit": 0, "unreadable": 0,
        "overlimit_files": [],
    }

    if pdf_files is None:
        pdf_files = _discover_pdfs(compressed_root)

    if not pdf_files:
        print("  \u26a0\ufe0f No compressed PDFs found to validate.")
        return True, stats

    max_bytes = max_mb * 1024 * 1024

    for pdf_path in pdf_files:
        rel_path = pdf_path.relative_to(compressed_root)
        file_size_bytes = pdf_path.stat().st_size
        file_size_mb = file_size_bytes / (1024 * 1024)

        stats["count"] += 1
        if file_size_mb > stats["largest_mb"]:
            stats["largest_mb"] = file_size_mb
            stats["largest_file"] = str(rel_path)

        try:
            with pymupdf.open(pdf_path) as doc:
                page_count = doc.page_count
        except Exception as error:
            stats["unreadable"] += 1
            stats["failed"] += 1
            stats["overlimit_files"].append((str(rel_path), file_size_mb, None))
            if not quiet:
                print(f"  \u274c [UNREADABLE] {rel_path} -> {error}")
            continue

        if page_count > stats["largest_pages"]:
            stats["largest_pages"] = page_count
            stats["largest_page_file"] = str(rel_path)

        size_exceeded = file_size_bytes >= max_bytes
        pages_exceeded = page_count > max_pages
        if size_exceeded or pages_exceeded:
            stats["overlimit_files"].append(
                (str(rel_path), file_size_mb, page_count)
            )
            stats["failed"] += 1
            if size_exceeded:
                stats["size_overlimit"] += 1
            if pages_exceeded:
                stats["page_overlimit"] += 1
            if not quiet:
                reasons = []
                if size_exceeded:
                    reasons.append(f"size must be under {max_mb} MB")
                if pages_exceeded:
                    reasons.append(f"pages must be at most {max_pages}")
                print(
                    f"  \u274c [EXCEEDS LIMIT] {rel_path} -> "
                    f"{file_size_mb:.2f} MB, {page_count} pages "
                    f"({' and '.join(reasons)})"
                )
        else:
            stats["passed"] += 1
            if not quiet:
                print(
                    f"  \u2705 [PASS] {rel_path} -> "
                    f"{file_size_mb:.2f} MB, {page_count} pages"
                )

    if quiet:
        print(
            f"  \u2139\ufe0f Validated {stats['count']} file(s): "
            f"{stats['passed']} passed, {stats['failed']} failed "
            f"({stats['size_overlimit']} by size, "
            f"{stats['page_overlimit']} by pages, "
            f"{stats['unreadable']} unreadable)."
        )

    if stats["overlimit_files"]:
        print(
            f"\n\U0001f6a8 VALIDATION FAILED: "
            f"{len(stats['overlimit_files'])} file(s) exceed the limits "
            f"(under {max_mb} MB and at most {max_pages} pages)."
        )
        return False, stats

    print(
        f"\n\U0001f389 ALL CLEAR: All files are strictly under {max_mb} MB "
        f"and contain at most {max_pages} pages."
    )
    return True, stats


# ==============================================================================
# STEP 4: PRINT SUMMARY STATISTICS
# ==============================================================================
def print_summary(
    compress_stats: dict,
    validate_stats: dict,
    max_mb: float,
    max_pages: int = 500,
    chunk_stats: dict | None = None,
):
    orig_mb = compress_stats["orig_bytes"] / (1024 * 1024)
    new_mb = compress_stats["new_bytes"] / (1024 * 1024)
    saved_mb = orig_mb - new_mb
    saved_pct = (saved_mb / orig_mb * 100) if orig_mb > 0 else 0

    print("\n==================================================================")
    print("\U0001f4ca SUMMARY STATISTICS")
    print("==================================================================")
    print(f"  PDFs compressed        : {compress_stats['count']}  (failed: {compress_stats['failed']}, skipped: {compress_stats.get('skipped', 0)})")
    print(f"  Total size before      : {orig_mb:.2f} MB")
    print(f"  Total size after       : {new_mb:.2f} MB")
    print(f"  Total space saved      : {saved_mb:.2f} MB ({saved_pct:.1f}%)")
    print(f"  Files validated        : {validate_stats['count']}")
    print(f"  \u2705 Passed both limits    : {validate_stats['passed']}")
    print(f"  \u274c Failed any limit      : {validate_stats['failed']}")
    print(f"     Size failures (>= {max_mb} MB): {validate_stats['size_overlimit']}")
    print(f"     Page failures (> {max_pages}) : {validate_stats['page_overlimit']}")
    print(f"     Unreadable PDFs          : {validate_stats['unreadable']}")
    if validate_stats["largest_file"]:
        print(f"  Largest output file    : {validate_stats['largest_file']} ({validate_stats['largest_mb']:.2f} MB)")
    if validate_stats["largest_page_file"]:
        print(f"  Largest page count     : {validate_stats['largest_page_file']} ({validate_stats['largest_pages']} pages)")
    if chunk_stats is not None:
        print(f"  Files chunked          : {chunk_stats['chunked']}")
        print(f"  Chunks produced        : {chunk_stats['produced']}")
        print(f"  Oversized pages rescued : {chunk_stats.get('rescued_pages', 0)}")
        print(f"  Chunks still over limit : {chunk_stats['still_over']}")
        print(f"  Chunk failures         : {chunk_stats['failed']}")
    print("==================================================================")

    # Highlight any files that are still over the limit so they stand out
    overlimit_files = validate_stats.get("overlimit_files", [])
    if overlimit_files:
        print(f"\n\U0001f6a8 \U0001f6a8 \U0001f6a8  FILES STILL OVER THE OUTPUT LIMITS  \U0001f6a8 \U0001f6a8 \U0001f6a8")
        print("------------------------------------------------------------------")
        for overlimit_file in overlimit_files:
            rel_path, size_mb, *page_count_values = overlimit_file
            page_count = page_count_values[0] if page_count_values else None
            page_text = (
                f", {page_count} pages"
                if page_count is not None
                else ", unreadable"
            )
            print(f"  \u274c {rel_path}  ->  {size_mb:.2f} MB{page_text}")
        print("------------------------------------------------------------------")
        print(f"  {len(overlimit_files)} file(s) need manual review / further compression.\n")


# ==============================================================================
# STEP 5: ASSERT FILE COUNT (cross-reference source vs output)
# ==============================================================================
def assert_file_count(source_root: Path, compressed_root: Path, pdf_only: bool, output_pdfs=None, chunked_count: int = 0):
    """Asserts that every convertible document in the source produced a PDF in the output.

    When chunking has occurred (chunked_count > 0), the output will contain MORE
    PDFs than source documents, so the pass condition becomes actual >= expected.
    """
    if pdf_only:
        source_files = _discover_pdfs(source_root)
        expected = len(source_files)
        source_desc = ".pdf"
    else:
        source_files = []
        for pattern in ("*.doc", "*.docx"):
            source_files.extend(f for f in source_root.rglob(pattern) if not f.name.startswith("~$"))
        source_files.extend(_discover_pdfs(source_root))
        # Deduplicate (a file won't match two patterns, but be safe)
        source_files = sorted(set(source_files))
        expected = len(source_files)
        source_desc = ".doc/.docx/.pdf"

    if output_pdfs is None:
        output_pdfs = _discover_pdfs(compressed_root)
    actual = len(output_pdfs)

    print("\n==================================================================")
    print("\U0001f50d FILE COUNT CHECK (source vs output)")
    print("==================================================================")
    print(f"  Source files ({source_desc}) : {expected}")
    print(f"  Output PDFs            : {actual}")

    if chunked_count > 0:
        # When chunking occurred, output has more PDFs than source documents.
        if actual >= expected:
            print(f"  \u2705 MATCH (with chunking): All {expected} source document(s) produced PDFs in the output.")
            print(f"     ({chunked_count} file(s) were chunked into multiple PDFs; output has {actual} total.)")
            print("==================================================================")
            return True
        else:
            print(f"  \u274c MISMATCH: {expected - actual} source document(s) are MISSING from the output!")
            output_stems = {f.stem for f in output_pdfs}
            missing = [f for f in source_files if f.stem not in output_stems]
            if missing:
                print("      Missing source documents:")
                for f in missing:
                    print(f"        \u2022 {f.relative_to(source_root)}")
            print("==================================================================")
            return False
    elif actual == expected:
        print(f"  \u2705 MATCH: All {expected} source document(s) produced a PDF in the output.")
    elif actual > expected:
        print(f"  \u26a0\ufe0f  MISMATCH: Output has {actual - expected} MORE PDF(s) than source documents.")
        print(f"      This may indicate leftover files from a previous run.")
    else:
        print(f"  \u274c MISMATCH: {expected - actual} source document(s) are MISSING from the output!")
        # Identify which source files have no matching output PDF
        output_stems = {f.stem for f in output_pdfs}
        missing = [f for f in source_files if f.stem not in output_stems]
        if missing:
            print("      Missing source documents:")
            for f in missing:
                print(f"        \u2022 {f.relative_to(source_root)}")
    print("==================================================================")
    return actual == expected


def _serialize_pdf_range(doc, start_page: int, end_page: int) -> bytes:
    """Serializes pages [start_page, end_page) using the final save settings."""
    chunk_doc = pymupdf.open()
    try:
        chunk_doc.insert_pdf(doc, from_page=start_page, to_page=end_page - 1)
        return chunk_doc.tobytes(garbage=3, deflate=True)
    finally:
        chunk_doc.close()


def _rescue_oversized_page(doc, page_index: int, max_bytes: float):
    """Rasterizes one oversized page at progressively smaller settings."""
    page = doc[page_index]
    attempts = (
        (180, 75),
        (150, 70),
        (120, 60),
        (96, 50),
        (72, 40),
        (50, 30),
    )

    for dpi, jpeg_quality in attempts:
        pixmap = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY, alpha=False)
        image = Image.frombytes("L", (pixmap.width, pixmap.height), pixmap.samples)
        image_buffer = io.BytesIO()
        image.save(
            image_buffer,
            format="JPEG",
            quality=jpeg_quality,
            optimize=True,
        )

        rescued_doc = pymupdf.open()
        try:
            rescued_page = rescued_doc.new_page(
                width=page.rect.width,
                height=page.rect.height,
            )
            rescued_page.insert_image(
                rescued_page.rect,
                stream=image_buffer.getvalue(),
            )
            rescued_bytes = rescued_doc.tobytes(garbage=3, deflate=True)
        finally:
            rescued_doc.close()

        if len(rescued_bytes) < max_bytes:
            return rescued_bytes, dpi, jpeg_quality

    return None


def _stage_precise_chunks(
    pdf_path: Path,
    staging_dir: Path,
    name_prefix: str,
    max_bytes: float,
    max_pages: int = 500,
) -> list[dict]:
    """Builds ordered chunks within exact byte and page-count limits."""
    if max_bytes <= 0:
        raise ValueError("The maximum PDF size must be greater than zero.")
    if max_pages < 1:
        raise ValueError("The maximum PDF page count must be at least one.")

    doc = pymupdf.open(pdf_path)
    chunks = []

    try:
        total_pages = len(doc)
        if total_pages == 0:
            raise ValueError("The PDF contains no pages.")

        start_page = 0
        while start_page < total_pages:
            end_page = start_page
            accepted_bytes = None

            while (
                end_page < total_pages
                and end_page - start_page < max_pages
            ):
                candidate_bytes = _serialize_pdf_range(
                    doc,
                    start_page,
                    end_page + 1,
                )
                if len(candidate_bytes) >= max_bytes:
                    break
                accepted_bytes = candidate_bytes
                end_page += 1

            rescued = False
            rescue_settings = None
            if accepted_bytes is None:
                rescue_result = _rescue_oversized_page(
                    doc,
                    start_page,
                    max_bytes,
                )
                if rescue_result is None:
                    page_number = start_page + 1
                    raise ValueError(
                        f"page {page_number} cannot be reduced below the size limit"
                    )
                accepted_bytes, dpi, jpeg_quality = rescue_result
                end_page = start_page + 1
                rescued = True
                rescue_settings = (dpi, jpeg_quality)

            chunk_number = len(chunks) + 1
            chunk_path = staging_dir / f"{name_prefix}_chunk-{chunk_number}.pdf"
            chunk_path.write_bytes(accepted_bytes)
            if chunk_path.stat().st_size >= max_bytes:
                raise RuntimeError(
                    f"staged chunk {chunk_number} is not strictly under the size limit"
                )
            if end_page - start_page > max_pages:
                raise RuntimeError(
                    f"staged chunk {chunk_number} exceeds the page limit"
                )

            chunks.append({
                "path": chunk_path,
                "start_page": start_page,
                "end_page": end_page,
                "size_bytes": len(accepted_bytes),
                "rescued": rescued,
                "rescue_settings": rescue_settings,
            })
            start_page = end_page
    finally:
        doc.close()

    return chunks


def _commit_precise_chunks(
    chunks: list[dict],
    output_pdf: Path,
    output_dir: Path,
    name_prefix: str,
) -> list[Path]:
    """Atomically replaces one over-limit PDF and its stale chunks."""
    backup_dir = chunks[0]["path"].parent / "backup"
    backup_dir.mkdir()
    stale_prefix = f"{name_prefix}_chunk-"
    stale_chunks = [
        path
        for path in output_dir.iterdir()
        if path.is_file()
        and path.name.startswith(stale_prefix)
        and path.suffix.lower() == ".pdf"
    ]
    old_paths = stale_chunks
    if output_pdf.exists() and output_pdf not in old_paths:
        old_paths.append(output_pdf)

    backups = []
    committed = []
    try:
        for old_path in old_paths:
            backup_path = backup_dir / old_path.name
            old_path.replace(backup_path)
            backups.append((backup_path, old_path))

        for chunk in chunks:
            final_path = output_dir / chunk["path"].name
            chunk["path"].replace(final_path)
            chunk["path"] = final_path
            committed.append(final_path)
    except Exception:
        for final_path in committed:
            if final_path.exists():
                final_path.unlink()
        for backup_path, old_path in reversed(backups):
            if backup_path.exists():
                backup_path.replace(old_path)
        raise

    return committed


def chunk_step(
    overlimit_files: list,
    compressed_root: Path,
    max_mb: float,
    source_root: Path | None = None,
    max_pages: int = 500,
) -> dict:
    """Chunks over-limit PDFs once using exact byte and page-count limits.

    Args:
        overlimit_files: tuples from validate_step containing path, size, and pages.
        compressed_root: the output folder containing the compressed PDFs.
        max_mb: the strict size limit each chunk must be under.
        max_pages: the maximum page count allowed in each chunk.
        source_root: the original source folder. When --skip-copy is used and
            over-limit files failed compression (so they're not in compressed_root),
            the chunk step falls back to the source file.

    Returns a stats dict: {chunked, produced, still_over, failed, rescued_pages}
    """
    stats = {
        "chunked": 0,
        "produced": 0,
        "still_over": 0,
        "failed": 0,
        "rescued_pages": 0,
    }
    max_bytes = max_mb * 1024 * 1024

    if not overlimit_files:
        return stats

    print(f"\n--- STEP 3b: EXACT SIZE CHUNKING ({len(overlimit_files)} over-limit file(s)) ---")

    for overlimit_file in overlimit_files:
        rel_path_str, size_mb, *page_count_values = overlimit_file
        page_count = page_count_values[0] if page_count_values else None
        pdf_path = compressed_root / rel_path_str
        if not pdf_path.exists():
            # With --skip-copy, over-limit files may not have been copied to the
            # output folder (especially if compression failed). Fall back to the
            # source file so we can still chunk it.
            if source_root is not None:
                source_path = source_root / rel_path_str
                if source_path.exists():
                    pdf_path = source_path
                    print(f"  \u2139\ufe0f  File not in output folder; using source: {rel_path_str}")
                else:
                    print(f"  \u274c File not found: {rel_path_str}")
                    stats["failed"] += 1
                    continue
            else:
                print(f"  \u274c File not found: {rel_path_str}")
                stats["failed"] += 1
                continue

        stem = pdf_path.stem
        output_pdf = compressed_root / rel_path_str
        output_dir = compressed_root / Path(rel_path_str).parent
        output_dir.mkdir(parents=True, exist_ok=True)
        page_note = f", {page_count} pages" if page_count is not None else ""
        print(
            f"  \U0001f4c4 Chunking: {rel_path_str} "
            f"({size_mb:.2f} MB{page_note})"
        )

        try:
            with tempfile.TemporaryDirectory(
                prefix=f".{stem}_chunks_",
                dir=output_dir,
            ) as temporary_dir:
                chunks = _stage_precise_chunks(
                    pdf_path,
                    Path(temporary_dir),
                    stem,
                    max_bytes,
                    max_pages=max_pages,
                )
                chunk_paths = _commit_precise_chunks(
                    chunks,
                    output_pdf,
                    output_dir,
                    stem,
                )

            stats["chunked"] += 1
            stats["produced"] += len(chunk_paths)
            for chunk, chunk_path in zip(chunks, chunk_paths):
                rel = chunk_path.relative_to(compressed_root)
                chunk_mb = chunk["size_bytes"] / (1024 * 1024)
                page_range = (
                    f"p. {chunk['start_page'] + 1}"
                    if chunk["end_page"] == chunk["start_page"] + 1
                    else f"pp. {chunk['start_page'] + 1}-{chunk['end_page']}"
                )
                rescue_note = ""
                if chunk["rescued"]:
                    dpi, quality = chunk["rescue_settings"]
                    stats["rescued_pages"] += 1
                    rescue_note = f", rasterized at {dpi} DPI / quality {quality}"
                print(
                    f"     \u2022 Produced: {rel} "
                    f"({page_range}, {chunk_mb:.2f} MB{rescue_note})"
                )
        except Exception as e:
            print(f"  \u274c Failed to chunk {rel_path_str}: {e}")
            stats["failed"] += 1
            stats["still_over"] += 1
            if not output_pdf.exists() and pdf_path != output_pdf:
                try:
                    shutil.copy2(pdf_path, output_pdf)
                except Exception as copy_error:
                    print(f"     \u274c Could not preserve failed source in output: {copy_error}")

    if stats["still_over"] > 0:
        print(f"\n  \u26a0\ufe0f  {stats['still_over']} file(s) could not be chunked below {max_mb} MB.")
        print("     The original files were preserved for manual review.")
    else:
        print(
            f"\n  \u2705 All chunks are under {max_mb} MB "
            f"and contain at most {max_pages} pages."
        )

    return stats


# ==============================================================================
# MAIN PIPELINE EXECUTION
# ==============================================================================
def resolve_output_root(source_root: Path, output_arg: str | None, suffix: str) -> Path:
    """Resolves the final compressed-output folder location.

    Rules:
      - If output_arg is None -> default behavior: "{source folder name} {suffix}"
        created as a SIBLING of the source folder (unchanged from before).
      - If output_arg is a bare name (no path separators, e.g. "FinalSubmission")
        -> also created as a sibling of the source folder, just under that name
        instead of the auto-generated one.
      - If output_arg contains a path separator or is an absolute path
        (e.g. "D:/Tenders/Final", "/mnt/d/Tenders/Final", "../Output",
        "/data/output") -> used EXACTLY as given (resolved to an absolute path).
    """
    if not output_arg:
        return source_root.parent / f"{source_root.name} {suffix}"

    looks_like_path = ("/" in output_arg) or ("\\" in output_arg) or Path(output_arg).is_absolute()

    if looks_like_path:
        return Path(output_arg).expanduser().resolve()
    else:
        # Bare folder name -> keep it next to the source folder, same convention
        # as the default, just with a user-chosen name instead of "<name> compressed".
        return source_root.parent / output_arg

def _publish_output_tree(staged_root: Path, final_root: Path) -> None:
    """Publishes a completed output tree while preserving the prior tree on failure."""
    final_root.parent.mkdir(parents=True, exist_ok=True)
    backup_root = final_root.parent / f".{final_root.name}.backup_{os.getpid()}"
    if backup_root.exists():
        raise FileExistsError(f"stale output backup exists: {backup_root}")

    previous_moved = False
    try:
        if final_root.exists():
            final_root.replace(backup_root)
            previous_moved = True
        staged_root.replace(final_root)
    except Exception:
        if previous_moved and backup_root.exists() and not final_root.exists():
            backup_root.replace(final_root)
        raise

    if previous_moved:
        if backup_root.is_dir():
            shutil.rmtree(backup_root)
        else:
            backup_root.unlink()


def run_tender_pipeline(
    source_folder_path: str,
    target_dpi=200,
    jpeg_quality=80,
    dpi_threshold: int | None = None,
    max_mb=50.0,
    max_pages: int = 500,
    output_folder: str | None = None,
    pdf_only: bool = False,
    silent: bool = False,
    no_chunk: bool = False,
    skip_copy: bool = False,
    quiet: bool = False,
    skip_compression: bool = False,
    workers: int | None = None,
):
    source_root = Path(source_folder_path).resolve()

    if not source_root.exists() or not source_root.is_dir():
        print(f"Error: Source directory '{source_root}' does not exist.")
        sys.exit(1)
    if target_dpi <= 0:
        raise ValueError("--dpi must be positive")
    if not 1 <= jpeg_quality <= 100:
        raise ValueError("--quality must be between 1 and 100")
    if dpi_threshold is not None and dpi_threshold <= target_dpi:
        raise ValueError("--dpi-threshold must be greater than --dpi")
    if max_mb <= 0:
        raise ValueError("--max-mb must be positive")
    if max_pages < 1:
        raise ValueError("--max-pages must be at least 1")
    if workers is not None and workers < 1:
        raise ValueError("--workers must be at least 1")

    final_output_root = resolve_output_root(source_root, output_folder, "compressed")
    final_output_root.parent.mkdir(parents=True, exist_ok=True)
    run_root = Path(tempfile.mkdtemp(
        prefix=f".{final_output_root.name}.run_",
        dir=final_output_root.parent,
    ))
    converted_root = run_root / "all-pdfs"
    compressed_root = run_root / "output"
    compressed_root.mkdir(parents=True)

    print("==================================================================")
    print(f"\U0001f680 STARTING TENDER DOCUMENT PIPELINE FOR: {source_root.name}")
    print("==================================================================")
    print(
        f"\u26a0\ufe0f Output limits: strictly under {max_mb} MB and at most "
        f"{max_pages} pages per PDF. Files over {max_pages} pages will be chunked."
    )

    if pdf_only:
        print("\n--- STEP 1: SKIPPED (--pdf-only: compressing existing PDFs directly) ---")
        # Use the source folder directly as the pool of PDFs to compress
        converted_root = source_root
    else:
        print("\n--- STEP 1: CONVERTING WORD DOCS (.doc/.docx) TO PDF ---")
        convert_docx_step(source_root, converted_root)

        raw_pdfs = _discover_pdfs(source_root)
        for pdf in raw_pdfs:
            rel_path = pdf.relative_to(source_root)
            dest = converted_root / rel_path
            dest.parent.mkdir(parents=True, exist_ok=True)
            if not dest.exists():
                shutil.copy2(pdf, dest)
        if raw_pdfs:
            print(f"  \u2022 Synced {len(raw_pdfs)} pre-existing PDF(s) into the conversion workspace.")

    if skip_compression:
        print("\n--- STEP 2: SKIPPED (--skip-compression: copying all PDFs as-is) ---")
    else:
        print("\n--- STEP 2: COMPRESSING ALL PDFS ---")
    compress_stats = compress_step(
        converted_root, compressed_root, target_dpi=target_dpi, jpeg_quality=jpeg_quality,
        max_mb=max_mb, skip_copy=skip_copy, quiet=quiet, skip_compression=skip_compression,
        dpi_threshold=dpi_threshold, workers=workers, max_pages=max_pages,
    )

    print("\n--- STEP 3: VALIDATING FINAL FILE SIZES ---")
    # Collect the output PDF list once and reuse it for validation + count check
    # (avoids re-walking the output tree two extra times).
    output_pdfs = _discover_pdfs(compressed_root)
    if skip_copy and not output_pdfs:
        # No files were copied to the output folder (all under limit, skip-copy on).
        # Validate the source files directly instead.
        print("  \u2139\ufe0f --skip-copy: no files in output folder. Validating source files directly.")
        source_pdfs = _discover_pdfs(converted_root)
        passed, validate_stats = validate_step(
            converted_root, max_mb=max_mb, max_pages=max_pages,
            pdf_files=source_pdfs, quiet=quiet,
        )
    else:
        passed, validate_stats = validate_step(
            compressed_root, max_mb=max_mb, max_pages=max_pages,
            pdf_files=output_pdfs, quiet=quiet,
        )

    # --- STEP 3b: EXACT SIZE CHUNKING ---
    # If files are still over the limit after compression, offer to chunk them.
    # --silent auto-proceeds; otherwise the user is prompted interactively.
    # --no-chunk disables chunking entirely.
    chunk_stats = None
    if not passed and not no_chunk and validate_stats["overlimit_files"]:
        overlimit = validate_stats["overlimit_files"]
        proceed = silent  # auto-proceed in silent mode

        if not silent:
            print(
                f"\n  {len(overlimit)} file(s) exceed the size or "
                f"{max_pages}-page limit."
            )
            print("  Chunking can split them to satisfy both limits.")
            try:
                answer = input("\n  Proceed with chunking? [y/N] ").strip().lower()
                proceed = answer in ("y", "yes")
            except (EOFError, KeyboardInterrupt):
                proceed = False

        if proceed:
            chunk_stats = chunk_step(
                overlimit, compressed_root, max_mb,
                source_root=source_root if skip_copy else None,
                max_pages=max_pages,
            )

            # Re-validate after chunking.
            print("\n--- STEP 3b: RE-VALIDATING AFTER CHUNKING ---")
            output_pdfs = _discover_pdfs(compressed_root)
            passed, validate_stats = validate_step(
                compressed_root, max_mb=max_mb, max_pages=max_pages,
                pdf_files=output_pdfs, quiet=quiet,
            )
        else:
            print("\n  \u23ed\ufe0f Chunking skipped.")

    print_summary(
        compress_stats, validate_stats, max_mb,
        max_pages=max_pages, chunk_stats=chunk_stats,
    )

    chunked_count = chunk_stats["chunked"] if chunk_stats else 0
    if skip_copy:
        # With --skip-copy, the output folder intentionally contains only
        # compressed/chunked files, not the 1731 under-limit files that were
        # left in place. Skip the count check since it would always mismatch.
        count_ok = True
        print("\n  \u2139\ufe0f --skip-copy: file count check skipped (output folder intentionally "
              "contains only compressed/chunked files).")
    else:
        count_ok = assert_file_count(
            source_root, compressed_root, pdf_only=pdf_only,
            output_pdfs=output_pdfs, chunked_count=chunked_count,
        )

    compression_ok = compress_stats["failed"] == 0
    print()
    if passed and count_ok and compression_ok:
        try:
            _publish_output_tree(compressed_root, final_output_root)
            shutil.rmtree(run_root, ignore_errors=True)
        except Exception as error:
            print(f"Failed to publish completed output: {error}")
            print(f"Staged files retained at: {run_root}")
            sys.exit(1)
        print("\u2705 PIPELINE COMPLETED SUCCESSFULLY! Documents ready for submission.")
        print(f"\U0001f4c1 Final files location: {final_output_root}")
    else:
        print(f"Staged files retained at: {run_root}")
        if not passed:
            print("\u274c PIPELINE COMPLETED WITH WARNINGS: Some files exceed the limit.")
        if not count_ok:
            print("\u274c PIPELINE COMPLETED WITH WARNINGS: File count mismatch (see above).")
        if not compression_ok:
            print("\u274c PIPELINE COMPLETED WITH WARNINGS: One or more PDFs failed compression.")
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Master pipeline for preparing tender submission documents: "
        "Word-to-PDF conversion, compression, and size validation."
    )
    parser.add_argument("-i", "--input", type=str, default="/data/my_tender_docs",
                         help="Path to the source folder containing raw tender documents")
    parser.add_argument("-o", "--output", type=str, default=None,
                         help="Name or path for the FINAL compressed output folder. "
                              "Bare name (e.g. 'FinalSubmission') -> created next to the "
                              "source folder. Path (e.g. '/mnt/d/Tenders/Final' or "
                              "'D:/Tenders/Final') -> used exactly as given. "
                              "Default: '<source folder name> compressed'.")
    parser.add_argument(
        "--dpi",
        type=int,
        default=200,
        help="Target DPI for high-resolution images (minimum 200 recommended for OCR)",
    )
    parser.add_argument(
        "--dpi-threshold",
        type=int,
        default=None,
        help="Only downsample images above this effective DPI (default: 1.5 x --dpi)",
    )
    parser.add_argument(
        "-q",
        "--quality",
        type=int,
        default=80,
        help="JPEG quality for rewritten images (1-100; color is preserved)",
    )
    parser.add_argument("--max-mb", type=float, default=50.0, help="Max allowed file size in MB")
    parser.add_argument(
        "--max-pages",
        type=int,
        default=500,
        help="Maximum pages allowed per output PDF (default: 500)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=None,
        help="Concurrent PDF compression processes (default: 2; use 1 for low-memory systems)",
    )
    parser.add_argument("--pdf-only", action="store_true",
                         help="Skip Word-to-PDF conversion and compress existing PDFs directly")
    parser.add_argument("--silent", action="store_true",
                         help="Auto-proceed chunking without prompting when files exceed the limit")
    parser.add_argument("--no-chunk", action="store_true",
                         help="Disable chunking entirely (even if files exceed the limit)")
    parser.add_argument("--skip-copy", action="store_true",
                         help="Skip copying under-limit files to the output folder. "
                              "Only compressed/chunked files are written. Dramatically "
                              "faster on slow filesystems (e.g. WSL shared mounts).")
    parser.add_argument("--quiet", action="store_true",
                         help="Suppress per-file output (skipped/compressed/PASS lines). "
                              "Show only summary counts instead.")
    parser.add_argument("--skip-compression", action="store_true",
                         help="Skip the compression step entirely. All files are copied "
                              "as-is to the output folder. Only validation and chunking "
                              "are performed.")

    args = parser.parse_args()

    run_tender_pipeline(
        source_folder_path=args.input,
        target_dpi=args.dpi,
        jpeg_quality=args.quality,
        dpi_threshold=args.dpi_threshold,
        max_mb=args.max_mb,
        max_pages=args.max_pages,
        output_folder=args.output,
        pdf_only=args.pdf_only,
        silent=args.silent,
        no_chunk=args.no_chunk,
        skip_copy=args.skip_copy,
        quiet=args.quiet,
        skip_compression=args.skip_compression,
        workers=args.workers,
    )
