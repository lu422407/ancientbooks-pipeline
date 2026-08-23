# -*- coding: utf-8 -*-
"""Reading order reconstruction and main-text/commentary classification."""
from __future__ import annotations

from typing import List

import numpy as np

from ancientbook.config import PipelineConfig
from ancientbook.models import BlockType, LayoutProfile, Line, Orientation, PageTranscription, ReadingDirection, TextBlock


def _same_column(a: TextBlock, b: TextBlock, tolerance: float) -> bool:
    return abs(a.bbox.center.x - b.bbox.center.x) < tolerance


def _group_into_columns(blocks: List[TextBlock], tolerance: float) -> List[List[TextBlock]]:
    if not blocks:
        return []
    items = sorted(blocks, key=lambda b: b.bbox.center.x)
    columns: List[List[TextBlock]] = []
    for b in items:
        placed = False
        for col in columns:
            if _same_column(b, col[0], tolerance):
                col.append(b)
                placed = True
                break
        if not placed:
            columns.append([b])
    # sort columns by center x
    for col in columns:
        col.sort(key=lambda b: b.bbox.center.y)
    columns.sort(key=lambda col: col[0].bbox.center.x, reverse=False)
    return columns


def _build_lines_from_columns(columns: List[List[TextBlock]]) -> List[Line]:
    """Columns are already ordered according to reading direction."""
    lines: List[Line] = []
    for col in columns:
        # within a column, merge overlapping-y boxes into one line (vertical text: characters stacked)
        col_sorted = sorted(col, key=lambda b: b.bbox.center.y)
        current: List[TextBlock] = []
        for b in col_sorted:
            if current and abs(b.bbox.center.y - current[-1].bbox.center.y) > max(b.bbox.height, current[-1].bbox.height) * 0.5:
                current.sort(key=lambda b: b.bbox.center.y)
                lines.append(Line(blocks=current))
                current = [b]
            else:
                current.append(b)
        if current:
            current.sort(key=lambda b: b.bbox.center.y)
            lines.append(Line(blocks=current))
    return lines


def reconstruct_reading_order(blocks: List[TextBlock], layout: LayoutProfile,
                            config: PipelineConfig) -> List[Line]:
    if not blocks:
        return []
    tolerance = np.median([b.bbox.width for b in blocks]) * 0.75 if blocks else 20.0
    if layout.orientation == Orientation.VERTICAL:
        # sort columns right-to-left
        columns = _group_into_columns(blocks, tolerance)
        columns.sort(key=lambda col: col[0].bbox.center.x, reverse=True)
    elif layout.orientation == Orientation.HORIZONTAL:
        columns = _group_into_columns(blocks, tolerance)
        columns.sort(key=lambda col: col[0].bbox.center.x, reverse=False)
    else:
        # fallback: left-to-right
        columns = _group_into_columns(blocks, tolerance)
        columns.sort(key=lambda col: col[0].bbox.center.x, reverse=False)
    return _build_lines_from_columns(columns)


def classify_and_order(blocks: List[TextBlock], layout: LayoutProfile,
                       config: PipelineConfig) -> PageTranscription:
    """Separate main text, commentary, and margin; then reconstruct reading order independently."""
    if not layout.main_text_region:
        # fallback: classify by height only
        main_blocks = blocks
        comm_blocks: List[TextBlock] = []
    else:
        main_blocks = []
        comm_blocks = []
        threshold = layout.avg_main_height * config.commentary_height_ratio if layout.avg_main_height else 0.0
        for b in blocks:
            if b.bbox.height < threshold and threshold > 0:
                comm_blocks.append(b)
            else:
                main_blocks.append(b)

    main_lines = reconstruct_reading_order(main_blocks, layout, config)
    for line in main_lines:
        line.line_type = BlockType.MAIN_TEXT

    comm_lines = reconstruct_reading_order(comm_blocks, layout, config)
    for line in comm_lines:
        line.line_type = BlockType.COMMENTARY

    # keep original order: main text first, then commentary (top notes often come after in canonical text? We'll keep sections separated)
    all_lines = main_lines + comm_lines

    confidences = [b.score for line in all_lines for b in line.blocks]
    avg_conf = float(np.mean(confidences)) if confidences else 0.0

    return PageTranscription(
        book="",
        volume="",
        leaf=0,
        pdf_page=0,
        side="",
        image_file=None,  # type: ignore[arg-type]
        ocr_engine="",
        ocr_confidence=avg_conf,
        review_status="auto",
        lines=all_lines,
    )
