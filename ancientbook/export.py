# -*- coding: utf-8 -*-
"""Export canonical Markdown with provenance frontmatter."""
from __future__ import annotations

from pathlib import Path
from typing import List

import yaml

from ancientbook.config import PipelineConfig
from ancientbook.models import BlockType, Line, PageTranscription


def _safe_yaml_value(v):
    """Avoid YAML anchors; keep strings unicode-safe."""
    if isinstance(v, Path):
        return str(v)
    return v


def _lines_to_text(lines: List[Line]) -> str:
    out: List[str] = []
    for line in lines:
        text = "".join(b.text for b in line.blocks)
        if text:
            out.append(text)
    return "\n".join(out)


def render_markdown(transcription: PageTranscription, image_rel: Path, pdf_rel: Path) -> str:
    """Render one leaf transcription as canonical Markdown."""
    front = {
        "type": "ancient_book_transcription",
        "book": transcription.book,
        "volume": transcription.volume,
        "leaf": transcription.leaf,
        "pdf_page": transcription.pdf_page,
        "side": transcription.side,
        "ocr_engine": transcription.ocr_engine,
        "ocr_confidence": round(transcription.ocr_confidence, 4),
        "review_status": transcription.review_status,
    }
    main_lines = [l for l in transcription.lines if l.line_type == BlockType.MAIN_TEXT]
    comm_lines = [l for l in transcription.lines if l.line_type == BlockType.COMMENTARY]
    other_lines = [l for l in transcription.lines if l.line_type not in (BlockType.MAIN_TEXT, BlockType.COMMENTARY)]

    body = f"---\n{yaml.safe_dump(front, sort_keys=False, allow_unicode=True)}---\n\n"
    body += f"# {transcription.book} / {transcription.volume}\n\n"
    body += f"## 第 {transcription.leaf} 叶（PDF 第 {transcription.pdf_page} 页 / {transcription.side}）\n\n"

    body += "### 正文\n\n"
    body += _lines_to_text(main_lines) + "\n\n"

    if comm_lines:
        body += "### 注 / 批\n\n"
        body += "> " + "\n> ".join(_lines_to_text(comm_lines).splitlines()) + "\n\n"

    if other_lines:
        body += "### 其他\n\n"
        body += _lines_to_text(other_lines) + "\n\n"

    body += "### Source\n\n"
    body += f"- PDF: `{pdf_rel}`\n"
    body += f"- PDF Page: {transcription.pdf_page}\n"
    body += f"- Image: `{image_rel}`\n"
    body += f"- OCR Engine: {transcription.ocr_engine}\n"
    body += f"- OCR Confidence: {transcription.ocr_confidence:.4f}\n"
    body += f"- Review Status: {transcription.review_status}\n"
    return body


def export_leaf(transcription: PageTranscription, config: PipelineConfig) -> Path:
    out_dir = config.dir("transcription") / transcription.book
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / f"{transcription.book}_leaf{transcription.leaf:04d}.md"

    image_rel = transcription.image_file.relative_to(config.project_root)
    # PDF 路径已存于 manifest 与 structured OCR JSON；markdown 中只显示书名作为来源
    book_stub = transcription.image_file.stem.split("_ppdf")[0]
    pdf_rel = Path("data") / "sources" / "pdf" / f"{book_stub}.pdf"

    md = render_markdown(transcription, image_rel, pdf_rel)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md)
    return md_path
