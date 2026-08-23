#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""温控友好批处理 runner（跨平台，替代 macOS 专用的 _ocr_batch.sh）。

设计（针对弱机/夏天场景）：
- 单 worker 串行，不吃满 CPU
- 每 chunk 一个子进程：模型加载成本摊薄到整个 chunk，内存泄漏被 chunk 大小约束
- Windows 下自动把子进程优先级降为 BelowNormal，跑批时机器保持可交互
- 叶间冷却间歇 + ONNX/OMP 线程上限，压住发热

用法示例：
  python run_batch.py --book 濒湖脉学 --dry-run        # 查看待处理叶
  python run_batch.py --book 濒湖脉学                    # v5 + 300DPI 默认档
  python run_batch.py --book 濒湖脉学 --cooldown 5      # 更保守的散热间歇
重跑安全：manifest 幂等，已完成的叶自动 SKIP。
"""
import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent
PY = sys.executable


def set_low_priority(pid: int) -> bool:
    """Windows: BELOW_NORMAL_PRIORITY_CLASS；其他平台忽略。"""
    if os.name != "nt":
        return False
    try:
        import ctypes
        k32 = ctypes.windll.kernel32
        PROCESS_SET_INFORMATION = 0x0200
        BELOW_NORMAL_PRIORITY_CLASS = 0x4000
        h = k32.OpenProcess(PROCESS_SET_INFORMATION, False, pid)
        if not h:
            return False
        ok = bool(k32.SetPriorityClass(h, BELOW_NORMAL_PRIORITY_CLASS))
        k32.CloseHandle(h)
        return ok
    except Exception:
        return False


def main():
    ap = argparse.ArgumentParser(description="温控友好古籍 OCR 批处理", formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--book", required=True, help="书名（须已 ingest，与 manifest 中一致）")
    ap.add_argument("--quality", default="v5", choices=["v5", "high", "mobile"])
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--limit", type=int, default=0, help="最多处理 N 叶（0=全部）")
    ap.add_argument("--chunk-size", type=int, default=40, help="每 chunk 叶数（模型复用 & 内存隔离）")
    ap.add_argument("--cooldown", type=float, default=2.0, help="叶间冷却秒数")
    ap.add_argument("--threads", type=int, default=2, help="OMP/ONNX 线程数上限")
    ap.add_argument("--dry-run", action="store_true", help="只列出待处理叶")
    args = ap.parse_args()

    os.environ.setdefault("ANCIENTBOOK_ROOT", str(REPO))
    sys.path.insert(0, str(REPO))
    from ancientbook.config import PipelineConfig
    from ancientbook.manifest import get_manifest

    cfg = PipelineConfig()
    manifest = get_manifest(cfg)
    recs = [r for r in manifest.all().values() if r.book == args.book]
    recs.sort(key=lambda r: (r.pdf_page, 0 if r.side == "R" else 1))
    if args.limit:
        recs = recs[:args.limit]
    specs = [f"{r.leaf}:{r.side}" for r in recs]
    if not specs:
        sys.exit(f"[batch] manifest 中没有书 {args.book!r} 的叶记录，请先运行 ancientbook ingest。")
    print(f"[batch] book={args.book} leaves={len(specs)} quality={args.quality} dpi={args.dpi} "
          f"chunk={args.chunk_size} cooldown={args.cooldown}s threads={args.threads}")
    if args.dry_run:
        print("[batch] dry-run:", " ".join(specs[:20]), ("..." if len(specs) > 20 else ""))
        return

    env = dict(os.environ)
    env["OMP_NUM_THREADS"] = str(args.threads)
    env["ANCIENTBOOK_ONNX_THREADS"] = str(args.threads)
    env["ANCIENTBOOK_ROOT"] = str(REPO)

    t_start = time.time()
    done = 0
    for i in range(0, len(specs), args.chunk_size):
        chunk = specs[i:i + args.chunk_size]
        print(f"[batch] chunk {i // args.chunk_size + 1}: {len(chunk)} leaves")
        p = subprocess.Popen(
            [PY, str(REPO / "_ocr_chunk.py"), args.book, args.quality,
             str(args.dpi), str(args.cooldown), *chunk],
            cwd=str(REPO), env=env,
        )
        set_low_priority(p.pid)
        rc = p.wait()
        done += len(chunk)
        print(f"[batch] 进度 {done}/{len(specs)} (chunk rc={rc}, 累计 {time.time() - t_start:.0f}s)")
        if rc != 0:
            print("[batch] chunk 异常退出，继续下一 chunk（manifest 幂等，可安全重跑）")
    print(f"[batch] 全部完成：{len(specs)} leaves，总用时 {(time.time() - t_start) / 60:.1f} min")


if __name__ == "__main__":
    main()
