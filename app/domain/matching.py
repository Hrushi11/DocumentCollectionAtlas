"""
Ingestion & matching (docs/04 §3). Turns an uploaded file into a decision:
auto-match a confident document to an open requirement slot, or route anything ambiguous
(unreadable / low-confidence / wrong-year / unknown-person / unexpected-extra) to review.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

from app.domain.classifier.base import Classification
from app.models import (
    Actor,
    DocState,
    DocType,
    Document,
    Event,
    ExceptionReason,
    ExtractionSource,
    HumanOverride,
    Origin,
    Requirement,
    RequirementDocument,
)

LOW_CONFIDENCE = 0.60

_SRC = {"form_fields": ExtractionSource.FORM_FIELDS, "text_layer": ExtractionSource.TEXT_LAYER,
        "ocr": ExtractionSource.OCR, "filename": ExtractionSource.FILENAME}


def _now():
    return datetime.now(timezone.utc)


def expected_year(doc_type: DocType | None, client) -> int | None:
    """Per-type year rule (docs/04 §3) — do NOT compare against client.tax_year blindly."""
    if doc_type is DocType.W2:
        return client.tax_year
    if doc_type is DocType.F1040:
        return client.tax_year - 1
    return None                      # ID (and unknown) are not year-scoped


def resolve_person(client, name: str | None):
    if not name:
        return None
    n = name.strip().lower()
    for p in client.people:
        pn = p.name.lower()
        if pn == n or pn.startswith(n) or n in pn or set(n.split()) <= set(pn.split()):
            return p
    return None


# --------------------------------------------------------------------------- helpers
def _log(session, client, actor, verb, doc):
    session.add(Event(client_id=client.id, actor=actor, verb=verb,
                      payload_json={"document_id": doc.id, "state": doc.state.value}))


def _is_active(req: Requirement) -> bool:
    if req.human_override in (HumanOverride.WAIVED, HumanOverride.REMOVED):
        return False
    return (req.system_required or req.origin is Origin.HUMAN
            or req.human_override is HumanOverride.PINNED)


def _has_active_link(req: Requirement) -> bool:
    return any(link.active for link in req.links)


def find_open_slot(session, client, doc_type: DocType, person_id, tax_year):
    reqs = session.query(Requirement).filter_by(client_id=client.id, doc_type=doc_type).all()
    cands = [r for r in reqs
             if _is_active(r) and r.person_id == person_id and not _has_active_link(r)
             and (doc_type is DocType.ID or r.tax_year == tax_year)]
    cands.sort(key=lambda r: r.slot_index)
    return cands[0] if cands else None


def _set_exception(session, client, doc, reason: ExceptionReason):
    doc.state = DocState.EXCEPTION
    doc.exception_reason = reason
    _log(session, client, Actor.SYSTEM, f"exception:{reason.value}", doc)


def _match(session, client, doc, req: Requirement, by: Origin, actor: Actor):
    link = RequirementDocument(linked_by=by, active=True)
    link.requirement = req          # relationship assignment keeps loaded collections fresh
    link.document = doc
    session.add(link)
    doc.state = DocState.MATCHED
    _log(session, client, actor, "auto_matched" if by is Origin.SYSTEM else "reviewed_accept", doc)


def _route(session, client, doc: Document, human_reviewed: bool = False):
    """Apply the intake gates to a document whose guess_* fields are already set.

    `human_reviewed=True` (a reassignment) skips the confidence gate — the accountant has
    already vouched for the guess — but the year/person/slot gates still apply."""
    if not doc.readable:
        return _set_exception(session, client, doc, ExceptionReason.UNREADABLE)
    if not human_reviewed and doc.confidence < LOW_CONFIDENCE:
        doc.state = DocState.NEEDS_REVIEW
        return _log(session, client, Actor.SYSTEM, "needs_review", doc)
    exp = expected_year(doc.guess_type, client)
    if exp is not None and doc.guess_year and doc.guess_year != exp:
        return _set_exception(session, client, doc, ExceptionReason.WRONG_YEAR)
    if doc.guess_person_id is None and doc.guess_type is not DocType.F1040:
        return _set_exception(session, client, doc, ExceptionReason.UNKNOWN_PERSON)
    # The 1040 is a household-level requirement (person_id is None) even though we extracted
    # the taxpayer's name from it.
    slot_person = None if doc.guess_type is DocType.F1040 else doc.guess_person_id
    slot = find_open_slot(session, client, doc.guess_type, slot_person, doc.guess_year)
    if slot is None:
        return _set_exception(session, client, doc, ExceptionReason.UNEXPECTED_EXTRA)
    _match(session, client, doc, slot, Origin.SYSTEM, Actor.SYSTEM)


# --------------------------------------------------------------------------- public API
def ingest(session, client, file_path: str, original_filename: str, classifier) -> Document:
    g: Classification = classifier.classify(file_path, original_filename)
    person = resolve_person(client, g.person_name)
    doc = Document(
        client_id=client.id, original_filename=original_filename, stored_path=file_path,
        guess_type=g.doc_type, guess_year=g.tax_year,
        guess_person_id=person.id if person else None, guess_person_name=g.person_name,
        extracted_employer=g.employer_name, extracted_wages=g.wages,
        extraction_source=_SRC.get(g.source), confidence=g.confidence, readable=g.readable,
        signals_json=g.signals, state=DocState.NEEDS_REVIEW,
    )
    session.add(doc)
    session.flush()
    _log(session, client, Actor.SYSTEM, "document_received", doc)
    _route(session, client, doc)
    session.commit()
    return doc


# --- review-queue actions (the human resolving the attention queue) ---
def accept(session, client, doc: Document, req: Requirement) -> Document:
    for link in doc.links:
        link.active = False
    _match(session, client, doc, req, Origin.HUMAN, Actor.ACCOUNTANT)
    doc.exception_reason = None
    doc.resolved_by, doc.resolved_at = Actor.ACCOUNTANT, _now()
    session.commit()
    return doc


def reject(session, client, doc: Document) -> Document:
    for link in doc.links:
        link.active = False
    doc.state = DocState.REJECTED
    doc.resolved_by, doc.resolved_at = Actor.ACCOUNTANT, _now()
    _log(session, client, Actor.ACCOUNTANT, "reviewed_reject", doc)
    session.commit()
    return doc


def reassign(session, client, doc: Document, person_name: str | None = None,
             tax_year: int | None = None) -> Document:
    """Correct the tool's guess, then re-run the intake gates."""
    if person_name is not None:
        person = resolve_person(client, person_name)
        doc.guess_person_id = person.id if person else None
        doc.guess_person_name = person_name
    if tax_year is not None:
        doc.guess_year = tax_year
    for link in doc.links:
        link.active = False
    doc.exception_reason = None
    _log(session, client, Actor.ACCOUNTANT, "reassigned", doc)
    _route(session, client, doc, human_reviewed=True)
    session.commit()
    return doc


def add_requirement(session, client, doc_type: DocType, person_id=None, tax_year=None,
                    slot_index=0, note: str | None = None) -> Requirement:
    """Accountant adds a requirement the system never anticipated (origin=HUMAN)."""
    from app.models import make_natural_key
    key = make_natural_key(person_id, doc_type, tax_year, slot_index)
    req = Requirement(client_id=client.id, person_id=person_id, doc_type=doc_type,
                      tax_year=tax_year, slot_index=slot_index, natural_key=key,
                      origin=Origin.HUMAN, system_required=False, note=note)
    session.add(req)
    session.add(Event(client_id=client.id, actor=Actor.ACCOUNTANT, verb="added",
                      payload_json={"doc_type": doc_type.value, "note": note}))
    session.commit()
    return req
