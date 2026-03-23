from __future__ import annotations
from typing import Literal
from pydantic import BaseModel


class QAPair(BaseModel):
    field_label: str
    normalized_key: str | None = None   # Canonical key from resolver
    field_type: str = "text"            # text, select, radio, checkbox, textarea, file
    answer: str
    options: list[str] | None = None
    source: Literal["profile", "history", "user", "inference"] = "user"
    company: str | None = None
    user_verified: bool = False


class ApplicationRecord(BaseModel):
    id: str
    url: str
    company: str
    job_title: str
    applied_at: str                      # ISO 8601
    status: Literal["in_progress", "submitted", "failed", "withdrawn"] = "in_progress"
    qa_pairs: list[QAPair] = []


class ApplicationHistory(BaseModel):
    applications: list[ApplicationRecord] = []
