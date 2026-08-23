"""
SQLAlchemy models — the schema from docs/03. No Flask imports (domain/tests use these directly).

Design spine (docs/01 §3): **Requirements** (the derived + human-edited checklist) and
**Documents** (files that arrive) are separate lifecycles joined only by RequirementDocument.
Effective status is NOT stored — it is computed (docs/04 §4) from origin / system_required /
human_override / links.
"""
from __future__ import annotations

import enum
import hashlib
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    JSON,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------- enums
class FilingStatus(enum.Enum):
    SINGLE = "single"
    MARRIED_JOINT = "married_joint"
    MARRIED_SEPARATE = "married_separate"
    HEAD_OF_HOUSEHOLD = "head_of_household"


class Role(enum.Enum):
    TAXPAYER = "taxpayer"
    SPOUSE = "spouse"
    DEPENDENT = "dependent"


class DocType(enum.Enum):
    W2 = "W2"
    F1040 = "1040"
    ID = "ID"


class EmploymentSource(enum.Enum):
    PRIOR_YEAR = "prior_year"        # carried baseline from last year's filing
    DISCLOSED = "disclosed"          # told to us up front this year
    LATE_DISCLOSURE = "late_disclosure"  # the "surfaced in March" case


class Origin(enum.Enum):
    SYSTEM = "system"
    HUMAN = "human"


class HumanOverride(enum.Enum):
    NONE = "none"
    WAIVED = "waived"        # "not needed"
    REMOVED = "removed"      # human deleted a system item (tombstone)
    PINNED = "pinned"        # human insists it is needed


class ExtractionSource(enum.Enum):
    FORM_FIELDS = "form_fields"
    TEXT_LAYER = "text_layer"
    OCR = "ocr"
    FILENAME = "filename"


class DocState(enum.Enum):
    MATCHED = "matched"
    NEEDS_REVIEW = "needs_review"
    EXCEPTION = "exception"
    REJECTED = "rejected"


class ExceptionReason(enum.Enum):
    UNREADABLE = "unreadable"
    WRONG_YEAR = "wrong_year"
    UNKNOWN_PERSON = "unknown_person"
    UNEXPECTED_EXTRA = "unexpected_extra"


class Actor(enum.Enum):
    SYSTEM = "system"
    ACCOUNTANT = "accountant"


# --------------------------------------------------------------------------- helpers
def make_natural_key(person_id: Optional[int], doc_type: DocType,
                     tax_year: Optional[int], slot_index: int) -> str:
    """Stable identity for a requirement so re-derivation re-finds it (docs/03, docs/04 §2)."""
    raw = f"{person_id or 0}|{doc_type.value}|{tax_year or 0}|{slot_index}"
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


# --------------------------------------------------------------------------- tables
class Client(Base):
    __tablename__ = "client"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    tax_year: Mapped[int]
    filing_status: Mapped[FilingStatus] = mapped_column(Enum(FilingStatus))
    created_at: Mapped[datetime] = mapped_column(default=_now)

    people: Mapped[list["Person"]] = relationship(back_populates="client",
                                                  cascade="all, delete-orphan")
    requirements: Mapped[list["Requirement"]] = relationship(back_populates="client",
                                                            cascade="all, delete-orphan")
    documents: Mapped[list["Document"]] = relationship(back_populates="client",
                                                      cascade="all, delete-orphan")
    runs: Mapped[list["DerivationRun"]] = relationship(back_populates="client",
                                                      cascade="all, delete-orphan")
    events: Mapped[list["Event"]] = relationship(back_populates="client",
                                                cascade="all, delete-orphan")


class Person(Base):
    __tablename__ = "person"

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("client.id"))
    name: Mapped[str] = mapped_column(String(200))
    role: Mapped[Role] = mapped_column(Enum(Role))

    client: Mapped["Client"] = relationship(back_populates="people")
    employments: Mapped[list["Employment"]] = relationship(back_populates="person",
                                                          cascade="all, delete-orphan")


class Employment(Base):
    """A person working for one employer during a tax year — the input to W-2 derivation."""
    __tablename__ = "employment"
    __table_args__ = (Index("ix_employment_person_year", "person_id", "tax_year"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("person.id"))
    tax_year: Mapped[int]
    employer_name: Mapped[Optional[str]] = mapped_column(String(200), default=None)
    ended_midyear: Mapped[bool] = mapped_column(default=False)
    source: Mapped[EmploymentSource] = mapped_column(Enum(EmploymentSource))
    disclosed_at: Mapped[datetime] = mapped_column(default=_now)

    person: Mapped["Person"] = relationship(back_populates="employments")


class DerivationRun(Base):
    __tablename__ = "derivation_run"

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("client.id"))
    created_at: Mapped[datetime] = mapped_column(default=_now)
    reason: Mapped[str] = mapped_column(String(200), default="")
    summary_json: Mapped[dict] = mapped_column(JSON, default=dict)

    client: Mapped["Client"] = relationship(back_populates="runs")


