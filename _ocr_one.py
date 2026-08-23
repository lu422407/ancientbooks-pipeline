# -*- coding: utf-8 -*-
"""Per-leaf subprocess to keep memory bounded (RapidOCR leaks ~7MB/leaf)."""
import os
import sys
import time
from pathlib import Path

ROOT = Path(os.environ.get("ANCIENTBOOK_ROOT", Path.home() / "Documents" / "AncientBooks"))
sys.path.insert(0, str(ROOT))

from ancientbook.config import PipelineConfig
from ancientbook.manifest import get_manifest
from ancientbook.models import Leaf
from ancientbook.pipeline import run_ocr, run_export


def main():
    book, leaf_no, side, quality, dpi = sys.argv[1:6]
    cfg = PipelineConfig(ocr_quality=quality, dpi=int(dpi))
    manifest = get_manifest(cfg)
    rec = manifest.get(book, int(leaf_no), side)
    if rec is None:
        print(f"NO_REC {leaf_no} {side}")
        sys.exit(0)
    leaf = Leaf(
        book=rec.book,
        pdf_path=Path(rec.pdf_path),
        pdf_index=rec.pdf_page - 1,
        side=rec.side,
        leaf_number=rec.leaf,
        image_path=Path(rec.image_file),
        image_hash=rec.image_hash,
    )
    t0 = time.time()
    t = run_ocr(leaf, cfg, manifest, force=False)
    dt = time.time() - t0
    if t is None:
        print(f"SKIP {leaf_no} {side}")
        sys.exit(0)
    md = run_export(t, cfg, manifest)
    print(f"OK {leaf_no} {side} {dt:.1f}s conf={t.ocr_confidence:.4f} lines={len(t.lines)} md={md.name}")


if __name__ == "__main__":
    main()
