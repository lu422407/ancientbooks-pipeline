# -*- coding: utf-8 -*-
"""评测基线：同一批叶，多个 OCR 配置对比（换模型前先跑这个）。

用法（需先 ingest）：
  python tools/eval_baseline.py --book 濒湖脉学 --leaves 3

输出：每配置的平均置信度 / 低置信行占比 / 块数 / 耗时，
以及逐行文本转储到 data/reports/eval/<book>/<quality>.md，供肉眼比对。
置信度只是代理指标，最终以肉眼比对为准。
"""
import argparse
import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
os.environ.setdefault("ANCIENTBOOK_ROOT", str(REPO))

from PIL import Image

from ancientbook.config import PipelineConfig
from ancientbook.manifest import get_manifest
from ancientbook.ocr_adapter import build_ocr_engine

QUALITIES = ["high", "mobile", "v5"]


def main():
    ap = argparse.ArgumentParser(description="OCR 配置评测基线")
    ap.add_argument("--book", required=True)
    ap.add_argument("--leaves", type=int, default=3, help="均匀抽取的叶数")
    args = ap.parse_args()

    cfg = PipelineConfig()
    manifest = get_manifest(cfg)
    recs = [r for r in manifest.all().values() if r.book == args.book]
    recs.sort(key=lambda r: (r.pdf_page, 0 if r.side == "R" else 1))
    if not recs:
        sys.exit(f"[eval] manifest 中没有 {args.book!r}，请先运行 ancientbook ingest。")
    step = max(1, len(recs) // args.leaves)
    sample = recs[::step][:args.leaves]
    out_dir = cfg.dir("reports") / "eval" / args.book
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[eval] book={args.book} sample={[f'{r.leaf}{r.side}' for r in sample]}")
    for q in QUALITIES:
        qcfg = PipelineConfig(ocr_quality=q)
        engine = build_ocr_engine(qcfg)
        scores_all, low, blocks_all, times, dump = [], 0, 0, [], []
        for rec in sample:
            img = Image.open(rec.image_file)
            t0 = time.time()
            blocks = engine.recognize(img)
            times.append(time.time() - t0)
            s = [b.score for b in blocks]
            scores_all.extend(s)
            low += sum(1 for x in s if x < 0.80)
            blocks_all += len(blocks)
            mean_leaf = sum(s) / len(s) if s else 0.0
            dump.append(f"### leaf {rec.leaf} {rec.side} conf={mean_leaf:.3f} lines={len(blocks)}")
            dump.extend(f"{b.score:.3f} {b.text}" for b in blocks)
        mean = sum(scores_all) / len(scores_all) if scores_all else 0.0
        (out_dir / f"{q}.md").write_text("\n".join(dump), encoding="utf-8")
        print(f"[eval] {q:7s} mean_conf={mean:.4f} low(<0.80)={low}/{len(scores_all)} "
              f"blocks={blocks_all} time={sum(times):.1f}s -> {out_dir / (q + '.md')}")
    print("[eval] 完成。请人工比对三个转储文件（置信度是代理指标，肉眼才是终审）。")


if __name__ == "__main__":
    main()
