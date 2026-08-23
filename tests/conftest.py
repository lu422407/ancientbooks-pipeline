# -*- coding: utf-8 -*-
"""Shared fixtures."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from ancientbook.config import PipelineConfig


@pytest.fixture
def tmp_project(tmp_path: Path):
    cfg = PipelineConfig(project_root=tmp_path, dpi=200)
    for name in ["sources_images", "ocr_raw", "ocr_structured", "transcription", "manifests", "reports"]:
        cfg.dir(name).mkdir(parents=True, exist_ok=True)
    return cfg
