# -*- coding: utf-8 -*-
"""Unit + integration tests for AncientBooks pipeline."""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from ancientbook.config import PipelineConfig
from ancientbook.export import render_markdown
from ancientbook.ingest import find_spread_split_column, leaf_name, safe_book_name, split_spread
from ancientbook.layout import build_layout, detect_columns, detect_orientation
from ancientbook.manifest import Manifest, sha256_file
from ancientbook.models import BBox, BlockType, ReadingDirection, TextBlock
from ancientbook.pipeline import run_ingest, run_ocr
from ancientbook.review import generate_review_queue, priority_label
from ancientbook.structure import classify_and_order, reconstruct_reading_order


def _make_blocks_vertical(texts_by_column):
    """Helper: create TextBlock list for vertical columns.
    texts_by_column: list of columns; each column is list of characters from top to bottom.
    """
    blocks = []
    col_x = 1000
    col_width = 50
    char_height = 80
    for col in texts_by_column:
        y = 100
        for ch in col:
            bbox = BBox(col_x, y, col_x + col_width, y + char_height)
            blocks.append(TextBlock(text=ch, bbox=bbox, score=0.98))
            y += char_height + 5
        col_x -= col_width + 40
    return blocks


def test_pdf_split_spread(tmp_project: PipelineConfig):
    img = Image.new("RGB", (1800, 1200), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    # left page text
    draw.rectangle([100, 100, 400, 1000], fill=(0, 0, 0))
    # right page text
    draw.rectangle([1300, 100, 1600, 1000], fill=(0, 0, 0))
    split_x = img.width // 2
    right, left = split_spread(img, split_x)
    assert right.width == 900
    assert left.width == 900


def test_page_hash(tmp_project: PipelineConfig):
    p1 = tmp_project.project_root / "test1.txt"
    p2 = tmp_project.project_root / "test2.txt"
    p1.write_text("hello")
    p2.write_text("world")
    assert sha256_file(p1) == sha256_file(p1)
    assert sha256_file(p1) != sha256_file(p2)


def test_vertical_layout(tmp_project: PipelineConfig):
    # three vertical columns, right to left reading
    cols = [
        ["天", "地", "玄", "黃"],
        ["宇", "宙", "洪", "荒"],
        ["日", "月", "盈", "昃"],
    ]
    blocks = _make_blocks_vertical(cols)
    orientation = detect_orientation(blocks)
    assert orientation.value == "vertical"
    col_count, centers = detect_columns(blocks, 1200, 1200)
    assert col_count == 3
    # 3 distinct column centers; leftmost < rightmost
    assert len(set(centers)) == 3
    assert centers[0] < centers[-1]


def test_reading_order(tmp_project: PipelineConfig):
    cols = [
        ["一", "二", "三"],
        ["四", "五", "六"],
    ]
    blocks = _make_blocks_vertical(cols)
    from ancientbook.layout import build_layout
    layout = build_layout(blocks, 1200, 1200, tmp_project)
    assert layout.reading_direction == ReadingDirection.RIGHT_TO_LEFT
    lines = reconstruct_reading_order(blocks, layout, tmp_project)
    text = "".join(l.text() for l in lines)
    # right column first, top-to-bottom, then left column
    assert text.startswith("一二三")
    assert "四五六" in text


def test_block_classification(tmp_project: PipelineConfig):
    blocks = []
    # main text tall boxes
    for i, ch in enumerate(["天", "地", "玄", "黃"]):
        blocks.append(TextBlock(text=ch, bbox=BBox(500, 100 + i * 80, 560, 170 + i * 80), score=0.97))
    # commentary small boxes near top
    for i, ch in enumerate(["註", "一"]):
        blocks.append(TextBlock(text=ch, bbox=BBox(300, 100 + i * 30, 330, 125 + i * 30), score=0.85))
    layout = build_layout(blocks, 800, 600, tmp_project)
    transcription = classify_and_order(blocks, layout, tmp_project)
    main = [l for l in transcription.lines if l.line_type == BlockType.MAIN_TEXT]
    comm = [l for l in transcription.lines if l.line_type == BlockType.COMMENTARY]
    assert len(main) > 0
    assert len(comm) > 0


def test_main_text_vs_commentary_separation(tmp_project: PipelineConfig):
    blocks = []
    main_chars = ["天", "地"]
    for i, ch in enumerate(main_chars):
        blocks.append(TextBlock(text=ch, bbox=BBox(400, 100 + i * 80, 460, 170 + i * 80), score=0.97))
    comm_chars = ["註", "曰"]
    for i, ch in enumerate(comm_chars):
        blocks.append(TextBlock(text=ch, bbox=BBox(200, 100 + i * 30, 230, 125 + i * 30), score=0.80))
    layout = build_layout(blocks, 800, 600, tmp_project)
    transcription = classify_and_order(blocks, layout, tmp_project)
    md = render_markdown(transcription, Path("img.png"), Path("book.pdf"))
    assert "### 正文" in md
    assert "### 注 / 批" in md
    # commentary text "註曰" should appear in the 注/批 section, not the 正文 section
    main_section = md.split("### 注 / 批")[0]
    assert "註" not in main_section
    assert "曰" not in main_section


def test_provenance(tmp_project: PipelineConfig):
    blocks = [TextBlock(text="道", bbox=BBox(0, 0, 10, 10), score=0.99)]
    layout = build_layout(blocks, 100, 100, tmp_project)
    transcription = classify_and_order(blocks, layout, tmp_project)
    transcription.book = "測試書"
    transcription.volume = "卷一"
    transcription.leaf = 23
    transcription.pdf_page = 25
    transcription.side = "R"
    transcription.image_file = Path("/tmp/0025.png")
    transcription.ocr_engine = "RapidOCR(high)"
    transcription.ocr_confidence = 0.96
    transcription.review_status = "auto"
    md = render_markdown(transcription, Path("0025.png"), Path("book.pdf"))
    assert "type: ancient_book_transcription" in md
    assert "book: 測試書" in md
    assert "leaf: 23" in md
    assert "pdf_page: 25" in md
    assert "side: R" in md
    assert "ocr_engine: RapidOCR(high)" in md
    assert "review_status: auto" in md
    assert "PDF: `book.pdf`" in md


def test_markdown_export(tmp_project: PipelineConfig):
    blocks = [TextBlock(text="可", bbox=BBox(0, 0, 10, 10), score=0.99)]
    layout = build_layout(blocks, 100, 100, tmp_project)
    transcription = classify_and_order(blocks, layout, tmp_project)
    transcription.book = "測試書"
    transcription.volume = "卷一"
    transcription.leaf = 1
    transcription.pdf_page = 1
    transcription.side = "whole"
    transcription.image_file = tmp_project.project_root / "img.png"
    transcription.ocr_engine = "test"
    transcription.ocr_confidence = 0.99
    transcription.review_status = "auto"
    from ancientbook.pipeline import run_export
    from ancientbook.manifest import get_manifest
    manifest = get_manifest(tmp_project)
    md_path = run_export(transcription, tmp_project, manifest)
    assert md_path.exists()
    assert "ancient_book_transcription" in md_path.read_text(encoding="utf-8")


def test_review_queue(tmp_project: PipelineConfig):
    from ancientbook.manifest import LeafRecord, get_manifest
    manifest = get_manifest(tmp_project)
    for i, conf in enumerate([0.99, 0.88, 0.75]):
        rec = LeafRecord(
            book="書", volume="卷一", leaf=i + 1, pdf_page=i + 1,
            side="R", pdf_path="/a.pdf", image_file="/a.png", image_hash="x",
            ocr_engine="t", ocr_version="v1", pipeline_version="0.1.0",
            confidence=conf,
        )
        manifest.upsert(rec)
    path = generate_review_queue(manifest, tmp_project)
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert "OCR Review Queue" in text
    assert "0.750" in text


def test_idempotent_rerun(tmp_project: PipelineConfig):
    # manifest.is_up_to_date gates reruns
    from ancientbook.manifest import LeafRecord, get_manifest
    manifest = get_manifest(tmp_project)
    rec = LeafRecord(
        book="book", volume="卷一", leaf=1, pdf_page=1, side="R",
        pdf_path="/book.pdf", image_file="/img.png", image_hash="abc",
        ocr_engine="rapidocr", ocr_version="rapidocr-high", pipeline_version="0.1.0",
    )
    manifest.upsert(rec)
    assert manifest.is_up_to_date("book", 1, "R", "abc", "rapidocr-high", "0.1.0")
    # different image hash => rerun needed
    assert not manifest.is_up_to_date("book", 1, "R", "different", "rapidocr-high", "0.1.0")
    # different ocr version => rerun
    assert not manifest.is_up_to_date("book", 1, "R", "abc", "rapidocr-mobile", "0.1.0")


def test_safe_book_name():
    assert safe_book_name("《标注传习录》卷一") == "标注传习录卷一"


def test_priority_labels(tmp_project: PipelineConfig):
    assert priority_label(0.75, tmp_project) == "high"
    assert priority_label(0.88, tmp_project) == "review"
    assert priority_label(0.97, tmp_project) == "low"
