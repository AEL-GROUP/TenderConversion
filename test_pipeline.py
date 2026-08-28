"""
test_pipeline.py
================
Test suite for pdf_tender_pipeline.py and filter_extensions.py.

Covers the pure-logic functions (no LibreOffice, no real PDFs needed) plus
integration tests that create small in-memory PDFs via PyMuPDF.

Run with:
    python -m pytest test_pipeline.py -v
or:
    python test_pipeline.py
"""

import io
import os
import shutil
import sys
from pathlib import Path

import pymupdf
import pytest

# Make the local modules importable
sys.path.insert(0, str(Path(__file__).parent))

import pdf_tender_pipeline as pipeline
import filter_extensions


# ------------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------------
def make_pdf(path: Path, num_pages: int = 3, page_size: int = 100):
    """Create a minimal PDF with the given number of pages."""
    doc = pymupdf.open()
    for _ in range(num_pages):
        page = doc.new_page(width=page_size, height=page_size)
        page.insert_text((10, 20), "test page")
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(path, garbage=3, deflate=True)
    doc.close()
    return path


def make_pdf_with_image(path: Path, num_pages: int = 2, img_size: int = 500):
    """Create a PDF with embedded images so compression has something to do."""
    from PIL import Image

    doc = pymupdf.open()
    for i in range(num_pages):
        page = doc.new_page(width=612, height=792)
        # Create a colour image (RGB) so compression can convert to grayscale
        img = Image.new("RGB", (img_size, img_size), color=(255, 100, 50))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        page.insert_image(page.rect, stream=buf.getvalue())
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(path, garbage=3, deflate=True)
    doc.close()
    return path


# ------------------------------------------------------------------------------
# Tests: _fallback_split_points
# ------------------------------------------------------------------------------
class TestFallbackSplitPoints:
    def test_single_page_returns_zero(self):
        assert pipeline._fallback_split_points(1, 100.0, 50.0) == [0]

    def test_zero_pages_returns_zero(self):
        assert pipeline._fallback_split_points(0, 100.0, 50.0) == [0]

    def test_two_pages_over_limit(self):
        points = pipeline._fallback_split_points(2, 100.0, 50.0)
        assert points[0] == 0
        assert len(points) >= 2

    def test_many_pages(self):
        points = pipeline._fallback_split_points(60, 126.0, 45.0)
        assert points[0] == 0
        # Should produce at least 3 chunks for 126 MB / 45 MB target
        assert len(points) >= 3
        # Last split point should be < 60
        assert points[-1] < 60

    def test_always_starts_with_zero(self):
        points = pipeline._fallback_split_points(10, 200.0, 50.0)
        assert points[0] == 0


# ------------------------------------------------------------------------------
# Tests: resolve_output_root
# ------------------------------------------------------------------------------
class TestResolveOutputRoot:
    def test_default_suffix(self, tmp_path):
        source = tmp_path / "MyTender"
        source.mkdir()
        result = pipeline.resolve_output_root(source, None, "compressed")
        assert result == tmp_path / "MyTender compressed"

    def test_bare_name(self, tmp_path):
        source = tmp_path / "MyTender"
        source.mkdir()
        result = pipeline.resolve_output_root(source, "FinalSubmission", "compressed")
        assert result == tmp_path / "FinalSubmission"

    def test_absolute_path(self, tmp_path):
        source = tmp_path / "MyTender"
        source.mkdir()
        out = tmp_path / "Output" / "Final"
        result = pipeline.resolve_output_root(source, str(out), "compressed")
        assert result == out.resolve()

    def test_relative_path_with_separator(self, tmp_path, monkeypatch):
        source = tmp_path / "MyTender"
        source.mkdir()
        # resolve_output_root resolves relative paths against CWD, so
        # change CWD to the source's parent to make the test deterministic.
        monkeypatch.chdir(source.parent)
        result = pipeline.resolve_output_root(source, "../Output", "compressed")
        assert result == (source.parent / ".." / "Output").resolve()


