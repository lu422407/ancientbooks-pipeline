# -*- coding: utf-8 -*-
"""Manifest: idempotency, provenance and review status."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from ancientbook.config import DATA_DIRS, PipelineConfig


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass
class LeafRecord:
    book: str
    volume: str
    leaf: int
    pdf_page: int
    side: str
    pdf_path: str
    image_file: str
    image_hash: str
    ocr_engine: str
    ocr_version: str
    pipeline_version: str
    raw_ocr_path: Optional[str] = None
    structured_ocr_path: Optional[str] = None
    markdown_path: Optional[str] = None
    review_status: str = "pending"  # pending / auto / reviewed / flagged
    confidence: float = 0.0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "LeafRecord":
        # ignore unknown future keys
        return cls(**{k: v for k, v in d.items() if k in {f.name for f in cls.__dataclass_fields__.values()}})


class Manifest:
    def __init__(self, path: Path):
        self.path = path
        self.records: Dict[str, LeafRecord] = {}
        self.load()

    def _key(self, book: str, leaf: int, side: str) -> str:
        return f"{book}::{leaf}::{side}"

    def load(self) -> None:
        if not self.path.exists():
            return
        with open(self.path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for k, v in data.get("records", {}).items():
            self.records[k] = LeafRecord.from_dict(v)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "manifest_version": "0.1.0",
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "records": {k: v.to_dict() for k, v in self.records.items()},
        }
        tmp = self.path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        tmp.replace(self.path)

    def get(self, book: str, leaf: int, side: str) -> Optional[LeafRecord]:
        return self.records.get(self._key(book, leaf, side))

    def upsert(self, record: LeafRecord) -> None:
        key = self._key(record.book, record.leaf, record.side)
        record.updated_at = datetime.now(timezone.utc).isoformat()
        self.records[key] = record
        self.save()

    def is_up_to_date(self, book: str, leaf: int, side: str, image_hash: str,
                      ocr_version: str, pipeline_version: str) -> bool:
        rec = self.get(book, leaf, side)
        if not rec:
            return False
        return (
            rec.image_hash == image_hash
            and rec.ocr_version == ocr_version
            and rec.pipeline_version == pipeline_version
        )

    def all(self) -> Dict[str, LeafRecord]:
        return dict(self.records)

    def remove(self, book: str, leaf: int, side: str) -> None:
        self.records.pop(self._key(book, leaf, side), None)

    def purge_book_pages(self, book: str, pdf_pages: set) -> int:
        """删除某书指定 PDF 页的旧记录（重跑 ingest 后清理过期叶）。

        同一 PDF 页重新 ingest 后可能由 whole 变为 R/L（或相反），
        旧的 side 记录若不清除会与新的共用叶号，导致导出互相覆盖。
        """
        stale = [k for k, r in self.records.items()
                 if r.book == book and r.pdf_page in pdf_pages]
        for k in stale:
            del self.records[k]
        if stale:
            self.save()
        return len(stale)


def get_manifest(config: Optional[PipelineConfig] = None) -> Manifest:
    cfg = config or PipelineConfig()
    return Manifest(cfg.dir("manifests") / "manifest.json")
