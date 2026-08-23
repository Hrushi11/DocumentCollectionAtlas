"""The classifier interface — one small contract everything else depends on (docs/02 §3.1)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Protocol

from app.models import DocType


@dataclass
class Classification:
    doc_type: Optional[DocType]
    tax_year: Optional[int]
    person_name: Optional[str]          # extracted from CONTENT, not the filename
    employer_name: Optional[str] = None
    wages: Optional[float] = None
    confidence: float = 0.0
    readable: bool = True
    source: str = "filename"            # form_fields | text_layer | ocr | filename
    signals: dict = field(default_factory=dict)


class Classifier(Protocol):
    def classify(self, file_path: str, original_filename: str) -> Classification: ...