# ------------------------------------------------------------------------------
# Tests: validate_step
# ------------------------------------------------------------------------------
class TestValidateStep:
    def test_all_pass(self, tmp_path):
        root = tmp_path / "output"
        root.mkdir()
        make_pdf(root / "small.pdf", num_pages=1)
        passed, stats = pipeline.validate_step(root, max_mb=50.0)
        assert passed is True
        assert stats["passed"] == 1
        assert stats["failed"] == 0

    def test_over_limit(self, tmp_path):
        root = tmp_path / "output"
        root.mkdir()
        make_pdf(root / "small.pdf", num_pages=1)
        passed, stats = pipeline.validate_step(root, max_mb=0.0)
        assert passed is False
        assert stats["failed"] == 1
        assert len(stats["overlimit_files"]) == 1

    def test_no_pdfs(self, tmp_path):
        root = tmp_path / "empty"
        root.mkdir()
        passed, stats = pipeline.validate_step(root, max_mb=50.0)
        assert passed is True
        assert stats["count"] == 0

    def test_quiet_mode(self, tmp_path, capsys):
        root = tmp_path / "output"
        root.mkdir()
        make_pdf(root / "a.pdf", num_pages=1)
        make_pdf(root / "b.pdf", num_pages=1)
        passed, stats = pipeline.validate_step(root, max_mb=50.0, quiet=True)
        captured = capsys.readouterr()
        # In quiet mode, per-file PASS lines should not appear
        assert "[PASS]" not in captured.out
        assert stats["passed"] == 2


# ------------------------------------------------------------------------------
# Tests: compress_step
# ------------------------------------------------------------------------------
class TestCompressStep:
    def test_under_limit_copied_as_is(self, tmp_path):
        src = tmp_path / "src"
        out = tmp_path / "out"
        src.mkdir()
        make_pdf(src / "small.pdf", num_pages=1)
        stats = pipeline.compress_step(src, out, max_mb=50.0)
        assert stats["count"] == 1
        assert stats["skipped"] == 1
        assert (out / "small.pdf").exists()

    def test_over_limit_compressed(self, tmp_path):
        src = tmp_path / "src"
        out = tmp_path / "out"
        src.mkdir()
        make_pdf_with_image(src / "big.pdf", num_pages=3, img_size=800)
        stats = pipeline.compress_step(src, out, max_mb=0.0, target_dpi=72, jpeg_quality=30)
        assert stats["count"] == 1
        assert stats["skipped"] == 0
        assert (out / "big.pdf").exists()

    def test_skip_copy_under_limit(self, tmp_path):
        src = tmp_path / "src"
        out = tmp_path / "out"
        src.mkdir()
        make_pdf(src / "small.pdf", num_pages=1)
        stats = pipeline.compress_step(src, out, max_mb=50.0, skip_copy=True)
        assert stats["skipped"] == 1
        # File should NOT be in the output folder
        assert not (out / "small.pdf").exists()

    def test_skip_compression_copies_all(self, tmp_path):
        src = tmp_path / "src"
        out = tmp_path / "out"
        src.mkdir()
        make_pdf(src / "a.pdf", num_pages=1)
        make_pdf_with_image(src / "b.pdf", num_pages=2, img_size=400)
        stats = pipeline.compress_step(src, out, max_mb=50.0, skip_compression=True)
        assert stats["count"] == 2
        assert stats["skipped"] == 2
        assert (out / "a.pdf").exists()
        assert (out / "b.pdf").exists()

    def test_skip_compression_with_skip_copy(self, tmp_path):
        src = tmp_path / "src"
        out = tmp_path / "out"
        src.mkdir()
        make_pdf(src / "a.pdf", num_pages=1)
        stats = pipeline.compress_step(src, out, max_mb=50.0, skip_compression=True, skip_copy=True)
        assert stats["skipped"] == 1
        assert not (out / "a.pdf").exists()

    def test_no_pdfs(self, tmp_path):
        src = tmp_path / "src"
        out = tmp_path / "out"
        src.mkdir()
        stats = pipeline.compress_step(src, out, max_mb=50.0)
        assert stats["count"] == 0


