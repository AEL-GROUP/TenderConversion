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
        # Create an RGB image so compression can exercise its color path.
        img = Image.new("RGB", (img_size, img_size), color=(255, 100, 50))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        page.insert_image(page.rect, stream=buf.getvalue())
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(path, garbage=3, deflate=True)
    doc.close()
    return path


def make_pdf_with_color_detail(path: Path, img_size: int = 1200):
    """Create native text, vector content, and a high-DPI color image."""
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (img_size, img_size), color=(220, 30, 30))
    draw = ImageDraw.Draw(image)
    draw.rectangle(
        (img_size // 2, 0, img_size, img_size),
        fill=(20, 80, 220),
    )
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")

    doc = pymupdf.open()
    page = doc.new_page(width=300, height=300)
    page.insert_text((20, 25), "COLOR SPECIFICATION")
    page.draw_rect(pymupdf.Rect(15, 35, 135, 155), color=(0, 0, 0), width=2)
    page.insert_image(
        pymupdf.Rect(20, 40, 120, 140),
        stream=buffer.getvalue(),
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(path, garbage=3, deflate=True)
    doc.close()
    return path


def make_pdf_with_unique_images(path: Path, num_pages: int = 6, img_size: int = 500):
    """Create pages with distinct text and incompressible images."""
    from PIL import Image

    doc = pymupdf.open()
    for page_number in range(1, num_pages + 1):
        page = doc.new_page(width=300, height=300)
        page.insert_text((20, 25), f"PAGE-{page_number}")
        image = Image.frombytes("L", (img_size, img_size), os.urandom(img_size ** 2))
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=85)
        page.insert_image(pymupdf.Rect(20, 40, 280, 280), stream=buffer.getvalue())
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(path, garbage=3, deflate=True)
    doc.close()
    return path


# ------------------------------------------------------------------------------
# Tests: exact page-range serialization
# ------------------------------------------------------------------------------
class TestSerializePdfRange:
    def test_measured_bytes_are_the_written_bytes(self, tmp_path):
        pdf_path = make_pdf(tmp_path / "doc.pdf", num_pages=4)
        doc = pymupdf.open(pdf_path)
        serialized = pipeline._serialize_pdf_range(doc, 1, 3)
        doc.close()

        output_path = tmp_path / "range.pdf"
        output_path.write_bytes(serialized)

        assert output_path.stat().st_size == len(serialized)
        range_doc = pymupdf.open(output_path)
        assert len(range_doc) == 2
        range_doc.close()


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


class TestStagedRunPublication:
    def test_repeated_run_replaces_stale_output_tree(self, tmp_path):
        source = tmp_path / "source"
        output = tmp_path / "final"
        source.mkdir()
        make_pdf(source / "document.pdf", num_pages=1)

        pipeline.run_tender_pipeline(
            str(source),
            output_folder=str(output),
            pdf_only=True,
            silent=True,
        )
        stale_file = output / "stale.txt"
        stale_file.write_text("old run", encoding="utf-8")

        pipeline.run_tender_pipeline(
            str(source),
            output_folder=str(output),
            pdf_only=True,
            silent=True,
        )

        assert (output / "document.pdf").exists()
        assert not stale_file.exists()
        assert (source / "document.pdf").exists()

    def test_compression_failure_prevents_publication(
        self, tmp_path, monkeypatch
    ):
        source = tmp_path / "source"
        output = tmp_path / "final"
        source.mkdir()
        source_pdf = make_pdf(source / "document.pdf", num_pages=1)

        def failed_compression(_source, compressed_root, **_kwargs):
            compressed_root.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_pdf, compressed_root / source_pdf.name)
            size = source_pdf.stat().st_size
            return {
                "count": 1,
                "failed": 1,
                "orig_bytes": size,
                "new_bytes": size,
                "skipped": 0,
            }

        monkeypatch.setattr(pipeline, "compress_step", failed_compression)

        with pytest.raises(SystemExit):
            pipeline.run_tender_pipeline(
                str(source),
                output_folder=str(output),
                pdf_only=True,
                silent=True,
                skip_copy=True,
            )

        assert not output.exists()


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

    def test_page_limit_is_enforced_independently_of_size(self, tmp_path):
        root = tmp_path / "output"
        root.mkdir()
        make_pdf(root / "many-pages.pdf", num_pages=3)

        passed, stats = pipeline.validate_step(
            root,
            max_mb=50.0,
            max_pages=2,
        )

        assert passed is False
        assert stats["page_overlimit"] == 1
        assert stats["size_overlimit"] == 0
        assert stats["overlimit_files"][0][2] == 3

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

    def test_parallel_workers_compress_independent_pdfs(self, tmp_path):
        src = tmp_path / "src"
        out = tmp_path / "out"
        make_pdf_with_image(src / "first" / "a.pdf", num_pages=1, img_size=500)
        make_pdf_with_image(src / "second" / "b.pdf", num_pages=1, img_size=500)

        stats = pipeline.compress_step(
            src,
            out,
            max_mb=0.0,
            target_dpi=72,
            jpeg_quality=30,
            workers=2,
        )

        assert stats["count"] == 2
        assert stats["failed"] == 0
        assert (out / "first" / "a.pdf").exists()
        assert (out / "second" / "b.pdf").exists()

    def test_parallel_worker_failure_does_not_block_valid_pdf(self, tmp_path):
        src = tmp_path / "src"
        out = tmp_path / "out"
        src.mkdir()
        (src / "broken.pdf").write_bytes(b"not a PDF")
        make_pdf_with_image(src / "valid.pdf", num_pages=1, img_size=500)

        stats = pipeline.compress_step(
            src,
            out,
            max_mb=0.0,
            target_dpi=72,
            jpeg_quality=30,
            workers=2,
        )

        assert stats["count"] == 2
        assert stats["failed"] == 1
        assert not (out / "broken.pdf").exists()
        assert (out / "valid.pdf").exists()

    def test_invalid_worker_count_is_rejected(self, tmp_path):
        src = tmp_path / "src"
        out = tmp_path / "out"
        src.mkdir()

        with pytest.raises(ValueError, match="workers"):
            pipeline.compress_step(src, out, workers=0)

    def test_skip_copy_under_limit(self, tmp_path):
        src = tmp_path / "src"
        out = tmp_path / "out"
        src.mkdir()
        make_pdf(src / "small.pdf", num_pages=1)
        stats = pipeline.compress_step(src, out, max_mb=50.0, skip_copy=True)
        assert stats["skipped"] == 1
        # File should NOT be in the output folder
        assert not (out / "small.pdf").exists()

    def test_skip_copy_stages_page_oversized_pdf_for_chunking(self, tmp_path):
        src = tmp_path / "src"
        out = tmp_path / "out"
        src.mkdir()
        make_pdf(src / "many-pages.pdf", num_pages=3)

        stats = pipeline.compress_step(
            src,
            out,
            max_mb=50.0,
            max_pages=2,
            skip_copy=True,
        )

        assert stats["skipped"] == 1
        assert (out / "many-pages.pdf").exists()

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

    def test_rewrite_preserves_color_text_and_geometry(self, tmp_path):
        source = make_pdf_with_color_detail(tmp_path / "source.pdf")
        output = tmp_path / "output.pdf"

        source_doc = pymupdf.open(source)
        source_page = source_doc[0]
        source_text = source_page.get_text()
        source_geometry = (
            tuple(source_page.mediabox),
            tuple(source_page.cropbox),
            source_page.rotation,
        )
        source_doc.close()

        pipeline.compress_single_pdf(
            source,
            output,
            target_dpi=200,
            jpeg_quality=80,
            max_bytes=0,
        )

        output_doc = pymupdf.open(output)
        output_page = output_doc[0]
        assert output_page.get_text() == source_text
        assert (
            tuple(output_page.mediabox),
            tuple(output_page.cropbox),
            output_page.rotation,
        ) == source_geometry

        image_info = output_page.get_image_info()
        assert image_info[0]["width"] < 1200
        pixmap = output_page.get_pixmap(dpi=72, colorspace=pymupdf.csRGB)
        red = pixmap.pixel(45, 80)
        blue = pixmap.pixel(95, 80)
        assert red[0] > red[2] + 50
        assert blue[2] > blue[0] + 50
        output_doc.close()

    @pytest.mark.parametrize(
        ("kwargs", "message"),
        [
            ({"target_dpi": 0}, "target_dpi"),
            ({"jpeg_quality": 101}, "jpeg_quality"),
            ({"target_dpi": 200, "dpi_threshold": 200}, "dpi_threshold"),
        ],
    )
    def test_invalid_compression_settings_are_rejected(
        self, tmp_path, kwargs, message
    ):
        source = make_pdf(tmp_path / "source.pdf", num_pages=1)
        with pytest.raises(ValueError, match=message):
            pipeline.compress_single_pdf(source, tmp_path / "output.pdf", **kwargs)

    def test_failed_candidate_does_not_replace_existing_output(self, tmp_path, monkeypatch):
        source = make_pdf_with_color_detail(tmp_path / "source.pdf")
        output = tmp_path / "output.pdf"
        output.write_bytes(b"previous successful output")

        def fail_save(*args, **kwargs):
            raise RuntimeError("injected save failure")

        monkeypatch.setattr(pipeline, "_save_compressed_document", fail_save)
        with pytest.raises(RuntimeError, match="injected save failure"):
            pipeline.compress_single_pdf(source, output, max_bytes=0)

        assert output.read_bytes() == b"previous successful output"


