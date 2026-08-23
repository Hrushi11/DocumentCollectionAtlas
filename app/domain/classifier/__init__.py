"""Pluggable document classification (docs/02 §3)."""
from .base import Classification, Classifier
from .extractor import TieredExtractor
from .stub import StubClassifier

__all__ = ["Classification", "Classifier", "TieredExtractor", "StubClassifier"]
