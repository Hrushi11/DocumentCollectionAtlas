"""A deterministic classifier for tests — returns whatever Classification you hand it."""
from __future__ import annotations

from .base import Classification


class StubClassifier:
    def __init__(self, result: Classification):
        self.result = result

    def classify(self, file_path: str, original_filename: str) -> Classification:
        return self.result
