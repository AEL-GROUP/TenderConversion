"""
pdf_tender_pipeline.py
======================
Master pipeline for preparing tender submission documents.

Steps
-----
  STEP 1: Convert Word documents (.doc AND .docx) to PDF via LibreOffice.
          (Skipped when --pdf-only is passed; existing PDFs are compressed directly.)
  STEP 2: Compress every PDF (grayscale + DPI downsampling) via PyMuPDF/Pillow.
          Files already under the size threshold are copied as-is.
  STEP 3: Validate every compressed PDF is strictly under a size threshold
          (default 50 MB).
  STEP 3b: Chunk any files still over the limit into smaller PDFs using
          page-count splitting. Re-chunks any chunks that are still over the
          limit with a letter suffix. Skipped when --no-chunk is passed or the
          user declines the interactive prompt (unless --silent auto-proceeds).
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
import io
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pymupdf  # PyMuPDF
from PIL import Image

# File extensions LibreOffice will convert to PDF
WORD_EXTENSIONS = ("*.doc", "*.docx")


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
def compress_single_pdf(input_path: Path, output_path: Path, target_dpi=200, jpeg_quality=80):
    """Compresses a single PDF by downsampling and converting images to grayscale."""
    doc = pymupdf.open(input_path)
    processed_xrefs = set()

    try:
        for page in doc:
            page_width_in = page.rect.width / 72.0
            max_width_px = max(1, int(page_width_in * target_dpi))

            for img in page.get_images():
                xref = img[0]
                if xref in processed_xrefs or xref == 0:
                    continue
                processed_xrefs.add(xref)

                base_image = doc.extract_image(xref)
                image_bytes = base_image["image"]

                try:
                    pil_img = Image.open(io.BytesIO(image_bytes))
                    pil_img.load()
                except Exception:
                    continue

                width, height = pil_img.size

                # Skip re-encoding if the image is already optimized:
                # small enough, already grayscale, and already JPEG.
                if (
                    width <= max_width_px
                    and pil_img.mode == "L"
                    and base_image.get("ext", "").lower() == "jpeg"
                ):
                    continue

                if width > max_width_px:
                    scale_factor = max_width_px / float(width)
                    new_height = max(1, int(float(height) * scale_factor))
                    pil_img = pil_img.resize(
                        (max_width_px, new_height), Image.Resampling.LANCZOS
                    )

                if pil_img.mode != "L":
                    pil_img = pil_img.convert("L")

                buffer = io.BytesIO()
                pil_img.save(buffer, format="JPEG", quality=jpeg_quality, optimize=True)
                page.replace_image(xref, stream=buffer.getvalue())

        output_path.parent.mkdir(parents=True, exist_ok=True)
        doc.save(output_path, garbage=3, deflate=True)
    finally:
        doc.close()


def compress_step(converted_root: Path, compressed_root: Path, target_dpi=200, jpeg_quality=80, max_mb=50.0, skip_copy=False, quiet=False, skip_compression=False):
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
    stats = {"count": 0, "failed": 0, "orig_bytes": 0, "new_bytes": 0, "skipped": 0}

    pdf_files = list(converted_root.rglob("*.pdf"))

    if not pdf_files:
        print("  \u2139\ufe0f No .pdf files found to compress.")
        return stats

    max_bytes = max_mb * 1024 * 1024
    if skip_compression:
        print(f"  Found {len(pdf_files)} PDF file(s) to process (--skip-compression: copying all as-is)...")
    else:
        print(f"  Found {len(pdf_files)} PDF file(s) to process (threshold: {max_mb} MB)...")

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
                # Don't copy — just record stats. The file stays in its original location.
                stats["skipped"] += 1
                stats["count"] += 1
                stats["orig_bytes"] += orig_bytes
                stats["new_bytes"] += orig_bytes
                continue
            output_pdf_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(pdf_path, output_pdf_path)
            if not quiet:
                print(f"  \u23ed\ufe0f Skipped (under {max_mb} MB): {rel_path} ({orig_mb:.2f} MB) -> copied as-is")
            stats["skipped"] += 1
            stats["count"] += 1
            stats["orig_bytes"] += orig_bytes
            stats["new_bytes"] += orig_bytes
            continue

        try:
            compress_single_pdf(
                pdf_path, output_pdf_path, target_dpi=target_dpi, jpeg_quality=jpeg_quality
            )
            new_bytes = output_pdf_path.stat().st_size
            new_mb = new_bytes / (1024 * 1024)
            savings = (((orig_mb - new_mb) / orig_mb) * 100) if orig_mb > 0 else 0
            if not quiet:
                print(f"  \u2022 Compressed: {rel_path} ({orig_mb:.2f}MB \u2192 {new_mb:.2f}MB, -{savings:.1f}%)")

            stats["count"] += 1
            stats["orig_bytes"] += orig_bytes
            stats["new_bytes"] += new_bytes
        except Exception as e:
            print(f"  \u274c Failed compression for {pdf_path.name}: {e}")
            stats["failed"] += 1

    if quiet:
        print(f"  \u2139\ufe0f Processed {stats['count']} file(s): "
              f"{stats['skipped']} skipped, {stats['count'] - stats['skipped'] - stats['failed']} compressed, "
              f"{stats['failed']} failed.")

    return stats


# ==============================================================================
# STEP 3: VALIDATE FILE SIZES (strictly under the limit)
# ==============================================================================
def validate_step(compressed_root: Path, max_mb: float = 50.0, pdf_files=None, quiet=False):
    """Validates that all compressed PDFs are STRICTLY under the size limit.

    When ``quiet`` is True, per-file PASS/FAIL lines are suppressed and only
    a summary count is printed.
    """
    stats = {
        "count": 0, "passed": 0, "failed": 0,
        "largest_mb": 0.0, "largest_file": None,
        "overlimit_files": [],
    }

    if pdf_files is None:
        pdf_files = list(compressed_root.rglob("*.pdf"))

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

        if file_size_bytes >= max_bytes:
            stats["overlimit_files"].append((str(rel_path), file_size_mb))
            stats["failed"] += 1
            if not quiet:
                print(f"  \u274c [EXCEEDS LIMIT] {rel_path} -> {file_size_mb:.2f} MB")
        else:
            stats["passed"] += 1
            if not quiet:
                print(f"  \u2705 [PASS] {rel_path} -> {file_size_mb:.2f} MB")

    if quiet:
        print(f"  \u2139\ufe0f Validated {stats['count']} file(s): "
              f"{stats['passed']} passed, {stats['failed']} over limit.")

    if stats["overlimit_files"]:
        print(f"\n\U0001f6a8 VALIDATION FAILED: {len(stats['overlimit_files'])} file(s) at/over {max_mb} MB!")
        return False, stats

    print(f"\n\U0001f389 ALL CLEAR: All files are verified strictly under {max_mb} MB.")
    return True, stats


# ==============================================================================
# STEP 4: PRINT SUMMARY STATISTICS
# ==============================================================================
def print_summary(compress_stats: dict, validate_stats: dict, max_mb: float, chunk_stats: dict | None = None):
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
    print(f"  \u2705 Passed (< {max_mb} MB)     : {validate_stats['passed']}")
    print(f"  \u274c Failed (>= {max_mb} MB)    : {validate_stats['failed']}")
    if validate_stats["largest_file"]:
        print(f"  Largest output file    : {validate_stats['largest_file']} ({validate_stats['largest_mb']:.2f} MB)")
    if chunk_stats and (chunk_stats["chunked"] > 0 or chunk_stats["produced"] > 0):
        print(f"  Files chunked          : {chunk_stats['chunked']}")
        print(f"  Chunks produced        : {chunk_stats['produced']}")
        print(f"  Chunks still over limit : {chunk_stats['still_over']}")
        print(f"  Chunk failures         : {chunk_stats['failed']}")
    print("==================================================================")

    # Highlight any files that are still over the limit so they stand out
    overlimit_files = validate_stats.get("overlimit_files", [])
    if overlimit_files:
        print(f"\n\U0001f6a8 \U0001f6a8 \U0001f6a8  FILES STILL OVER THE {max_mb} MB LIMIT  \U0001f6a8 \U0001f6a8 \U0001f6a8")
        print("------------------------------------------------------------------")
        for rel_path, size_mb in overlimit_files:
            print(f"  \u274c {rel_path}  ->  {size_mb:.2f} MB")
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
        source_files = [f for f in source_root.rglob("*.pdf") if not f.name.startswith("~$")]
        expected = len(source_files)
        source_desc = ".pdf"
    else:
        source_files = []
        for pattern in ("*.doc", "*.docx", "*.pdf"):
            source_files.extend(f for f in source_root.rglob(pattern) if not f.name.startswith("~$"))
        # Deduplicate (a file won't match two patterns, but be safe)
        source_files = sorted(set(source_files))
        expected = len(source_files)
        source_desc = ".doc/.docx/.pdf"

    if output_pdfs is None:
        output_pdfs = [f for f in compressed_root.rglob("*.pdf") if not f.name.startswith("~$")]
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


# Max re-chunking passes to prevent infinite loops.
MAX_RECHUNK_PASSES = 2


def _fallback_split_points(num_pages: int, file_size_mb: float, target_mb: float) -> list[int]:
    """Even page-count-based split into chunks of roughly equal page count."""
    if num_pages <= 1:
        return [0]
    if target_mb <= 0:
        # Avoid division by zero: split into one page per chunk.
        return list(range(0, num_pages))
    est_chunks = max(2, int(file_size_mb / target_mb) + 1)
    pages_per_chunk = max(1, num_pages // est_chunks)
    points = list(range(0, num_pages, pages_per_chunk))
    if points[0] != 0:
        points.insert(0, 0)
    return points


def _split_pdf_at_pages(
    pdf_path: Path, output_dir: Path, split_points: list[int], name_prefix: str
) -> list[Path]:
    """Splits a PDF at the given 0-indexed page boundaries.

    Names chunks: {name_prefix}_chunk-1.pdf, {name_prefix}_chunk-2.pdf, etc.
    Returns the list of output file paths.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open(pdf_path)
    total_pages = len(doc)
    output_paths = []

    try:
        for i in range(len(split_points)):
            start = split_points[i]
            end = split_points[i + 1] if i + 1 < len(split_points) else total_pages
            new_doc = pymupdf.open()
            new_doc.insert_pdf(doc, from_page=start, to_page=end - 1)
            chunk_name = f"{name_prefix}_chunk-{i + 1}.pdf"
            chunk_path = output_dir / chunk_name
            new_doc.save(chunk_path, garbage=3, deflate=True)
            new_doc.close()
            output_paths.append(chunk_path)
    finally:
        doc.close()

    return output_paths


