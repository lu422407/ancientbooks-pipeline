# -*- coding: utf-8 -*-
"""Orchestrator: ingest → OCR → structure → export → manifest."""
from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

import yaml
from PIL import Image

from ancientbook.config import PipelineConfig
from ancientbook.export import export_leaf
from ancientbook.ingest import ingest_pdf, safe_book_name, update_manifest_from_leaves
from ancientbook.layout import build_layout
from ancientbook.manifest import LeafRecord, Manifest, get_manifest, sha256_file
from ancientbook.models import BBox, LayoutProfile, Leaf, Orientation, PageTranscription, ReadingDirection, TextBlock
from ancientbook.ocr_adapter import build_ocr_engine
from ancientbook.review import generate_review_queue
from ancientbook.structure import classify_and_order


def run_ingest(pdf_path: Path, book: str, volume: str, config: PipelineConfig,
               limit_pages: int = 0, manifest: Optional[Manifest] = None) -> List[Leaf]:
    leaves = ingest_pdf(pdf_path, book, volume, config, limit_pages)
    if manifest is not None:
        # 同一 PDF 页重新 ingest 后拆页方式可能变化（whole↔R/L），
        # 先清掉这些页的旧记录，避免新旧叶号复用导致导出互相覆盖
        manifest.purge_book_pages(book, {l.pdf_index + 1 for l in leaves})
    engine_label = f"{config.ocr_engine}-{config.ocr_quality}"
    update_manifest_from_leaves(leaves, config, volume=volume,
                                ocr_engine=config.ocr_engine,
                                ocr_version=engine_label,
                                manifest=manifest)
    return leaves


