# 交接文档 — 古籍 OCR 流水线优化

> 交接日期：2026-08-23
> 交接背景：方案调研与代码审查已完成，尚未改代码。下一台机器（i3-10100 + 24G）接手实施。

## 1. 项目现状

- 本仓库 = `lu422407/ancientbooks-pipeline`，`handoff` 分支。
- **2026-08-23 已完成基础实施**（在旧笔记本上）：v5 模型档、中缝智能检测、JPEG 输出、温控 runner、评测工具、14 个单测全过、濒湖脉学小样 ingest 验证通过。剩余工作见 §7。
- 管线能力：PDF → 拆叶图像 → RapidOCR → 版面/结构化 → Markdown + 人工复核队列，manifest 幂等可断点续跑。
- 本机（笔记本）环境：仓库内 `.venv`（含 onnxruntime）；数据根 = 仓库目录。

## 2. 数据位置（重要）

- PDF 原件在**飞牛 NAS**，已映射 `Z:\`，根目录 `Z:\中医和古书`，共 **368 个 PDF**。
  - `Z:\中医和古书\中医\`（约 8 本，含神农本草经、伤寒杂病论桂林古本、濒湖脉学等）
  - `Z:\中医和古书\古书\`（绝大多数，传习录、淮南鸿烈解、王叔和脉经、故唐律疏义等）
  - 根目录：`黄帝外经.pdf`
- 设计约定（.gitignore 已体现）：**PDF 不拷入仓库、不上传 git**，ingest 时直接从 Z:\ 读。
- 换机器后需重新映射 Z:\（或改用 UNC 路径）。
- 测试用薄书建议：`Z:\中医和古书\中医\濒湖脉学.pdf`。

## 3. 硬件与目标

| 机器 | 配置 | 角色 |
|---|---|---|
| 老笔记本 | i5-3337U（2C4T 1.8GHz）+ GT 740M（无 CUDA/DML 价值） | 退役或只做轻活；夏天满载死机 |
| **新主力** | **i3-10100（4C8T）+ 24GB** | 跑全部 OCR；可本地 CPU 推理 7B VLM |

- **目标：精度优先，可以慢。全程离线优先（书页不上云）。**

## 4. 代码审查发现的问题（✅=已修复，2026-08-23）

1. ✅ **高精度档用错模型**：`ocr_adapter.py` 原 `high` 档用 PP-OCRv4 简体 server 识别繁体书。现已新增 `v5` 档（PP-OCRv5 server，繁简一体）并设为默认；旧 `high`/`mobile` 档保留作基线对比。
2. ✅ **中缝居中硬切**：`ingest.py` 新增 `find_gutter_column()`——降采样像素墨迹密度找中央带空白谷底，带宽度校验（≥4% 页宽，避免把列间隙当中缝）；**找不到缝就不拆**（每页单半叶的扫描格式整页作一叶）。注意：实测 `濒湖脉学.pdf` 就是每页单半叶格式，页 1（封面）有宽空白会被拆 R/L，正文页整页保留。
3. ✅ **每叶重载模型**：新增 `_ocr_chunk.py`（每 chunk 一进程、模型加载一次）+ `run_batch.py` 调度。
4. ✅ **批处理脚本不可用**：`run_batch.py` 跨平台替代 macOS 专用 `_ocr_batch.sh`。
5. ✅ **PNG 慢且三重哈希**：默认 JPEG(q95) 输出，删除了从未使用的整页哈希；DPI 默认 300。
6. 已知小瑕疵：一本书内混有拆页和整页时叶编号会撞号（如 `2:L` 与 `2:whole` 并存）——manifest 键不冲突，仅编号不美观，后续可改为统一按 PDF 页计。
7. 仍未做：全库无并行（在 10100 上也只需 1~2 worker，不急）。

## 5. 已定技术方案

### 5.1 模型与渲染（核心精度升级）
- 识别：**PP-OCRv5 SERVER**（原生繁简一体，含拼音/和刻），替换 v4 简体 server。
- 检测：v6 从 SMALL 升 **SERVER**（若 rapidocr 无此组合则保持 SMALL）。
- 渲染 DPI：**200 → 300**（`ancientbook/config.py:44`）。
- 参考写法（改 `ocr_adapter.py` `_init_engine`）：
  ```python
  RapidOCR(params={
      "Det.lang_type": LangDet.CH,
      "Det.model_type": ModelType.SERVER,      # 原 SMALL
      "Det.ocr_version": OCRVersion.PPOCRV6,
      "Rec.lang_type": LangRec.CH,             # v5 主模型原生含繁体
      "Rec.model_type": ModelType.SERVER,
      "Rec.ocr_version": OCRVersion.PPOCRV5,   # 原 PPOCRV4
  })
  ```

### 5.2 中缝切分修复
ingest 拆页前用**像素墨迹密度直方图找谷底**（复用 `find_spread_split_column` 的平滑+谷底逻辑，数据源从 OCR blocks 换成降采样二值化图像的列墨量）。另逐书确认是否整开跨页（不需要拆的把 `split_spread=False`）。

### 5.3 双模型互校（精度大杀器，慢就慢）
两种配置各跑一遍（如 v5 server + CHT v4），逐行对齐后：
- 置信度取高者为准；
- **读法不一致的行进 review queue，双读法并排展示**。
符合项目「LLM 不偷当校勘者」原则：机器产真值，分歧交人工。

### 5.4 疑难页本地 VLM 复核（零 API 成本）
- 全量初稿：PP-OCRv5（快）。
- 低置信/互校分歧页（约 5~15%）：送本地 **Ollama Qwen2.5-VL 7B**（Q4 约 6GB，CPU 每页 1~3 分钟，24G 内存够）。
- **关键坑：必须限制上下文** `num_ctx ≈ 4096`，否则 Ollama 默认大上下文会吃几十 GB 内存（实测翻车案例见参考链接）。
- 3B 版可做快筛（每页几十秒）。
- 备选轻量 VLM：PaddleOCR-VL 0.9B（CPU 可跑但慢、部署链路主推 GPU）、HunyuanOCR 1B（CPU 生态不成熟，观望）。

### 5.5 温控（若还用笔记本；台式机可放宽）
单进程顺序批处理 + 每 worker 复用模型、每 30~50 叶回收进程（摊薄泄漏）；ONNX `intra_op_num_threads=2`；进程优先级 BelowNormal；可配叶间冷却间歇；夜间跑。

### 5.6 ingest 优化
JPEG(90) 替代 PNG；去掉重复哈希。

## 6. 新机器环境搭建

```bash
git clone https://github.com/lu422407/ancientbooks-pipeline.git
cd ancientbooks-pipeline
git checkout handoff                 # 交接分支
python -m venv .venv && .venv\Scripts\activate
pip install -e .                     # rapidocr[onnxruntime] / pymupdf，首次运行自动下模型
pip install pytest                   # 跑测试用

