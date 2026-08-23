"""
TieredExtractor — the content-first classifier (docs/02 §3):
  tier 1  form fields   (AcroForm /V)      — exact name/employer/wages
  tier 2  text layer    (pdfplumber)       — type + year + best-effort name
  tier 3  OCR           (stub)             — image-only ⇒ unreadable

Type + year come from the (static) template text, which is present on both blank and filled
forms; identity comes from tier 1 when available, else tier 2. Filename is never used here.
"""
from __future__ import annotations

import re
from collections import Counter

import pdfplumber
from pypdf import PdfReader

from app.models import DocType

from .base import Classification
from .fields_map import (
    F1040_FIELDS,
    F1040_TOKENS,
    MIN_CHARS,
    W2_FIELDS,
    W2_TOKENS,
    YEAR_MAX,
    YEAR_MIN,
)


def _text(path: str) -> str:
    try:
        with pdfplumber.open(path) as pdf:
            return "\n".join((p.extract_text() or "") for p in pdf.pages)
    except Exception:
        return ""


def _filled_fields(path: str) -> dict:
    try:
        fields = PdfReader(path).get_fields() or {}
    except Exception:
        return {}
    # Several W-2 copies share short names; keep only non-empty values (docs/02 §3.2 note).
    return {k.split(".")[-1]: str(v.get("/V")).strip()
            for k, v in fields.items() if v.get("/V")}


def _detect_type(text: str, fields: dict) -> DocType | None:
    low = text.lower()
    if any(tok in low for tok in F1040_TOKENS):
        return DocType.F1040
    if sum(tok in low for tok in W2_TOKENS) >= 2:
        return DocType.W2
    # Fallback: infer from which form fields are present.
    if fields.get(W2_FIELDS["wages"]) or fields.get(W2_FIELDS["first"]):
        return DocType.W2
    if fields.get(F1040_FIELDS["tp_first"]) or fields.get(F1040_FIELDS["tp_last"]):
        return DocType.F1040
    return None


def _detect_year(text: str) -> int | None:
    years = [int(y) for y in re.findall(r"\b(?:19|20)\d{2}\b", text)
             if YEAR_MIN <= int(y) <= YEAR_MAX]
    return Counter(years).most_common(1)[0][0] if years else None


def _num(raw: str | None) -> float | None:
    if not raw:
        return None
    try:
        return float(raw.replace("$", "").replace(",", "").strip())
    except ValueError:
        return None


def _name_from_text(text: str) -> str | None:
    """Best-effort employee name from a text-layer W-2 (label-anchored)."""
    m = re.search(r"[Ee]mployee'?s? name[^\n]*\n\s*([A-Z][a-z]+\s+[A-Z][a-z]+)", text)
    return m.group(1) if m else None


class TieredExtractor:
    def classify(self, file_path: str, original_filename: str) -> Classification:
        text = _text(file_path)
        fields = _filled_fields(file_path)

        # tier 3 — nothing to read
        if len(text.strip()) < MIN_CHARS and not fields:
            return Classification(None, None, None, confidence=0.05, readable=False,
                                  source="ocr", signals={"reason": "no text, no form fields"})

        doc_type = _detect_type(text, fields)
        year = _detect_year(text)
        person = employer = wages = None
        source = "text_layer"

        if fields and doc_type is DocType.W2 and (
                fields.get(W2_FIELDS["first"]) or fields.get(W2_FIELDS["last"])):
            person = f"{fields.get(W2_FIELDS['first'], '')} {fields.get(W2_FIELDS['last'], '')}".strip()
            employer = fields.get(W2_FIELDS["employer"])
            wages = _num(fields.get(W2_FIELDS["wages"]))
            source = "form_fields"
        elif fields and doc_type is DocType.F1040 and (
                fields.get(F1040_FIELDS["tp_first"]) or fields.get(F1040_FIELDS["tp_last"])):
            person = f"{fields.get(F1040_FIELDS['tp_first'], '')} {fields.get(F1040_FIELDS['tp_last'], '')}".strip()
            source = "form_fields"
        elif text:
            person = _name_from_text(text)
            source = "text_layer"

        confidence = self._score(source, doc_type, year, person)
        signals = {"has_form_fields": bool(fields), "text_chars": len(text.strip()),
                   "detected_type": doc_type.value if doc_type else None, "year": year}
        return Classification(doc_type, year, person or None, employer, wages,
                              confidence, True, source, signals)

    @staticmethod
    def _score(source: str, doc_type, year, person) -> float:
        if source == "form_fields":
            return 0.95 if (doc_type and year) else 0.80
        if doc_type and year and person:
            return 0.80
        if doc_type and year:
            return 0.50          # can't tell who ⇒ needs review
        return 0.40
