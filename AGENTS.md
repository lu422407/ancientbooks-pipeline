# AGENTS.md — 接手前必读

**完整背景、方案、待办见 `HANDOFF.md`（本分支）。** 硬约束摘要：

- 目标：**精度优先，可以慢**；全程离线优先，书页不上云。
- PDF 原件在飞牛 NAS 的 `Z:\中医和古书`（368 个 PDF），只读、不拷入仓库。
- 主力机：i3-10100 + 24GB（无独显）；老笔记本夏天满载会死机，别给它派重活。
- 2026-08-23 已完成：v5 模型档（默认）、中缝智能检测（无缝不拆）、JPEG/q95、DPI300、温控 runner `run_batch.py`、评测工具 `tools/eval_baseline.py`。测试 14 个全过。
- 跑批一律用 `python run_batch.py --book 书名`（幂等可断点续跑）；换模型/参数先跑评测基线。
- Ollama 跑 Qwen2.5-VL 必须 `num_ctx≈4096`，否则内存爆炸。
- 数据根用环境变量 `ANCIENTBOOK_ROOT` 指到本仓库。
- 剩余大项：全量初稿（10100 夜间挂机）→ 双模型互校 → VLM 疑难页复核 → 复核 HTML。详见 HANDOFF.md §7。
