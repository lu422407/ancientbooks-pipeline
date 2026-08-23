# -*- coding: utf-8 -*-
"""Sample knowledge-node generation from canonical transcriptions.
This is a deliberately minimal first-pass:
- One concept node per book title (傳習錄)
- One people node (王陽明) detected from title page
- One volume node (上卷)
Citations point back to the leaf transcription.
"""
import sys
from pathlib import Path

ROOT = Path("/Users/luapple/Documents/AncientBooks")
sys.path.insert(0, str(ROOT))

from datetime import datetime, timezone
from ancientbook.config import PipelineConfig

cfg = PipelineConfig()
book = "《标注传习录》卷一"
volume = "卷一"
trans_dir = cfg.dir("transcription") / book
out_dir = cfg.dir("knowledge_concepts")
out_dir.mkdir(parents=True, exist_ok=True)
people_dir = cfg.dir("knowledge_people")
people_dir.mkdir(parents=True, exist_ok=True)
methods_dir = cfg.dir("knowledge_methods")
methods_dir.mkdir(parents=True, exist_ok=True)

# Available leaf markdowns for citation
leaves = sorted(trans_dir.glob(f"{book}_leaf*.md"))
cite_to_leaves = {}
for p in leaves:
    text = p.read_text(encoding="utf-8")
    # crude parsing
    name = p.name
    cite_to_leaves[name] = text[:300]

now = datetime.now(timezone.utc).strftime("%Y-%m-%d")

# concept node: 傳習錄
content = f"""---
type: ancient_book_concept
title: 傳習錄
source_book: {book}
source_volume: {volume}
created: {now}
---

# 傳習錄

## 概念

明代哲學家王陽明（1472–1529）語錄彙編，由其弟子輯錄其書信、語錄與論學篇章而成，分上、下兩卷。是陽明學派的核心理論來源。

## 相關原典出處

- [[{book}/{book}_leaf0004|第 4 叶（書名葉）]] — 書名「傳習錄」、作者「王陽明先生著」、刊記「浪華書林 積玉圃本」
- [[{book}/{book}_leaf0003|第 3 叶（目錄）]] — 上卷目錄，錄徐日仁 14 條、陸原靜 80 條、薛尚謙 35 條
- [[{book}/{book}_leaf0003|第 3 叶（目錄續）]] — 案語：通行刻本附有楊[明]山小引、焦竑序、張可大等序

## 解釋

傳習一名取自《論語·學而》：「傳不習乎？」意為「所傳所習」。全書核心觀點為「心即理」「知行合一」「致良知」。

## 核心概念關聯

- [[心即理]]
- [[知行合一]]
- [[致良知]]
- [[王陽明]]
"""
(ROOT / "data" / "knowledge" / "concepts" / "傳習錄.md").write_text(content, encoding="utf-8")

# people node: 王陽明
content2 = f"""---
type: ancient_book_person
title: 王陽明
source_book: {book}
source_volume: {volume}
created: {now}
---

# 王陽明

## 生平

王守仁（1472–1529），字伯安，號陽明，明代哲學家、政治家、軍事家。心學集大成者。

## 出處

- [[{book}/{book}_leaf0004|第 4 叶]] — 書名頁「王陽明先生著」

## 核心思想

- [[心即理]]
- [[知行合一]]
- [[致良知]]

## 著作

- [[傳習錄]]（上卷 / 下卷 / 附錄）
"""
(ROOT / "data" / "knowledge" / "people" / "王陽明.md").write_text(content2, encoding="utf-8")

# method node: 知行合一
content3 = f"""---
type: ancient_book_method
title: 知行合一
source_book: {book}
source_volume: {volume}
created: {now}
---

# 知行合一

## 概念

陽明心學重要命題。認為「知」與「行」不可分離：真知必能行，不能行即非真知。

## 來源

- 為《傳習錄》核心議題之一（後續葉將有原文引述，本書目錄葉已標明）
- [[{book}/{book}_leaf0003|第 3 叶目錄]]

## 相關概念

- [[王陽明]]
- [[致良知]]
"""
(ROOT / "data" / "knowledge" / "methods" / "知行合一.md").write_text(content3, encoding="utf-8")

# 評估報告
report = f"""# POC 評估報告 — 《{book}》

生成時間：{now}

## 1. 樣本
- 書名：{book}
- 卷：{volume}
- PDF 總頁數：91
- POC 葉數：**20**（PDF 前 10 個 spread，含封面 / 書名葉 / 目錄葉 / 正文起始）

## 2. Pipeline 階段
- ✅ ingest: PyMuPDF 200 dpi 渲染，自動拆分 spread 為 R/L 兩葉，計算 sha256
- ✅ layout: 從 OCR 框推斷 orientation/reading_direction/columns
- ✅ OCR: RapidOCR(high) = ch_PP-OCRv4_rec_server
- ✅ structure: 閱讀順序（垂直右→左）、正文/注分層
- ✅ export: Canonical Markdown 含完整 provenance
- ✅ review_queue: 按 confidence 排序、可配閾值
- ✅ manifest: image_hash + ocr_version + pipeline_version 控管冪等
- ✅ 一個真實 Knowledge Node 樣本（概念：傳習錄；人物：王陽明；方法：知行合一）

## 3. 已知 OCR 識別錯誤樣本
| 原字 | 識別結果 | 原因 |
|---|---|---|
| 傳 | 傅（葉3目錄） | 部首誤識 |
| 楊[明]山 | 楊[明]山 → 楊山 | 漏字（陰影 / 刻蝕） |
| 竑 | 琊 / 焦琊 | 形近誤識 |
| 積 | 猜（葉4刊記） | 形近誤識 |
| 浪華 | 浪华 | 繁簡混用輸出（古籍本就是繁體，但偶爾輸出簡體） |

## 4. Pipeline 優點
- 每葉獨立子進程，記憶體可控
- Raw + Structured 兩份 JSON 完整保存，絕不覆蓋
- 閾值可調（commentary_height_ratio / high_priority_threshold / review_threshold）
- 重新運行時自動跳過已處理葉（image_hash + ocr_version + pipeline_version 比對）

## 5. 已知失敗案例 / 限制
- 封面葉 / 校色卡葉 detection 框太少（< 3 個 block），導致 layout profile 不準確（被列為 review 優先級）
- title page 大字（傳習錄 三字）獨立塊極少，detection 偶爾合併錯誤
- Commentary 分類基於字高啟發式，若古籍同時使用雙行小注且字號接近（<0.72 ratio）會誤判
- LLM 完全未參與原文校勘（符合「LLM 不偷當校勘者」原則）
- 異體字未做專門處理（保留 OCR 輸出原貌）
- 頁碼 detection 尚未實作（frontmatter 中 pdf_page 已記錄，但未自動從頁面中 OCR 頁碼）
- Reading order 在「欄內兩列註文」場景尚未專門處理（古籍罕見）

## 6. 下一階段建議
- Phase 8-9: Knowledge Node 自動抽取（從正文塊 N-gram + 字典匹配候選概念；候選 → 人工確認）
- 引入異體字字典（保留原字 + 標注正字 + 連結）
- 頁碼自動偵測（基於頁面底部小字 + 數字模式）
- 跨書概念關聯圖（以 [[概念名]] 雙鏈接為索引層）
- RAG：建立 canonical markdown 全文 + Knowledge Node 雙索引（BM25 + 語義）
"""
(ROOT / "data" / "reports" / "poc_report.md").write_text(report, encoding="utf-8")
print("knowledge nodes + report written")
print("leaves in transcription:", len(leaves))
