from __future__ import annotations
from typing import Literal
from pydantic import BaseModel


class InteractionStep(BaseModel):
    action: Literal["click", "type", "input", "keys", "wait", "select", "eval", "scroll"]
    target: str                 # "{idx}" for element index, key name, or JS expression
    value: str | None = None    # Text to type, key to press, JS to eval, etc.
    wait_ms: int = 300          # Pause after this step (ms)
    note: str | None = None     # Human-readable explanation


class InteractionRecipe(BaseModel):
    widget_type: str            # "combobox", "date_segmented", "react_virtualized", "standard_select", "radio_group"
    ats_platform: str | None = None  # "workday", "greenhouse", "lever", etc.
    steps: list[InteractionStep]
    description: str            # Human-readable: "Click to open, type to filter, select match"


class QAPair(BaseModel):
    field_label: str
    normalized_key: str | None = None   # Canonical key from resolver
    field_type: str = "text"            # text, select, radio, checkbox, textarea, file, combobox
    answer: str
    options: list[str] | None = None
    source: Literal["profile", "history", "user", "inference"] = "user"
    company: str | None = None
    user_verified: bool = False
    interaction_recipe: InteractionRecipe | None = None  # How this field was successfully filled


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
