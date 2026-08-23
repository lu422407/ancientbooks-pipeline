# -*- coding: utf-8 -*-
"""Review queue: flag low-confidence / problematic leaves."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

from ancientbook.config import PipelineConfig
from ancientbook.manifest import Manifest


def priority_label(confidence: float, config: PipelineConfig) -> str:
    if confidence < config.high_priority_threshold:
        return "high"
    if confidence < config.review_threshold:
        return "review"
    return "low"


def generate_review_queue(manifest: Manifest, config: PipelineConfig) -> Path:
    out_path = config.dir("reports") / "review_queue.md"
    config.dir("reports").mkdir(parents=True, exist_ok=True)

    records = sorted(manifest.all().values(), key=lambda r: (r.confidence, r.leaf))
    lines = [
        "# OCR Review Queue\n",
        f"\n生成时间: {datetime.now(timezone.utc).isoformat()}\n",
        f"阈值配置: high_priority={config.high_priority_threshold}, review={config.review_threshold}\n\n",
        "| 书 | 叶 | side | confidence | status | 优先级 | markdown |\n",
        "|---|---|---|---|---|---|---|\n",
    ]
    for rec in records:
        prio = priority_label(rec.confidence, config)
        md = rec.markdown_path or ""
        lines.append(
            f"| {rec.book} | {rec.leaf} | {rec.side} | {rec.confidence:.3f} | {rec.review_status} | {prio} | `{md}` |\n"
        )

    # Detailed section for non-low priority
    lines.append("\n## 需要人工复核的页面\n\n")
    flagged = [r for r in records if priority_label(r.confidence, config) != "low"]
    if not flagged:
        lines.append("暂无高优先级复核项。\n")
    for rec in flagged:
        lines.append(
            f"\n### {rec.book} / {rec.volume} / 第 {rec.leaf} 叶 ({rec.side})\n\n"
            f"- Confidence: {rec.confidence:.3f}\n"
            f"- Image: `{rec.image_file}`\n"
            f"- Raw OCR: `{rec.raw_ocr_path}`\n"
            f"- Markdown: `{rec.markdown_path}`\n\n"
            "疑似问题：\n\n"
            "- [ ] OCR 置信度偏低\n"
            "- [ ] 阅读顺序需人工确认\n"
            "- [ ] 正文/注文边界不确定\n"
            "- [ ] 存在异体字或缺字\n\n"
        )

    with open(out_path, "w", encoding="utf-8") as f:
        f.writelines(lines)
    return out_path
