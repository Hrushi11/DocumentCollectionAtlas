"""
Derivation — the pure function that turns client facts into the *desired* requirement set
(docs/04 §1). No DB writes: it returns lightweight `DerivedRequirement` tuples that
reconciliation (M3) merges into stored `Requirement` rows.

Rules:
  - one household prior-year 1040  (tax_year - 1)
  - one government ID per filing adult (taxpayer + spouse; dependents don't file)
  - one W-2 per distinct employer a person worked for during the tax year
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from app.models import DocType, Person, Role, make_natural_key

FILING_ADULTS = {Role.TAXPAYER, Role.SPOUSE}


@dataclass(frozen=True)
class DerivedRequirement:
    person_id: Optional[int]      # None = household-level (the single 1040)
    doc_type: DocType
    tax_year: Optional[int]       # None = not year-scoped (gov ID)
    slot_index: int = 0

    @property
    def natural_key(self) -> str:
        return make_natural_key(self.person_id, self.doc_type, self.tax_year, self.slot_index)


def w2_employers(person: Person, tax_year: int) -> list:
    """Distinct employers a person worked for during `tax_year`, in disclosure order.

    A mid-year job change is simply a second employment row → a second employer → a second
    W-2. Named employers are de-duplicated; unknown-name stints each count (docs/04 §1)."""
    emps = [e for e in person.employments if e.tax_year == tax_year]
    emps.sort(key=lambda e: (e.disclosed_at or datetime.min.replace(tzinfo=timezone.utc),
                             e.id or 0))
    out, seen = [], set()
    for e in emps:
        if e.employer_name and e.employer_name in seen:
            continue
        if e.employer_name:
            seen.add(e.employer_name)
        out.append(e)
    return out


def derive(client) -> list[DerivedRequirement]:
    """Pure: client facts → desired requirements. Idempotent; safe to call repeatedly."""
    reqs: list[DerivedRequirement] = []

    # (a) household prior-year 1040
    reqs.append(DerivedRequirement(None, DocType.F1040, client.tax_year - 1, 0))

    # (b) government ID per filing adult
    for person in client.people:
        if person.role in FILING_ADULTS:
            reqs.append(DerivedRequirement(person.id, DocType.ID, None, 0))

    # (c) one W-2 per distinct employer per person, for the tax year
    for person in client.people:
        for slot, _employer in enumerate(w2_employers(person, client.tax_year)):
            reqs.append(DerivedRequirement(person.id, DocType.W2, client.tax_year, slot))

    return reqs