def _split_pdf_at_pages_with_suffix(
    pdf_path: Path, output_dir: Path, split_points: list[int], name_prefix: str, suffix_letter: str
) -> list[Path]:
    """Like _split_pdf_at_pages but names chunks with a letter suffix for re-chunking.

    Names chunks: {name_prefix}_chunk-{N}{suffix_letter}.pdf (e.g. _chunk-1a.pdf).
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open(pdf_path)
    total_pages = len(doc)
    output_paths = []

    try:
        for i in range(len(split_points)):
            start = split_points[i]
            end = split_points[i + 1] if i + 1 < len(split_points) else total_pages
            new_doc = pymupdf.open()
            new_doc.insert_pdf(doc, from_page=start, to_page=end - 1)
            chunk_name = f"{name_prefix}_chunk-{i + 1}{suffix_letter}.pdf"
            chunk_path = output_dir / chunk_name
            new_doc.save(chunk_path, garbage=3, deflate=True)
            new_doc.close()
            output_paths.append(chunk_path)
    finally:
        doc.close()

    return output_paths


def chunk_step(
    overlimit_files: list,
    compressed_root: Path,
    max_mb: float,
    source_root: Path | None = None,
) -> dict:
    """Chunks over-limit PDFs into smaller files using page-count splitting.

    Args:
        overlimit_files: list of (rel_path_str, size_mb) tuples from validate_step.
        compressed_root: the output folder containing the compressed PDFs.
        max_mb: the strict size limit each chunk must be under.
        source_root: the original source folder. When --skip-copy is used and
            over-limit files failed compression (so they're not in compressed_root),
            the chunk step falls back to the source file.

    Returns a stats dict: {chunked, produced, still_over, failed}
    """
    stats = {"chunked": 0, "produced": 0, "still_over": 0, "failed": 0}
    max_bytes = max_mb * 1024 * 1024
    target_mb = max_mb * 0.9  # Aim close to the limit (per user choice).

    if not overlimit_files:
        return stats

    print(f"\n--- STEP 3b: PAGE-COUNT CHUNKING ({len(overlimit_files)} over-limit file(s)) ---")

    # First pass: chunk each over-limit file.
    new_chunks = []  # (path, rel_path) for re-validation
    for rel_path_str, size_mb in overlimit_files:
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
        output_dir = compressed_root / Path(rel_path_str).parent
        output_dir.mkdir(parents=True, exist_ok=True)
        num_pages = 0
        doc = pymupdf.open(pdf_path)
        num_pages = len(doc)
        doc.close()

        if num_pages <= 1:
            print(f"  \u274c Cannot chunk (only {num_pages} page): {rel_path_str} ({size_mb:.2f} MB)")
            print(f"     This file needs manual intervention (e.g. re-scan at lower DPI).")
            stats["failed"] += 1
            continue

        print(f"  \U0001f4c4 Chunking: {rel_path_str} ({size_mb:.2f} MB, {num_pages} pages)")

        split_points = _fallback_split_points(num_pages, size_mb, target_mb)
        print(f"     Split points (page indices): {split_points}")

        try:
            chunk_paths = _split_pdf_at_pages(pdf_path, output_dir, split_points, stem)
            # Delete the original over-limit file from the output folder (if it was there).
            out_pdf = compressed_root / rel_path_str
            if out_pdf.exists():
                out_pdf.unlink()
            stats["chunked"] += 1
            stats["produced"] += len(chunk_paths)
            for cp in chunk_paths:
                rel = cp.relative_to(compressed_root)
                new_chunks.append((cp, str(rel)))
                cp_mb = cp.stat().st_size / (1024 * 1024)
                print(f"     \u2022 Produced: {rel} ({cp_mb:.2f} MB)")
        except Exception as e:
            print(f"  \u274c Failed to chunk {rel_path_str}: {e}")
            stats["failed"] += 1
            continue

    # Re-chunking passes for any chunks still over the limit.
    for pass_num in range(1, MAX_RECHUNK_PASSES + 1):
        over_chunks = [(p, r) for (p, r) in new_chunks if p.stat().st_size >= max_bytes]
        if not over_chunks:
            break

        print(f"\n  \U0001f501 RE-CHUNKING PASS {pass_num}: {len(over_chunks)} chunk(s) still over limit")
        rechunk_target_mb = max_mb * 0.6  # Smaller target to ensure they fit.
        suffix_letter = chr(ord("a") + pass_num - 1)  # 'a' for pass 1, 'b' for pass 2.
        next_new_chunks = []

        for chunk_path, rel_str in over_chunks:
            chunk_mb = chunk_path.stat().st_size / (1024 * 1024)
            stem = chunk_path.stem
            output_dir = chunk_path.parent

            doc = pymupdf.open(chunk_path)
            num_pages = len(doc)
            doc.close()

            if num_pages <= 1:
                print(f"     \u274c Cannot re-chunk (only {num_pages} page): {rel_str} ({chunk_mb:.2f} MB)")
                stats["still_over"] += 1
                next_new_chunks.append((chunk_path, rel_str))
                continue

            print(f"     \U0001f4c4 Re-chunking: {rel_str} ({chunk_mb:.2f} MB, {num_pages} pages)")

            split_points = _fallback_split_points(num_pages, chunk_mb, rechunk_target_mb)
            print(f"     Re-split points (page indices): {split_points}")

            try:
                rechunk_paths = _split_pdf_at_pages_with_suffix(
                    chunk_path, output_dir, split_points, stem, suffix_letter
                )
                chunk_path.unlink()
                stats["produced"] += len(rechunk_paths) - 1  # replaced 1 with N
                for rp in rechunk_paths:
                    rel = rp.relative_to(compressed_root)
                    next_new_chunks.append((rp, str(rel)))
                    rp_mb = rp.stat().st_size / (1024 * 1024)
                    print(f"     \u2022 Produced: {rel} ({rp_mb:.2f} MB)")
            except Exception as e:
                print(f"     \u274c Failed to re-chunk {rel_str}: {e}")
                stats["still_over"] += 1
                next_new_chunks.append((chunk_path, rel_str))

        # Replace new_chunks with the updated list for the next pass.
        new_chunks = next_new_chunks

    # Count any chunks still over the limit after all passes.
    final_over = [p for (p, _) in new_chunks if p.stat().st_size >= max_bytes]
    stats["still_over"] = len(final_over)

    if stats["still_over"] > 0:
        print(f"\n  \u26a0\ufe0f  {stats['still_over']} chunk(s) are STILL over {max_mb} MB after re-chunking.")
        print(f"     These may need manual intervention (e.g. re-scan at lower DPI).")
    else:
        print(f"\n  \u2705 All chunks are under {max_mb} MB.")

    # Flatten chunk names: rename all chunks to a clean sequential scheme.
    # e.g. "doc_chunk-2_chunk-1a_chunk-1b.pdf" -> "doc_chunk-1.pdf", "doc_chunk-2.pdf", ...
    _flatten_chunk_names(new_chunks, compressed_root)

    return stats


def _flatten_chunk_names(chunks: list, compressed_root: Path):
    """Renames all chunk files to a clean sequential {stem}_chunk-{N}.pdf scheme.

    After multi-pass re-chunking, files may have nested names like:
      doc_chunk-2_chunk-1a_chunk-1b.pdf
    This flattens them to:
      doc_chunk-1.pdf, doc_chunk-2.pdf, ...

    Groups chunks by their original document stem (everything before the first
    '_chunk-') and renumbers sequentially within each group.
    """
    if not chunks:
        return

    # Group chunks by their original document stem.
    # The original stem is everything before the first "_chunk-" in the filename.
    groups: dict[str, list[Path]] = {}
    for chunk_path, _ in chunks:
        name = chunk_path.name
        # Find the original stem: everything before the first "_chunk-"
        marker = "_chunk-"
        idx = name.find(marker)
        if idx == -1:
            # Not a chunk file, skip.
            continue
        original_stem = name[:idx]
        groups.setdefault(original_stem, []).append(chunk_path)

    renamed = []
    for original_stem, chunk_paths in groups.items():
        # Sort by file size descending so the largest chunks get the lowest numbers
        # (keeps the natural reading order roughly intact).
        chunk_paths.sort(key=lambda p: p.stat().st_size, reverse=True)

        for i, old_path in enumerate(chunk_paths):
            new_name = f"{original_stem}_chunk-{i + 1}.pdf"
            new_path = old_path.parent / new_name

            # Avoid name collisions: if new_path already exists (from a previous
            # flatten or a non-chunk file), append a suffix.
            if new_path.exists() and new_path != old_path:
                new_path = old_path.parent / f"{original_stem}_chunk-{i + 1}_renamed.pdf"

            if new_path != old_path:
                old_path.rename(new_path)
                renamed.append((old_path, new_path))

    if renamed:
        print(f"\n  \U0001f4cb Flattened {len(renamed)} chunk name(s) to clean sequential scheme:")
        for old_path, new_path in renamed:
            old_rel = old_path.name
            new_rel = new_path.relative_to(compressed_root)
            print(f"     {old_rel}  \u2192  {new_rel}")


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


def run_tender_pipeline(
    source_folder_path: str,
    target_dpi=200,
    jpeg_quality=80,
    max_mb=50.0,
    output_folder: str | None = None,
    pdf_only: bool = False,
    silent: bool = False,
    no_chunk: bool = False,
    skip_copy: bool = False,
    quiet: bool = False,
    skip_compression: bool = False,
):
    source_root = Path(source_folder_path).resolve()

    if not source_root.exists() or not source_root.is_dir():
        print(f"Error: Source directory '{source_root}' does not exist.")
        sys.exit(1)

    converted_root = source_root.parent / f"{source_root.name} all-pdfs"
    compressed_root = resolve_output_root(source_root, output_folder, "compressed")

    # Safety check: ensure the output path is usable as a directory.
    # If it exists as a file (e.g. leftover from a failed run), remove it.
    if compressed_root.exists() and not compressed_root.is_dir():
        print(f"  \u26a0\ufe0f  Output path '{compressed_root}' exists as a file, not a directory. Removing it.")
        compressed_root.unlink()
    # Create the output directory. On WSL/Docker shared mounts, mkdir can
    # raise FileExistsError for a path that os.path.exists says doesn't exist
    # (stale filesystem cache). Work around this by creating a temp dir and
    # renaming it into place.
    try:
        compressed_root.mkdir(parents=True, exist_ok=True)
    except FileExistsError:
        if compressed_root.is_dir():
            pass  # Directory exists, that's fine.
        else:
            import tempfile
            tmp = compressed_root.parent / f"{compressed_root.name}.tmp_{os.getpid()}"
            tmp.mkdir(parents=True, exist_ok=True)
            tmp.rename(compressed_root)

    print("==================================================================")
    print(f"\U0001f680 STARTING TENDER DOCUMENT PIPELINE FOR: {source_root.name}")
    print("==================================================================")

    if pdf_only:
        print("\n--- STEP 1: SKIPPED (--pdf-only: compressing existing PDFs directly) ---")
        # Use the source folder directly as the pool of PDFs to compress
        converted_root = source_root
    else:
        print("\n--- STEP 1: CONVERTING WORD DOCS (.doc/.docx) TO PDF ---")
        convert_docx_step(source_root, converted_root)

        raw_pdfs = list(source_root.rglob("*.pdf"))
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
    )

    print("\n--- STEP 3: VALIDATING FINAL FILE SIZES ---")
    # Collect the output PDF list once and reuse it for validation + count check
    # (avoids re-walking the output tree two extra times).
    output_pdfs = [f for f in compressed_root.rglob("*.pdf") if not f.name.startswith("~$")]
    if skip_copy and not output_pdfs:
        # No files were copied to the output folder (all under limit, skip-copy on).
        # Validate the source files directly instead.
        print("  \u2139\ufe0f --skip-copy: no files in output folder. Validating source files directly.")
        source_pdfs = [f for f in converted_root.rglob("*.pdf") if not f.name.startswith("~$")]
        passed, validate_stats = validate_step(converted_root, max_mb=max_mb, pdf_files=source_pdfs, quiet=quiet)
    else:
        passed, validate_stats = validate_step(compressed_root, max_mb=max_mb, pdf_files=output_pdfs, quiet=quiet)

    # --- STEP 3b: PAGE-COUNT CHUNKING ---
    # If files are still over the limit after compression, offer to chunk them.
    # --silent auto-proceeds; otherwise the user is prompted interactively.
    # --no-chunk disables chunking entirely.
    chunk_stats = None
    if not passed and not no_chunk and validate_stats["overlimit_files"]:
        overlimit = validate_stats["overlimit_files"]
        proceed = silent  # auto-proceed in silent mode

        if not silent:
            print(f"\n  {len(overlimit)} file(s) are over the {max_mb} MB limit.")
            print("  Chunking can split them into smaller PDFs using page-count splitting.")
            try:
                answer = input("\n  Proceed with chunking? [y/N] ").strip().lower()
                proceed = answer in ("y", "yes")
            except (EOFError, KeyboardInterrupt):
                proceed = False

        if proceed:
            chunk_stats = chunk_step(
                overlimit, compressed_root, max_mb,
                source_root=source_root if skip_copy else None,
            )

            # Re-validate after chunking.
            print("\n--- STEP 3b: RE-VALIDATING AFTER CHUNKING ---")
            output_pdfs = [f for f in compressed_root.rglob("*.pdf") if not f.name.startswith("~$")]
            passed, validate_stats = validate_step(compressed_root, max_mb=max_mb, pdf_files=output_pdfs, quiet=quiet)
        else:
            print("\n  \u23ed\ufe0f Chunking skipped.")

    print_summary(compress_stats, validate_stats, max_mb, chunk_stats=chunk_stats)

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

    print()
    if passed and count_ok:
        print("\u2705 PIPELINE COMPLETED SUCCESSFULLY! Documents ready for submission.")
        print(f"\U0001f4c1 Final files location: {compressed_root}")
    else:
        if not passed:
            print("\u274c PIPELINE COMPLETED WITH WARNINGS: Some files exceed the limit.")
        if not count_ok:
            print("\u274c PIPELINE COMPLETED WITH WARNINGS: File count mismatch (see above).")
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
    parser.add_argument("--dpi", type=int, default=200, help="Target DPI for image downsampling")
    parser.add_argument("-q", "--quality", type=int, default=80, help="JPEG quality (1-100)")
    parser.add_argument("--max-mb", type=float, default=50.0, help="Max allowed file size in MB")
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
        max_mb=args.max_mb,
        output_folder=args.output,
        pdf_only=args.pdf_only,
        silent=args.silent,
        no_chunk=args.no_chunk,
        skip_copy=args.skip_copy,
        quiet=args.quiet,
        skip_compression=args.skip_compression,
    )
