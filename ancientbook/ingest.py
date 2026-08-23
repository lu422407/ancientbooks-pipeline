# -*- coding: utf-8 -*-
"""PDF -> page/leaf images with hashes and provenance."""
from __future__ import annotations

import io
from pathlib import Path
from typing import List, Tuple

import fitz  # PyMuPDF
import numpy as np
from PIL import Image

from ancientbook.config import PipelineConfig
from ancientbook.manifest import LeafRecord, sha256_bytes, sha256_file
from ancientbook.models import BBox, Leaf, TextBlock


def _pil_from_pixmap(pix) -> Image.Image:
    # PyMuPDF samples: RGBA if alpha, else RGB
    img = Image.frombytes("RGB" if pix.n == 3 else "RGBA", [pix.width, pix.height], pix.samples)
    if img.mode == "RGBA":
        rgb = Image.new("RGB", img.size, (255, 255, 255))
        rgb.paste(img, mask=img.split()[-1])
        return rgb
    return img


def render_pdf_page(doc: fitz.Document, page_index: int, dpi: int = 200) -> Image.Image:
    page = doc[page_index]
    pix = page.get_pixmap(dpi=dpi)
    return _pil_from_pixmap(pix)


def find_spread_split_column(image: Image.Image, blocks: List[TextBlock], gap_ratio: float = 0.25) -> int:
    """基于 OCR 框的 x 密度寻找跨页中缝；未提供 blocks 时回退中线。"""
    w = image.width
    if not blocks:
        return w // 2
    # density histogram over x (bin width ~ 5 px)
    hist = np.zeros(w, dtype=np.float32)
    for b in blocks:
        x0 = max(0, int(b.bbox.x0))
        x1 = min(w, int(b.bbox.x1))
        hist[x0:x1] += 1
    # smooth
    kernel = np.ones(11)
    conv = np.convolve(hist, kernel, mode="same")
    # search valley in central zone
    margin = int(w * gap_ratio)
    zone = conv[margin:-margin]
    if zone.size == 0:
        return w // 2
    valley = int(np.argmin(zone)) + margin
    return valley


def split_spread(image: Image.Image, split_x: int) -> Tuple[Image.Image, Image.Image]:
    right = image.crop((0, 0, split_x, image.height))
    left = image.crop((split_x, 0, image.width, image.height))
    return right, left


def leaf_name(book: str, pdf_index: int, side: str) -> str:
    return f"{book}_ppdf{pdf_index+1:04d}_{side}.png"


def safe_book_name(name: str) -> str:
    safe = []
    for c in name:
        if c.isalnum() or c in "_-\u4e00-\u9fff":
            safe.append(c)
        elif c in "《》()（）[]【】":
            continue
        else:
            safe.append("_")
    return "".join(safe).rstrip("_")[:80]


def ingest_pdf(pdf_path: Path, book: str, volume: str, config: PipelineConfig,
               limit_pages: int = 0, existing_manifest=None) -> List[Leaf]:
    """渲染 PDF，若配置 split_spread=True 则将每页拆为左右两叶。"""
    config.dir("sources_images").mkdir(parents=True, exist_ok=True)
    book_safe = safe_book_name(book)
    out_dir = config.dir("sources_images") / book_safe
    out_dir.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(str(pdf_path))
    total = doc.page_count
    n = min(total, limit_pages) if limit_pages else total
    leaves: List[Leaf] = []

    for pi in range(n):
        img = render_pdf_page(doc, pi, dpi=config.dpi)
        img_bytes = io.BytesIO()
        img.save(img_bytes, format="PNG")
        img_bytes.seek(0)
        full_hash = sha256_bytes(img_bytes.read())
        img_bytes.seek(0)

        if config.split_spread:
            # for split, first get a quick OCR-free center split based on image
            split_x = img.width // 2
            right_img, left_img = split_spread(img, split_x)
            # numbering convention: PDF physical right side is the book's earlier recto page
            right_path = out_dir / leaf_name(book_safe, pi, "R")
            left_path = out_dir / leaf_name(book_safe, pi, "L")
            right_img.save(right_path, "PNG")
            left_img.save(left_path, "PNG")
            leaves.append(Leaf(book, pdf_path, pi, "R", pi * 2 + 1, right_path, sha256_file(right_path)))
            leaves.append(Leaf(book, pdf_path, pi, "L", pi * 2 + 2, left_path, sha256_file(left_path)))
        else:
            leaf_path = out_dir / leaf_name(book_safe, pi, "whole")
            img.save(leaf_path, "PNG")
            leaves.append(Leaf(book, pdf_path, pi, "whole", pi + 1, leaf_path, sha256_file(leaf_path)))

    doc.close()
    return leaves


def update_manifest_from_leaves(leaves: List[Leaf], config: PipelineConfig,
                                volume: str = "", ocr_engine: str = "rapidocr",
                                ocr_version: str = "", manifest=None):
    from ancientbook.manifest import get_manifest
    m = manifest or get_manifest(config)
    for leaf in leaves:
        rec = m.get(leaf.book, leaf.leaf_number, leaf.side)
        if rec is None:
            rec = LeafRecord(
                book=leaf.book,
                volume=volume,
                leaf=leaf.leaf_number,
                pdf_page=leaf.pdf_index + 1,
                side=leaf.side,
                pdf_path=str(leaf.pdf_path),
                image_file=str(leaf.image_path),
                image_hash=leaf.image_hash,
                ocr_engine=ocr_engine,
                ocr_version=ocr_version,
                pipeline_version=config.pipeline_version,
            )
        else:
            rec.image_hash = leaf.image_hash
            rec.pdf_path = str(leaf.pdf_path)
            rec.image_file = str(leaf.image_path)
        m.upsert(rec)
    return m