class Requirement(Base):
    """The checklist item. Layered state (origin / system_required / human_override) is what
    makes re-derivation non-destructive — see docs/04 §2. Effective status is computed."""
    __tablename__ = "requirement"
    __table_args__ = (
        UniqueConstraint("client_id", "natural_key", name="uq_requirement_client_natkey"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("client.id"))
    person_id: Mapped[Optional[int]] = mapped_column(ForeignKey("person.id"), default=None)
    doc_type: Mapped[DocType] = mapped_column(Enum(DocType))
    tax_year: Mapped[Optional[int]] = mapped_column(default=None)
    slot_index: Mapped[int] = mapped_column(default=0)
    natural_key: Mapped[str] = mapped_column(String(32))

    origin: Mapped[Origin] = mapped_column(Enum(Origin), default=Origin.SYSTEM)
    system_required: Mapped[bool] = mapped_column(default=True)
    human_override: Mapped[HumanOverride] = mapped_column(Enum(HumanOverride),
                                                         default=HumanOverride.NONE)
    note: Mapped[Optional[str]] = mapped_column(String(500), default=None)
    created_by_run_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("derivation_run.id"), default=None)
    created_at: Mapped[datetime] = mapped_column(default=_now)
    updated_at: Mapped[datetime] = mapped_column(default=_now, onupdate=_now)

    client: Mapped["Client"] = relationship(back_populates="requirements")
    person: Mapped[Optional["Person"]] = relationship()
    links: Mapped[list["RequirementDocument"]] = relationship(
        back_populates="requirement", cascade="all, delete-orphan")


class Document(Base):
    """A file that arrived + the classifier's guess + a state."""
    __tablename__ = "document"
    __table_args__ = (Index("ix_document_client_state", "client_id", "state"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("client.id"))
    original_filename: Mapped[str] = mapped_column(String(300))
    stored_path: Mapped[str] = mapped_column(String(500))
    uploaded_at: Mapped[datetime] = mapped_column(default=_now)

    guess_type: Mapped[Optional[DocType]] = mapped_column(Enum(DocType), default=None)
    guess_year: Mapped[Optional[int]] = mapped_column(default=None)
    guess_person_id: Mapped[Optional[int]] = mapped_column(ForeignKey("person.id"),
                                                          default=None)
    guess_person_name: Mapped[Optional[str]] = mapped_column(String(200), default=None)
    extracted_employer: Mapped[Optional[str]] = mapped_column(String(200), default=None)
    extracted_wages: Mapped[Optional[float]] = mapped_column(Numeric(12, 2), default=None)
    extraction_source: Mapped[Optional[ExtractionSource]] = mapped_column(
        Enum(ExtractionSource), default=None)

    confidence: Mapped[float] = mapped_column(default=0.0)
    readable: Mapped[bool] = mapped_column(default=True)
    signals_json: Mapped[dict] = mapped_column(JSON, default=dict)

    state: Mapped[DocState] = mapped_column(Enum(DocState), default=DocState.NEEDS_REVIEW)
    exception_reason: Mapped[Optional[ExceptionReason]] = mapped_column(
        Enum(ExceptionReason), default=None)
    resolved_by: Mapped[Optional[Actor]] = mapped_column(Enum(Actor), default=None)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(default=None)

    client: Mapped["Client"] = relationship(back_populates="documents")
    links: Mapped[list["RequirementDocument"]] = relationship(
        back_populates="document", cascade="all, delete-orphan")


class RequirementDocument(Base):
    """Link: a document fulfills a requirement. Join table keeps the two lifecycles separate
    and lets a human re-point a mis-matched doc while preserving history (docs/03)."""
    __tablename__ = "requirement_document"

    id: Mapped[int] = mapped_column(primary_key=True)
    requirement_id: Mapped[int] = mapped_column(ForeignKey("requirement.id"))
    document_id: Mapped[int] = mapped_column(ForeignKey("document.id"))
    linked_by: Mapped[Origin] = mapped_column(Enum(Origin), default=Origin.SYSTEM)
    linked_at: Mapped[datetime] = mapped_column(default=_now)
    active: Mapped[bool] = mapped_column(default=True)  # False = superseded link (audit)

    requirement: Mapped["Requirement"] = relationship(back_populates="links")
    document: Mapped["Document"] = relationship(back_populates="links")


class Event(Base):
    """Append-only audit log — the story the reviewers read (docs/03)."""
    __tablename__ = "event"

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("client.id"))
    at: Mapped[datetime] = mapped_column(default=_now)
    actor: Mapped[Actor] = mapped_column(Enum(Actor))
    verb: Mapped[str] = mapped_column(String(50))
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict)

    client: Mapped["Client"] = relationship(back_populates="events")