# Ollama（疑难页复核用）
# 官网 https://ollama.com 装 Windows 版
ollama pull qwen2.5vl:7b             # 记得 num_ctx 限制 4096！

# 数据根指到仓库内（否则默认 ~/Documents/AncientBooks）
setx ANCIENTBOOK_ROOT <仓库绝对路径>

# 映射飞牛 Z: 后验证
ls Z:/中医和古书
```

### 日常跑批（run_batch.py，温控友好）
```bash
python run_batch.py --book 濒湖脉学 --dry-run     # 查看待处理叶
python run_batch.py --book 濒湖脉学                # v5 + 300DPI 默认档
python run_batch.py --book X --cooldown 5         # 更保守散热（笔记本）
python run_batch.py --book X --threads 4          # 台式机可放宽
# 重跑安全：manifest 幂等，已完成叶自动 SKIP

# 评测基线（换任何模型/参数前后都先跑）
python tools/eval_baseline.py --book 濒湖脉学 --leaves 3
# 输出三配置对比 + data/reports/eval/<book>/*.md 逐行转储供肉眼比对
```

## 7. 待办清单（基础部分已完成，剩余如下）

1. ~~评测基线~~（工具已就位：`tools/eval_baseline.py`；在 10100 上用真实古籍——《濒湖脉学》是现代排印本，代表性不足，建议再抽 `古书/` 里一两种刻本扫描对比）。
2. ~~换模型 + DPI300 + 中缝修复 + runner + JPEG~~ ✅ 2026-08-23 完成。
3. **全量初稿**：在 10100 上逐书 `ancientbook ingest`（Z: 直读）+ `run_batch.py`，夜间挂机。
4. 双模型互校 + 分歧报告并入 review queue（§5.3，未实施）。
5. Ollama Qwen2.5-VL 疑难页复核集成（§5.4，未实施），结果合入 review queue。
6. 人工复核提效：叶面图像+文本对照的 HTML（未实施）。
7. （远期）注册 EvaHan 拿数据集、租 GPU LoRA 微调专属模型。

## 8. 调研结论摘要（2026-08）

### 首次评测基线（2026-08-23，濒湖脉学 3 叶，旧笔记本 2 线程）

| 配置 | 平均置信度 | 低置信行(<0.80) | 耗时* |
|---|---|---|---|
| high（v4 简体 server，旧默认） | 0.9418 | 1/13 | 514s |
| mobile（v4 繁体 mobile） | 0.9367 | 0/13 | 22s |
| **v5（PP-OCRv5 server，新默认）** | **0.9609** | **0/13** | 201s |

\* 含首次模型下载，仅量级参考。肉眼比对：原文「珍因撮粹撷华，僭撰此书」high 漏读「撮」「僭」二字，v5 全对；high 另有一条 0.554 的乱码行，v5 无。

**重要发现**：`濒湖脉学.pdf` 是简体横排现代排印本——馆藏为简繁混杂（`中医/` 多新排印本，`古书/` 多繁体刻本扫描）。v5 繁简一体正是为此。**下一步应在 `古书/` 里选一种繁体刻本重跑 `tools/eval_baseline.py` 验证繁体场景**，再开始全量。

### GitHub 调研结论

- GitHub 上**没有**「下载即用、本地 CPU 跑、精度强于 PP-OCRv5」的古籍专用 OCR 引擎。古籍专用高精度只有两种形态：云 API 编排（guji-ocr，¥0.016/页）或自己微调。
- 古籍 OCR 精度前沿已在**多模态大模型**（EvaHan 2026 基线即 Qwen2.5-VL 微调）。传统检测+识别管线的角色 = 便宜初稿 + 置信度分诊。
- 本方案全部本地化：初稿（PP-OCRv5）+ 疑难页（本地 Qwen2.5-VL）+ 人工复核，零 API 费、书不出内网。
- 全量 368 本约 11 万页：初稿每叶 1~3s，疑难页每页 1~3 分钟，挂机数周可完成，符合"可以慢"。

## 9. 关键参考

- EvaHan 2026（古籍评测/数据集/基线）：https://github.com/GoThereGit/EvaHan
- guji-ocr（云 API 三 Agent 参考）：https://github.com/daiuuuuu/guji-ocr
- 荀子 XunziALLM（古籍后处理 LLM）：https://github.com/Xunzi-LLM-of-Chinese-classics/XunziALLM
- PaddleOCR-VL：https://github.com/PaddlePaddle/PaddleOCR
- HunyuanOCR：https://github.com/Tencent-Hunyuan/HunyuanOCR
- Qwen llama.cpp 指南：https://qwen.readthedocs.io/en/latest/quantization/llama.cpp.html
- Ollama 内存爆掉案例（num_ctx 坑）：https://dev.to/ljkunal/how-ollama-silently-ate-65gb-of-my-vram-and-how-i-fixed-it-22pf
- RapidOCR 模型列表：https://rapidai.github.io/RapidOCRDocs/main/model_list/
- duguang-ocr-onnx-v2（通用备选）：https://www.modelscope.cn/models/mscoder/duguang-ocr-onnx-v2
