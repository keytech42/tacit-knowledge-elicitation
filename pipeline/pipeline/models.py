"""Intermediate data types for all pipeline stages."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


# --- Stage 1: Ingestion ---


class SourceType(str, Enum):
    slack = "slack"
    notion = "notion"
    pdf = "pdf"
    text = "text"


class ParsedChunk(BaseModel):
    text: str
    chunk_index: int
    total_chunks: int
    char_offset: int = 0


class ParsedDocument(BaseModel):
    source_path: str
    source_type: SourceType
    title: str
    raw_text: str
    chunks: list[ParsedChunk] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
    content_hash: str = ""


# --- Stage 2: Norm Extraction ---


class NormType(str, Enum):
    stated = "stated"
    practiced = "practiced"


class NormStatement(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    text: str
    norm_type: NormType
    source_document: str = ""
    source_passage: str = ""
    confidence: float = 0.0


# --- Stage 3: Contradiction Detection ---


class Severity(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class Contradiction(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    norm_a_id: str
    norm_b_id: str
    tension_description: str
    severity: Severity = Severity.medium
    confidence: float = 0.0


# --- Stage 4: Question Generation ---


class GeneratedQuestion(BaseModel):
    title: str
    body: str
    category: str = ""
    evidence: list[str] = Field(default_factory=list)
    source_passages: list[str] = Field(default_factory=list)
    suggested_options: list[str] = Field(default_factory=list)
    confidence: float = 0.0


# --- Run Manifest ---


class StageStatus(str, Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    skipped = "skipped"


class StageResult(BaseModel):
    name: str
    status: StageStatus = StageStatus.pending
    started_at: datetime | None = None
    completed_at: datetime | None = None
    item_count: int = 0
    error: str | None = None


class RunManifest(BaseModel):
    run_id: str
    experiment_name: str
    config_file: str
    started_at: datetime
    completed_at: datetime | None = None
    stages: list[StageResult] = Field(default_factory=list)
    totals: dict[str, int] = Field(default_factory=dict)
