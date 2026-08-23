# -*- coding: utf-8 -*-
"""Chunk worker: 每个 chunk 一个进程——模型只加载一次，内存泄漏被 chunk 大小约束。

与 _ocr_one.py 的区别：一次处理多叶（模型加载成本摊薄），由 run_batch.py 调度。
"""
import os
import sys
import time
from pathlib import Path

ROOT = Path(os.environ.get("ANCIENTBOOK_ROOT", Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT))

from ancientbook.config import PipelineConfig
from ancientbook.manifest import get_manifest
from ancientbook.models import Leaf
from ancientbook.pipeline import run_export, run_ocr


def main():
    # argv: book quality dpi cooldown leafspec...  其中 leafspec = "叶号:边" 如 "3:R"
    book, quality, dpi, cooldown = sys.argv[1:5]
    cooldown = float(cooldown)
    specs = sys.argv[5:]
    cfg = PipelineConfig(ocr_quality=quality, dpi=int(dpi))
    manifest = get_manifest(cfg)
    ok = skip = fail = 0
    for spec in specs:
        no, side = spec.split(":")
        rec = manifest.get(book, int(no), side)
        if rec is None:
            print(f"NO_REC {no} {side}", flush=True)
            skip += 1
            continue
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
        try:
            t = run_ocr(leaf, cfg, manifest, force=False)
            if t is None:
                print(f"SKIP {no} {side}", flush=True)
                skip += 1
            else:
                run_export(t, cfg, manifest)
                dt = time.time() - t0
                print(f"OK {no} {side} {dt:.1f}s conf={t.ocr_confidence:.4f} lines={len(t.lines)}", flush=True)
                ok += 1
        except Exception as e:
            print(f"FAIL {no} {side} {type(e).__name__}: {e}", flush=True)
            fail += 1
        if cooldown > 0:
            time.sleep(cooldown)
    print(f"CHUNK_DONE ok={ok} skip={skip} fail={fail}", flush=True)


if __name__ == "__main__":
    main()