# ------------------------------------------------------------------------------
# Tests: _split_pdf_at_pages
# ------------------------------------------------------------------------------
class TestSplitPdfAtPages:
    def test_split_into_two(self, tmp_path):
        src = tmp_path / "src"
        out = tmp_path / "out"
        src.mkdir()
        pdf = make_pdf(src / "doc.pdf", num_pages=4)
        result = pipeline._split_pdf_at_pages(pdf, out, [0, 2], "doc")
        assert len(result) == 2
        assert result[0].name == "doc_chunk-1.pdf"
        assert result[1].name == "doc_chunk-2.pdf"
        # Verify page counts
        d1 = pymupdf.open(result[0])
        assert len(d1) == 2
        d1.close()
        d2 = pymupdf.open(result[1])
        assert len(d2) == 2
        d2.close()

    def test_split_uneven(self, tmp_path):
        src = tmp_path / "src"
        out = tmp_path / "out"
        src.mkdir()
        pdf = make_pdf(src / "doc.pdf", num_pages=5)
        result = pipeline._split_pdf_at_pages(pdf, out, [0, 2, 4], "doc")
        assert len(result) == 3
        d1 = pymupdf.open(result[0])
        assert len(d1) == 2
        d1.close()
        d2 = pymupdf.open(result[1])
        assert len(d2) == 2
        d2.close()
        d3 = pymupdf.open(result[2])
        assert len(d3) == 1
        d3.close()


# ------------------------------------------------------------------------------
# Tests: chunk_step (integration)
# ------------------------------------------------------------------------------
class TestChunkStep:
    def test_chunk_over_limit_file(self, tmp_path):
        out = tmp_path / "out"
        out.mkdir()
        # Create a PDF, then validate with max_mb=0 so it's "over limit"
        make_pdf(out / "big.pdf", num_pages=6)
        passed, vstats = pipeline.validate_step(out, max_mb=0.0)
        assert not passed
        cstats = pipeline.chunk_step(vstats["overlimit_files"], out, max_mb=50.0)
        assert cstats["chunked"] == 1
        assert cstats["produced"] >= 2
        # Original should be deleted
        assert not (out / "big.pdf").exists()
        # Chunks should exist
        chunks = list(out.glob("big_chunk-*.pdf"))
        assert len(chunks) >= 2

    def test_chunk_single_page_fails(self, tmp_path):
        out = tmp_path / "out"
        out.mkdir()
        make_pdf(out / "single.pdf", num_pages=1)
        passed, vstats = pipeline.validate_step(out, max_mb=0.0)
        cstats = pipeline.chunk_step(vstats["overlimit_files"], out, max_mb=50.0)
        assert cstats["failed"] == 1
        assert cstats["chunked"] == 0

    def test_no_overlimit_files(self, tmp_path):
        out = tmp_path / "out"
        out.mkdir()
        cstats = pipeline.chunk_step([], out, max_mb=50.0)
        assert cstats["chunked"] == 0
        assert cstats["produced"] == 0


# ------------------------------------------------------------------------------
# Tests: assert_file_count
# ------------------------------------------------------------------------------
class TestAssertFileCount:
    def test_match(self, tmp_path):
        src = tmp_path / "src"
        out = tmp_path / "out"
        src.mkdir()
        out.mkdir()
        make_pdf(src / "a.pdf", num_pages=1)
        make_pdf(out / "a.pdf", num_pages=1)
        ok = pipeline.assert_file_count(src, out, pdf_only=True)
        assert ok is True

    def test_mismatch_missing(self, tmp_path):
        src = tmp_path / "src"
        out = tmp_path / "out"
        src.mkdir()
        out.mkdir()
        make_pdf(src / "a.pdf", num_pages=1)
        make_pdf(src / "b.pdf", num_pages=1)
        make_pdf(out / "a.pdf", num_pages=1)
        ok = pipeline.assert_file_count(src, out, pdf_only=True)
        assert ok is False

    def test_with_chunking(self, tmp_path):
        src = tmp_path / "src"
        out = tmp_path / "out"
        src.mkdir()
        out.mkdir()
        make_pdf(src / "a.pdf", num_pages=1)
        make_pdf(out / "a_chunk-1.pdf", num_pages=1)
        make_pdf(out / "a_chunk-2.pdf", num_pages=1)
        ok = pipeline.assert_file_count(src, out, pdf_only=True, chunked_count=1)
        assert ok is True


