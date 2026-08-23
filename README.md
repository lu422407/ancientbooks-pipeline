# AncientBooks Pipeline

> 圖片型古籍 PDF → 結構化 Markdown → Knowledge Node → Obsidian
> 
> 完整 provenance + 可重跑 + 人工可校 + 可擴展

## 快速開始

```bash
# 安裝依賴（需先有 rapidocr 3.9+、pymupdf）
pip install -e .

# 一鍵跑完（ingest → ocr → export → review）
ancientbook run /Volumes/.../某古籍.pdf --book 某古籍 --volume 卷一 --limit-pages 5

# 分步執行
ancientbook ingest /Volumes/.../某古籍.pdf --book 某古籍 --volume 卷一 --limit-pages 5
ancientbook ocr --book 某古籍
ancientbook export --book 某古籍
ancientbook review

# 狀態
ancientbook status
```

## 目錄結構

```
AncientBooks/
├── ancientbook/                 # Python 包
│   ├── cli.py                   # Click CLI
│   ├── config.py                # PipelineConfig（可調閾值）
│   ├── models.py                # BBox / TextBlock / LayoutProfile / PageTranscription
│   ├── manifest.py              # 冪等 + provenance
│   ├── ingest.py                # PDF → 葉圖像 + spread 拆分
│   ├── layout.py                # 版面分析
│   ├── ocr_adapter.py           # OCREngine 抽象 + RapidOCR 實作
│   ├── structure.py             # 閱讀順序 + 正文/注分類
│   ├── export.py                # Canonical Markdown
│   ├── review.py                # 人工覆核佇列
│   └── pipeline.py              # 編排
├── tests/                       # 12 個 pytest 測試
├── data/
│   ├── sources/
│   │   ├── pdf/                 # 原始 PDF（Pipeline 不寫；只讀）
│   │   └── images/{book}/       # 拆頁後的葉圖像
│   ├── ocr/
│   │   ├── raw/{book}/          # OCR 原始 blocks + confidence
│   │   └── structured/{book}/   # 版面 + 結構化後的 JSON
│   ├── transcription/{book}/    # Canonical Markdown
│   ├── knowledge/
│   │   ├── concepts/            # 概念節點
│   │   ├── people/              # 人物
│   │   ├── methods/             # 方法
│   │   ├── events/              # 事件
│   │   ├── quotations/          # 引文
│   │   └── interpretations/     # 解釋
│   ├── metadata/
│   ├── manifests/manifest.json  # 全部葉的 provenance + 狀態
│   └── reports/
│       ├── review_queue.md      # 人工覆核佇列
│       └── poc_report.md        # POC 評估報告
├── pyproject.toml
├── _ocr_one.py                  # 每葉獨立子進程入口（避免 OOM）
└── _ocr_batch.sh                # 20 葉批量 runner
```

## 設計原則

1. **Provenance 不可破壞**：每個 Markdown 都帶 frontmatter 指向 PDF / 葉圖像 / OCR 引擎 / 信心值
2. **Raw 不可覆蓋**：`ocr/raw/` 是 OCR 原始輸出；`ocr/structured/` 是版面結構化結果；兩者獨立保存
3. **LLM 不偷當校勘者**：第一層 OCR 真值由引擎產生；LLM 只在 Knowledge Node 抽取層做解釋
4. **閾值可調不寫死**：`commentary_height_ratio / high_priority_threshold / review_threshold` 全部 CLI / 環境變量可調
5. **可重跑冪等**：manifest 用 `image_hash + ocr_version + pipeline_version` 三元組判斷是否要重做
6. **每葉獨立子進程**：RapidOCR 有記憶體洩漏（~7MB/葉），WorkBuddy Bash 預設上限會 SIGKILL；batch 腳本用 subprocess 隔離
7. **版面不寫死**：`LayoutProfile` 從 OCR 框推斷 orientation / reading_direction / column_count

## 測試

```bash
PYTHONPATH=. python -m pytest tests/ -v
```

12 個測試覆蓋：頁 hash、垂直版面、閱讀順序、塊分類、正文/注分離、provenance、markdown 導出、review queue、冪等、安全檔名、優先級標籤。
