# 交接文档 — 古籍 OCR 流水线优化

> 交接日期：2026-08-23
> 交接背景：方案调研与代码审查已完成，尚未改代码。下一台机器（i3-10100 + 24G）接手实施。

## 1. 项目现状

- 本仓库 = `lu422407/ancientbooks-pipeline`，`handoff` 分支。
- **2026-08-23 已完成基础实施**（在旧笔记本上）：v5 模型档、中缝智能检测、JPEG 输出、温控 runner、评测工具、14 个单测全过、濒湖脉学小样 ingest 验证通过。剩余工作见 §7。
- 管线能力：PDF → 拆叶图像 → RapidOCR → 版面/结构化 → Markdown + 人工复核队列，manifest 幂等可断点续跑。
- 本机（笔记本）环境：仓库内 `.venv`（含 onnxruntime）；数据根 = 仓库目录。

## 2. 数据位置（重要）

- PDF 原件在**飞牛 NAS**，已映射 `Z:\`，根目录 `Z:\中医和古书`。
- **主要目标文件夹：`Z:\中医和古书\古中医书`（307 个 PDF，6.3GB）**，含：
  - 单文件为主（王叔和脉经 01-10、金匮要略、重刻庄子南华真经、张注列子、校正宋本伤寒论等）
  - 子目录：`皇帝内经/`(6)、`《校正宋本伤寒论》/`(3)、`针灸彩图/`、一个 djvu 目录
  - 另有 16 个 .djvu/.rar/.chm 需另行转换才能进管线
- 同根目录下还有 `中医/`(8，多为现代排印本+朗读音频)、`古代名著/`(43)、`PDF-MD/`(9)。
- 注意：早期目录名 `古书/` 已不存在（现为 `古中医书/`）。
- 设计约定（.gitignore 已体现）：**PDF 不拷入仓库、不上传 git**，ingest 时直接从 Z:\ 读。
- 换机器后需重新映射 Z:\（或改用 UNC 路径）。

### ⚠️ 两类截然不同的图像格式（务必先判型）
| 类型 | 特征 | 例子 | 管线行为 |
|---|---|---|---|
| 普通扫描件 | 满幅、白底黑字 | 濒湖脉学、多数排印本 | 直接拆页/整页 |
| **文物档案摄影** | 灰背景板+柯达色卡+标尺，书占中间 | **古中医书/ 王叔和脉经等** | 先裁背景，再拆页 |

后者已由 `crop_archive_photo()` + `native_dpi()` 自动处理（见 §4A）。
测试用书：`古中医书/《王叔和脉经》01.pdf`（31 页，档案摄影，含训点/朱批/藏书印）。

## 3. 硬件与目标

| 机器 | 配置 | 角色 |
|---|---|---|
| 老笔记本 | i5-3337U（2C4T 1.8GHz）+ GT 740M（无 CUDA/DML 价值） | 退役或只做轻活；夏天满载死机 |
| **新主力** | **i3-10100（4C8T）+ 24GB** | 跑全部 OCR；可本地 CPU 推理 7B VLM |

- **目标：精度优先，可以慢。全程离线优先（书页不上云）。**

## 4. 代码审查发现的问题（✅=已修复）

### 4A. 文物档案摄影支持（2026-08-23 第二轮，针对 `古中医书/`）

`Z:\中医和古书\古中医书`（307 个 PDF）里的《王叔和脉经》等是**文物级档案摄影**，
不是普通扫描件：画面含灰色背景板、柯达色卡、标尺，书只占中间一块。
这解释了此前的所有异常，已针对性修复：

1. ✅ **禁止放大渲染**：此类页声明 36×24 英寸，但内嵌图仅 2592×1728（等效 72 DPI）。
   原先按 `--dpi 300` 渲染 = 放大 4 倍到 **10800×7200（77.8MP）**，纯插值、无新信息、
   白烧 CPU（单叶 265 秒）。新增 `native_dpi()` 取 `min(请求dpi, 内嵌图原生dpi)`。
2. ✅ **裁掉背景板**：新增 `crop_archive_photo()`——以边缘像素估背景亮度，
   用"明显亮于背景"的像素定位书页包围盒并裁切；普通满幅扫描件不受影响。
3. ✅ **中缝检测改相对阈值**：原用绝对阈值（<160 算墨），灰背景板（~96-105）被误判为墨，
   导致中缝检测失效、跨页被当成"每页单半叶"整页保留。改用 P90 纸张亮度的相对阈值。

### 4B. 三个关键 bug（同轮修复）

4. ✅ **阅读顺序反转**：`split_spread` 把图像左侧（x=0 起）命名为 `right`。
   竖排书右起阅读，物理右页才在阅读顺序中靠前 → 原实现整个阅读顺序反了。
   已改为返回 `(物理右, 物理左)`。**这个 bug 会静默产生乱序文本，最危险。**
5. ✅ **叶号冲突**：`whole` 用 `pi+1`、拆页用 `pi*2+1/2`，同书混排时撞号
   （如 page1 的 whole=2 与 page0 的 L=2）。现整页也占 `pi*2+1`。
6. ✅ **导出互相覆盖**：markdown 文件名不含 side，叶号复用导致两份转写写进同一文件。
   现改为 `_leaf{NNNN}_{side}.md`。另加 `Manifest.purge_book_pages()`，
   重跑 ingest 时清理同页过期记录（whole↔R/L 切换后不留孤儿）。

### 4C. 前轮已修复（针对普通扫描件）

7. ✅ **高精度档用错模型**：新增 `v5` 档（PP-OCRv5 server 繁简一体）并设为默认。
8. ✅ **中缝居中硬切**：新增 `find_gutter_column()`，找不到缝就不拆。
9. ✅ **每叶重载模型**：`_ocr_chunk.py` + `run_batch.py`。
10. ✅ **PNG 慢**：默认 JPEG(q95)，DPI 300。
11. 仍未做：全库无并行；混排编号不美观（已不冲突）。

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

### 繁体刻本基线（2026-08-23，王叔和脉经01 三叶，旧笔记本 2 线程）

| 配置 | 平均置信度 | 低置信行 | 检出块 | 耗时 |
|---|---|---|---|---|
| high（v4 简体 server） | 0.8979 | 10/52 | 52 | 1172s |
| mobile（v4 繁体 mobile） | 0.7379 | 19/27 | 27 | 42s |
| **v5（PP-OCRv5 server）** | 0.8878 | **8/54** | **54** | 316s |

**⚠️ 本轮 high 置信度反超 v5（0.898 vs 0.888），但肉眼比对证明这是假象**——简体模型把繁体字「自信地读错」，置信度不降。逐字对照（叶2，参照肉眼转录）：

- high 错 5 字，含严重语义翻转：「腎→賢」「脈→豚」「脈→眼」「於→招」「脈→旅」，且简繁混输出（脉经/賢）。
- v5 错 2 字（「脈→旅」×2）+ 漏 2 个「於」；「腎」读对；还额外检出版心内容（页码「4」）。
- 叶3 同样：原文「扁鵲倉公華佗」v5 对 6/8，high 对 3/8；「虢太子」的「虢」v5 对 high 错成「號」；「顏色不變」v5 对 high 错成「颊色不」。

**定论：v5 为唯一正确选择**；mobile 在刻本上崩掉（块数减半）；置信度只可作分诊（进 review queue），不可作质量结论。此书扫描磨损重，正是疑难页 VLM 复核的目标类型。可选优化：输出经 OpenCC 统一简繁（保留 raw 不动）。

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
