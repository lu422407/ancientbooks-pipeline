# -*- coding: utf-8 -*-
"""Pipeline configuration & paths."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List


PROJECT_ROOT = Path(os.environ.get("ANCIENTBOOK_ROOT", Path.home() / "Documents" / "AncientBooks"))

DATA_DIRS = {
    "sources_pdf": PROJECT_ROOT / "data" / "sources" / "pdf",
    "sources_images": PROJECT_ROOT / "data" / "sources" / "images",
    "ocr_raw": PROJECT_ROOT / "data" / "ocr" / "raw",
    "ocr_structured": PROJECT_ROOT / "data" / "ocr" / "structured",
    "transcription": PROJECT_ROOT / "data" / "transcription",
    "annotations": PROJECT_ROOT / "data" / "annotations",
    "metadata": PROJECT_ROOT / "data" / "metadata",
    "manifests": PROJECT_ROOT / "data" / "manifests",
    "reports": PROJECT_ROOT / "data" / "reports",
    "knowledge_concepts": PROJECT_ROOT / "data" / "knowledge" / "concepts",
    "knowledge_people": PROJECT_ROOT / "data" / "knowledge" / "people",
    "knowledge_events": PROJECT_ROOT / "data" / "knowledge" / "events",
    "knowledge_methods": PROJECT_ROOT / "data" / "knowledge" / "methods",
    "knowledge_quotations": PROJECT_ROOT / "data" / "knowledge" / "quotations",
    "knowledge_interpretations": PROJECT_ROOT / "data" / "knowledge" / "interpretations",
}


def ensure_dirs() -> None:
    for p in DATA_DIRS.values():
        p.mkdir(parents=True, exist_ok=True)


@dataclass
class PipelineConfig:
    """可配置阈值；用户希望阈值可调，不能写死。"""

    project_root: Path = PROJECT_ROOT

    # image rendering
    dpi: int = 300  # 古籍笔画细，200 DPI 对识别偏低

    # leaf image storage: 'png'(无损) | 'jpeg'(快约10倍，q95 对笔画影响可忽略)
    image_format: str = "jpeg"
    jpeg_quality: int = 95

    # OCR
    # 'v5'     -> PP-OCRv5 server（繁简一体，精度首选，新默认）
    # 'high'   -> PP-OCRv4 server 简体（旧配置，仅留作基线对比）
    # 'mobile' -> PP-OCRv4 mobile 繁体(cht)
    ocr_quality: str = "v5"
    ocr_engine: str = "rapidocr"

    # layout
    split_spread: bool = True
    spread_gap_ratio: float = 0.25  # 中缝留白宽度比例阈值

    # review thresholds
    high_priority_threshold: float = 0.80
    review_threshold: float = 0.95
    # commentary size ratio
    commentary_height_ratio: float = 0.72
    # minimum block area (px²) to keep
    min_block_area: int = 80

    # provenance
    pipeline_version: str = "0.1.0"

    def dir(self, name: str) -> Path:
        return self.project_root / DATA_DIRS[name].relative_to(PROJECT_ROOT)