def load_raw_blocks(raw_path: Path) -> List[TextBlock]:
    with open(raw_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    blocks = []
    for b in data.get("blocks", []):
        x0, y0, x1, y1 = b["bbox"]
        blocks.append(TextBlock(
            text=b["text"],
            bbox=BBox(x0, y0, x1, y1),
            score=b.get("score", 0.0),
            polygon=b.get("polygon"),
        ))
    return blocks


def load_cached_transcription(rec, config: PipelineConfig) -> Optional[PageTranscription]:
    """When manifest says up-to-date, rebuild transcription from stored JSON."""
    if not rec.structured_ocr_path or not Path(rec.structured_ocr_path).exists():
        return None
    if not rec.raw_ocr_path or not Path(rec.raw_ocr_path).exists():
        return None
    with open(rec.structured_ocr_path, "r", encoding="utf-8") as f:
        struct = json.load(f)
    layout = LayoutProfile(
        orientation=Orientation(struct["layout"]["orientation"]),
        reading_direction=ReadingDirection(struct["layout"]["reading_direction"]),
        column_count=struct["layout"]["column_count"],
        column_x_centers=struct["layout"].get("column_x_centers", []),
        avg_main_height=struct["layout"].get("avg_main_height", 0.0),
        avg_commentary_height=struct["layout"].get("avg_commentary_height", 0.0),
    )
    blocks = load_raw_blocks(Path(rec.raw_ocr_path))
    transcription = classify_and_order(blocks, layout, config)
    transcription.book = rec.book
    transcription.volume = rec.volume
    transcription.leaf = rec.leaf
    transcription.pdf_page = rec.pdf_page
    transcription.side = rec.side
    transcription.image_file = Path(rec.image_file)
    transcription.ocr_engine = struct.get("ocr_engine", rec.ocr_engine)
    transcription.review_status = rec.review_status
    transcription.ocr_confidence = rec.confidence
    transcription.raw_path = Path(rec.raw_ocr_path)
    transcription.structured_path = Path(rec.structured_ocr_path)
    return transcription

def run_ocr(leaf: Leaf, config: PipelineConfig, manifest: Manifest,
            force: bool = False) -> Optional[PageTranscription]:
    rec = manifest.get(leaf.book, leaf.leaf_number, leaf.side)
    ocr_version = f"{config.ocr_engine}-{config.ocr_quality}"

    if not force and rec and manifest.is_up_to_date(
        leaf.book, leaf.leaf_number, leaf.side, leaf.image_hash, ocr_version, config.pipeline_version
    ):
        cached = load_cached_transcription(rec, config)
        if cached:
            return cached

    engine = build_ocr_engine(config)
    img = Image.open(leaf.image_path)
    blocks = engine.recognize(img)

    # save raw OCR JSON
    raw_dir = config.dir("ocr_raw") / safe_book_name(leaf.book)
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_path = raw_dir / f"{leaf.book}_leaf{leaf.leaf_number:04d}_{leaf.side}_raw.json"
    raw_data = {
        "book": leaf.book,
        "leaf": leaf.leaf_number,
        "side": leaf.side,
        "pdf_page": leaf.pdf_index + 1,
        "image_file": str(leaf.image_path),
        "image_hash": leaf.image_hash,
        "ocr_engine": engine.version_info(),
        "blocks": [
            {
                "text": b.text,
                "bbox": [b.bbox.x0, b.bbox.y0, b.bbox.x1, b.bbox.y1],
                "score": b.score,
                "polygon": b.polygon,
            }
            for b in blocks
        ],
    }
    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump(raw_data, f, ensure_ascii=False, indent=2)

    # build layout profile
    layout = build_layout(blocks, img.width, img.height, config)
    struct_dir = config.dir("ocr_structured") / safe_book_name(leaf.book)
    struct_dir.mkdir(parents=True, exist_ok=True)
    struct_path = struct_dir / f"{leaf.book}_leaf{leaf.leaf_number:04d}_{leaf.side}_structured.json"
    struct_data = {
        "book": leaf.book,
        "leaf": leaf.leaf_number,
        "side": leaf.side,
        "pdf_page": leaf.pdf_index + 1,
        "image_file": str(leaf.image_path),
        "image_hash": leaf.image_hash,
        "ocr_engine": engine.version_info(),
        "layout": {
            "orientation": layout.orientation.value,
            "reading_direction": layout.reading_direction.value,
            "column_count": layout.column_count,
            "avg_main_height": layout.avg_main_height,
            "avg_commentary_height": layout.avg_commentary_height,
            "column_x_centers": layout.column_x_centers,
            "main_text_region": layout.main_text_region.to_polygon() if layout.main_text_region else None,
            "annotation_regions": [r.to_polygon() for r in layout.annotation_regions if r],
        },
        "raw_path": str(raw_path),
    }
    with open(struct_path, "w", encoding="utf-8") as f:
        json.dump(struct_data, f, ensure_ascii=False, indent=2)

    # reading order + classification
    transcription = classify_and_order(blocks, layout, config)
    transcription.book = leaf.book
    transcription.volume = manifest.get(leaf.book, leaf.leaf_number, leaf.side).volume
    transcription.leaf = leaf.leaf_number
    transcription.pdf_page = leaf.pdf_index + 1
    transcription.side = leaf.side
    transcription.image_file = leaf.image_path
    transcription.ocr_engine = engine.version_info()
    transcription.review_status = "auto"
    transcription.raw_path = raw_path
    transcription.structured_path = struct_path

    # review status based on confidence
    if transcription.ocr_confidence < config.high_priority_threshold:
        transcription.review_status = "flagged"
    elif transcription.ocr_confidence < config.review_threshold:
        transcription.review_status = "review"
    else:
        transcription.review_status = "auto"

    # update manifest
    if rec is None:
        rec = LeafRecord(
            book=leaf.book,
            volume=transcription.volume,
            leaf=leaf.leaf_number,
            pdf_page=leaf.pdf_index + 1,
            side=leaf.side,
            pdf_path=str(leaf.pdf_path),
            image_file=str(leaf.image_path),
            image_hash=leaf.image_hash,
            ocr_engine=config.ocr_engine,
            ocr_version=ocr_version,
            pipeline_version=config.pipeline_version,
        )
    rec.ocr_version = ocr_version
    rec.pipeline_version = config.pipeline_version
    rec.image_hash = leaf.image_hash
    rec.raw_ocr_path = str(raw_path)
    rec.structured_ocr_path = str(struct_path)
    rec.confidence = transcription.ocr_confidence
    rec.review_status = transcription.review_status
    manifest.upsert(rec)

    return transcription


def run_export(transcription: PageTranscription, config: PipelineConfig, manifest: Manifest) -> Path:
    md_path = export_leaf(transcription, config)
    rec = manifest.get(transcription.book, transcription.leaf, transcription.side)
    if rec:
        rec.markdown_path = str(md_path)
        manifest.upsert(rec)
    return md_path
