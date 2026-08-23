# -*- coding: utf-8 -*-
"""Data models for pages, blocks, layout and transcriptions."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import List, Optional, Tuple


class ReadingDirection(str, Enum):
    RIGHT_TO_LEFT = "right_to_left"
    LEFT_TO_RIGHT = "left_to_right"
    TOP_TO_BOTTOM = "top_to_bottom"
    UNKNOWN = "unknown"


class Orientation(str, Enum):
    VERTICAL = "vertical"
    HORIZONTAL = "horizontal"
    UNKNOWN = "unknown"


class BlockType(str, Enum):
    MAIN_TEXT = "main_text"
    COMMENTARY = "commentary"
    ANNOTATION = "annotation"
    PAGE_HEADER = "page_header"
    PAGE_FOOTER = "page_footer"
    PAGE_NUMBER = "page_number"
    UNKNOWN = "unknown"


@dataclass
class Point:
    x: float
    y: float


@dataclass
class BBox:
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0

    @property
    def area(self) -> float:
        return self.width * self.height

    @property
    def center(self) -> Point:
        return Point((self.x0 + self.x1) / 2.0, (self.y0 + self.y1) / 2.0)

    def to_polygon(self) -> List[Tuple[float, float]]:
        return [(self.x0, self.y0), (self.x1, self.y0), (self.x1, self.y1), (self.x0, self.y1)]


@dataclass
class TextBlock:
    text: str
    bbox: BBox
    score: float = 0.0
    # derived geometry
    polygon: Optional[List[Tuple[float, float]]] = None

    @property
    def center(self) -> Point:
        return self.bbox.center

    @property
    def area(self) -> float:
        return self.bbox.area


@dataclass
class LayoutProfile:
    """每个版面一张独立的 profile，不硬编码全局版式。"""

    orientation: Orientation
    reading_direction: ReadingDirection
    column_count: int
    page_regions: List[BBox] = field(default_factory=list)
    main_text_region: Optional[BBox] = None
    annotation_regions: List[BBox] = field(default_factory=list)
    header_region: Optional[BBox] = None
    footer_region: Optional[BBox] = None
    page_number_region: Optional[BBox] = None
    # debug
    column_x_centers: List[float] = field(default_factory=list)
    avg_main_height: float = 0.0
    avg_commentary_height: float = 0.0


@dataclass
class Line:
    blocks: List[TextBlock] = field(default_factory=list)
    line_type: BlockType = BlockType.UNKNOWN

    def text(self) -> str:
        return "".join(b.text for b in self.blocks)


@dataclass
class PageTranscription:
    book: str
    volume: str
    leaf: int
    pdf_page: int
    side: str  # 'L' | 'R' | 'whole'
    image_file: Path
    ocr_engine: str
    ocr_confidence: float
    review_status: str
    lines: List[Line] = field(default_factory=list)
    raw_path: Optional[Path] = None
    structured_path: Optional[Path] = None


@dataclass
class Leaf:
    book: str
    pdf_path: Path
    pdf_index: int
    side: str
    leaf_number: int
    image_path: Path
    image_hash: str