# ------------------------------------------------------------------------------
# Tests: filter_extensions.py
# ------------------------------------------------------------------------------
class TestExtractExtensions:
    def test_basic(self):
        paths = [Path("a.pdf"), Path("b.docx"), Path("c.PDF")]
        exts = filter_extensions.extract_extensions(paths)
        assert ".pdf" in exts
        assert ".docx" in exts

    def test_no_extension(self):
        paths = [Path("README"), Path("Makefile")]
        exts = filter_extensions.extract_extensions(paths)
        assert exts == []

    def test_sorted(self):
        paths = [Path("z.pdf"), Path("a.doc"), Path("m.png")]
        exts = filter_extensions.extract_extensions(paths)
        assert exts == sorted(exts)


class TestCopyPreservingStructure:
    def test_with_base_dir(self, tmp_path):
        base = tmp_path / "src"
        base.mkdir()
        sub = base / "sub"
        sub.mkdir()
        f = sub / "file.pdf"
        f.write_text("test")
        dest = tmp_path / "out"
        filter_extensions.copy_preserving_structure(f, dest, base_dir=base)
        assert (dest / "sub" / "file.pdf").exists()

    def test_without_base_dir(self, tmp_path):
        f = tmp_path / "file.pdf"
        f.write_text("test")
        dest = tmp_path / "out"
        filter_extensions.copy_preserving_structure(f, dest, base_dir=None)
        # On Windows, absolute paths like C:\... have parts[0] = 'C:\',
        # so parts[1:] strips the drive root and the file lands at dest / tmp_path.name / file.pdf
        # On Linux, parts[0] = '/', so parts[1:] strips root and file lands at dest / tmp_path.name / file.pdf
        # Check that the file exists somewhere under dest
        found = list(dest.rglob("file.pdf"))
        assert len(found) == 1


# ------------------------------------------------------------------------------
# Integration: full pipeline run with --skip-compression
# ------------------------------------------------------------------------------
class TestPipelineSkipCompression:
    def test_skip_compression_copies_and_validates(self, tmp_path):
        src = tmp_path / "tender"
        out = tmp_path / "final"
        src.mkdir()
        make_pdf(src / "small1.pdf", num_pages=1)
        make_pdf(src / "small2.pdf", num_pages=2)

        pipeline.run_tender_pipeline(
            source_folder_path=str(src),
            output_folder=str(out),
            pdf_only=True,
            skip_compression=True,
            silent=True,
            quiet=True,
        )
        # Both files should be copied as-is
        assert (out / "small1.pdf").exists()
        assert (out / "small2.pdf").exists()

    def test_skip_compression_with_chunking(self, tmp_path):
        src = tmp_path / "tender"
        out = tmp_path / "final"
        src.mkdir()
        # Create a multi-page PDF; with a tiny max_mb it will be over-limit and chunked
        make_pdf(src / "big.pdf", num_pages=6)

        pipeline.run_tender_pipeline(
            source_folder_path=str(src),
            output_folder=str(out),
            pdf_only=True,
            skip_compression=True,
            silent=True,
            quiet=True,
            max_mb=0.001,
        )
        # Original should be gone, chunks should exist
        assert not (out / "big.pdf").exists()
        chunks = list(out.glob("big_chunk-*.pdf"))
        assert len(chunks) >= 2


if __name__ == "__main__":
    # Allow running directly without pytest
    pytest.main([__file__, "-v", "--tb=short"])
