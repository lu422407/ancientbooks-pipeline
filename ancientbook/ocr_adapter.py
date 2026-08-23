# -*- coding: utf-8 -*-
"""OCR Engine Adapter — do not bind to a single backend."""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, List, Tuple, Union

import numpy as np
from PIL import Image

from ancientbook.config import PipelineConfig
from ancientbook.models import BBox, TextBlock


class OCREngine(ABC):
    @abstractmethod
    def recognize(self, image: Union[np.ndarray, Image.Image, Path]) -> List[TextBlock]:
        """Return raw text blocks with geometry and confidence."""
        ...

    @abstractmethod
    def version_info(self) -> str:
        ...


class RapidOCREngine(OCREngine):
    """RapidOCR 3.x adapter (PP-OCRv6 det + PP-OCRv4 rec)."""

    def __init__(self, config: PipelineConfig):
        self.config = config
        self.quality = config.ocr_quality
        self._engine = None

    def _init_engine(self):
        if self._engine is not None:
            return
        from rapidocr import LangDet, LangRec, ModelType, OCRVersion, RapidOCR

        if self.quality == "high":
            rec_lang, rec_model = LangRec.CH, ModelType.SERVER
            version = "rapidocr_ch_server_v4"
        else:
            rec_lang, rec_model = LangRec.CHINESE_CHT, ModelType.MOBILE
            version = "rapidocr_cht_mobile_v4"
        self._version = version
        self._engine = RapidOCR(params={
            "Det.lang_type": LangDet.CH,
            "Det.model_type": ModelType.SMALL,
            "Det.ocr_version": OCRVersion.PPOCRV6,
            "Rec.lang_type": rec_lang,
            "Rec.model_type": rec_model,
            "Rec.ocr_version": OCRVersion.PPOCRV4,
        })

    def version_info(self) -> str:
        self._init_engine()
        return f"RapidOCR({self.quality})/{self._version}"

    def recognize(self, image: Union[np.ndarray, Image.Image, Path]) -> List[TextBlock]:
        self._init_engine()
        if isinstance(image, (str, Path)):
            img = Image.open(str(image)).convert("RGB")
            arr = np.array(img)
        elif isinstance(image, Image.Image):
            arr = np.array(image.convert("RGB"))
        else:
            arr = image
            if len(arr.shape) == 2:
                arr = np.stack([arr] * 3, axis=-1)
            elif arr.shape[-1] == 4:
                arr = arr[..., :3]

        res = self._engine(arr)
        boxes, txts, scores = self._unpack(res)
        if boxes is None:
            return []

        blocks: List[TextBlock] = []
        for box, txt, score in zip(boxes, txts, scores):
            text = txt[0] if isinstance(txt, (list, tuple)) else txt
            score_val = score[0] if isinstance(score, (list, tuple)) else score
            score_val = float(score_val) if score_val is not None else 0.0
            pts = np.array(box, dtype=float).reshape(-1, 2)
            x0, y0 = pts.min(axis=0)
            x1, y1 = pts.max(axis=0)
            bbox = BBox(float(x0), float(y0), float(x1), float(y1))
            if bbox.area < self.config.min_block_area:
                continue
            blocks.append(TextBlock(text=text, bbox=bbox, score=score_val, polygon=[tuple(p) for p in pts]))
        return blocks

    def _unpack(self, res: Any) -> Tuple[Any, Any, Any]:
        if isinstance(res, tuple):
            boxes = res[0] if len(res) > 0 else None
            txts = res[1] if len(res) > 1 else None
            scores = res[2] if len(res) > 2 else None
            if scores is None and boxes is not None:
                scores = [0.0] * len(boxes)
            return boxes, txts, scores
        boxes = getattr(res, "boxes", None)
        txts = getattr(res, "txts", None)
        scores = getattr(res, "scores", None)
        if scores is None and boxes is not None:
            try:
                scores = [0.0] * len(boxes)
            except TypeError:
                scores = []
        return boxes, txts, scores


def build_ocr_engine(config: PipelineConfig) -> OCREngine:
    if config.ocr_engine == "rapidocr":
        return RapidOCREngine(config)
    raise ValueError(f"Unknown OCR engine: {config.ocr_engine}")