# ------------------------------------------------------------------------------
# Tests: chunk_step (integration)
# ------------------------------------------------------------------------------
class TestChunkStep:
    def test_chunks_to_page_limit_even_when_bytes_are_under_limit(self, tmp_path):
        out = tmp_path / "out"
        out.mkdir()
        pdf_path = make_pdf(out / "many-pages.pdf", num_pages=5)

        cstats = pipeline.chunk_step(
            [(pdf_path.name, pdf_path.stat().st_size / (1024 * 1024), 5)],
            out,
            max_mb=50.0,
            max_pages=2,
        )

        chunks = sorted(out.glob("many-pages_chunk-*.pdf"))
        assert cstats["produced"] == 3
        page_counts = []
        for chunk in chunks:
            with pymupdf.open(chunk) as chunk_doc:
                page_counts.append(chunk_doc.page_count)
        assert page_counts == [2, 2, 1]

    def test_chunks_once_under_exact_limit_in_page_order(self, tmp_path):
        out = tmp_path / "out"
        out.mkdir()
        pdf_path = make_pdf_with_unique_images(out / "big.pdf")
        stale_chunk = out / "big_chunk-99.pdf"
        stale_chunk.write_bytes(b"stale")

        doc = pymupdf.open(pdf_path)
        two_page_bytes = len(pipeline._serialize_pdf_range(doc, 0, 2))
        doc.close()
        max_bytes = two_page_bytes + 1
        max_mb = max_bytes / (1024 * 1024)

        cstats = pipeline.chunk_step(
            [(pdf_path.name, pdf_path.stat().st_size / (1024 * 1024))],
            out,
            max_mb=max_mb,
        )
        assert cstats["chunked"] == 1
        assert cstats["produced"] >= 2
        assert not (out / "big.pdf").exists()
        assert not stale_chunk.exists()

        chunks = sorted(
            out.glob("big_chunk-*.pdf"),
            key=lambda path: int(path.stem.rsplit("-", 1)[1]),
        )
        assert len(chunks) == cstats["produced"]
        assert all(chunk.stat().st_size < max_bytes for chunk in chunks)

        page_text = []
        for chunk in chunks:
            chunk_doc = pymupdf.open(chunk)
            page_text.extend(
                page.get_text().strip().splitlines()[0]
                for page in chunk_doc
            )
            chunk_doc.close()
        assert page_text == [f"PAGE-{number}" for number in range(1, 7)]

    def test_single_oversized_page_is_rescued(self, tmp_path):
        out = tmp_path / "out"
        out.mkdir()
        pdf_path = make_pdf_with_unique_images(
            out / "single.pdf",
            num_pages=1,
            img_size=1000,
        )
        max_mb = 0.08

        cstats = pipeline.chunk_step(
            [(pdf_path.name, pdf_path.stat().st_size / (1024 * 1024))],
            out,
            max_mb=max_mb,
        )

        rescued_chunk = out / "single_chunk-1.pdf"
        assert cstats["chunked"] == 1
        assert cstats["rescued_pages"] == 1
        assert rescued_chunk.stat().st_size < max_mb * 1024 * 1024
        assert not pdf_path.exists()

    def test_failed_rescue_preserves_original_and_stale_chunks(self, tmp_path):
        out = tmp_path / "out"
        out.mkdir()
        pdf_path = make_pdf_with_unique_images(out / "single.pdf", num_pages=1)
        original_bytes = pdf_path.read_bytes()
        stale_chunk = out / "single_chunk-1.pdf"
        stale_chunk.write_bytes(b"existing chunk")

        cstats = pipeline.chunk_step(
            [(pdf_path.name, pdf_path.stat().st_size / (1024 * 1024))],
            out,
            max_mb=0.0001,
        )

        assert cstats["failed"] == 1
        assert cstats["still_over"] == 1
        assert cstats["chunked"] == 0
        assert pdf_path.read_bytes() == original_bytes
        assert stale_chunk.read_bytes() == b"existing chunk"

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

    def test_page_limit_triggers_chunking_without_size_failure(self, tmp_path):
        src = tmp_path / "tender"
        out = tmp_path / "final"
        src.mkdir()
        make_pdf(src / "many-pages.pdf", num_pages=5)

        pipeline.run_tender_pipeline(
            source_folder_path=str(src),
            output_folder=str(out),
            pdf_only=True,
            skip_compression=True,
            silent=True,
            quiet=True,
            max_mb=50.0,
            max_pages=2,
        )

        chunks = sorted(out.glob("many-pages_chunk-*.pdf"))
        assert len(chunks) == 3
        for chunk in chunks:
            with pymupdf.open(chunk) as doc:
                assert doc.page_count <= 2


if __name__ == "__main__":
    # Allow running directly without pytest
    pytest.main([__file__, "-v", "--tb=short"])
