# -*- coding: utf-8 -*-
"""Layout detection from OCR boxes; orientation and reading direction are detected, not hard-coded."""
from __future__ import annotations

from typing import List, Optional, Tuple

import numpy as np

from ancientbook.config import PipelineConfig
from ancientbook.models import BBox, BlockType, LayoutProfile, Orientation, ReadingDirection, TextBlock


def _box_height(b: TextBlock) -> float:
    return b.bbox.height


def _box_width(b: TextBlock) -> float:
    return b.bbox.width


def detect_orientation(blocks: List[TextBlock]) -> Orientation:
    if not blocks:
        return Orientation.UNKNOWN
    heights = np.array([_box_height(b) for b in blocks])
    widths = np.array([_box_width(b) for b in blocks])
    # vertical text boxes are tall and narrow; horizontal are short and wide
    ratios = heights / np.maximum(widths, 1.0)
    if np.median(ratios) > 1.4:
        return Orientation.VERTICAL
    if np.median(ratios) < 0.8:
        return Orientation.HORIZONTAL
    return Orientation.UNKNOWN


def detect_columns(blocks: List[TextBlock], img_width: int, img_height: int) -> Tuple[int, List[float]]:
    """按 x 中心聚类得到栏数；返回（栏数，每栏中心 x）。"""
    if not blocks:
        return 0, []
    centers = np.array([b.bbox.center.x for b in blocks])
    # tolerance proportional to median character height
    med_h = np.median([_box_height(b) for b in blocks]) if blocks else 20
    thr = max(15, med_h * 0.6)
    sorted_centers = sorted(centers)
    columns: List[List[float]] = []
    for cx in sorted_centers:
        placed = False
        for col in columns:
            avg = sum(col) / len(col)
            if abs(cx - avg) < thr:
                col.append(cx)
                placed = True
                break
        if not placed:
            columns.append([cx])
    x_centers = [sum(col) / len(col) for col in columns]
    return len(columns), x_centers


def estimate_main_text_height(blocks: List[TextBlock]) -> float:
    if not blocks:
        return 0.0
    heights = sorted([_box_height(b) for b in blocks], reverse=True)
    # take median of upper half as main text height (main text usually largest)
    n = max(1, len(heights) // 2)
    return float(np.median(heights[:n]))


def classify_regions(blocks: List[TextBlock], img_width: int, img_height: int,
                    config: PipelineConfig) -> Tuple[List[TextBlock], List[TextBlock], List[TextBlock]]:
    """Rough region classification: main vs commentary vs margin based on size and y position."""
    main_height = estimate_main_text_height(blocks)
    commentary_threshold = main_height * config.commentary_height_ratio if main_height else 0.0
    main_blocks: List[TextBlock] = []
    commentary_blocks: List[TextBlock] = []
    margin_blocks: List[TextBlock] = []

    top_margin = img_height * 0.08
    bottom_margin = img_height * 0.92
    for b in blocks:
        h = _box_height(b)
        cy = b.bbox.center.y
        if cy < top_margin or cy > bottom_margin:
            margin_blocks.append(b)
        elif h < commentary_threshold and h > 0:
            commentary_blocks.append(b)
        else:
            main_blocks.append(b)
    return main_blocks, commentary_blocks, margin_blocks


def build_layout(blocks: List[TextBlock], img_width: int, img_height: int,
                 config: PipelineConfig) -> LayoutProfile:
    orientation = detect_orientation(blocks)
    column_count, x_centers = detect_columns(blocks, img_width, img_height)

    if orientation == Orientation.VERTICAL:
        reading_direction = ReadingDirection.RIGHT_TO_LEFT
    elif orientation == Orientation.HORIZONTAL:
        reading_direction = ReadingDirection.LEFT_TO_RIGHT
    else:
        reading_direction = ReadingDirection.UNKNOWN

    main_blocks, commentary_blocks, margin_blocks = classify_regions(blocks, img_width, img_height, config)

    def _bbox_of(blocks_sub: List[TextBlock]) -> Optional[BBox]:
        if not blocks_sub:
            return None
        x0 = min(b.bbox.x0 for b in blocks_sub)
        y0 = min(b.bbox.y0 for b in blocks_sub)
        x1 = max(b.bbox.x1 for b in blocks_sub)
        y1 = max(b.bbox.y1 for b in blocks_sub)
        return BBox(x0, y0, x1, y1)

    main_text_region = _bbox_of(main_blocks)
    annotation_regions = [_bbox_of(commentary_blocks)] if commentary_blocks else []

    # header/footer: small blocks in top/bottom margin
    header_blocks = [b for b in margin_blocks if b.bbox.center.y < img_height * 0.08]
    footer_blocks = [b for b in margin_blocks if b.bbox.center.y > img_height * 0.92]
    header_region = _bbox_of(header_blocks)
    footer_region = _bbox_of(footer_blocks)

    # page number candidate: footer region or isolated small block near a corner
    page_number_region = None
    if footer_blocks:
        page_number_region = _bbox_of(footer_blocks)

    avg_main = np.median([_box_height(b) for b in main_blocks]) if main_blocks else 0.0
    avg_comm = np.median([_box_height(b) for b in commentary_blocks]) if commentary_blocks else 0.0

    return LayoutProfile(
        orientation=orientation,
        reading_direction=reading_direction,
        column_count=column_count,
        page_regions=[main_text_region] if main_text_region else [],
        main_text_region=main_text_region,
        annotation_regions=annotation_regions,
        header_region=header_region,
        footer_region=footer_region,
        page_number_region=page_number_region,
        column_x_centers=x_centers,
        avg_main_height=float(avg_main),
        avg_commentary_height=float(avg_comm),
    )
