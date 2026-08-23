"""M2: derivation counts are right (docs/05 A1–A3). Pure logic — no browser, no reconciliation."""
from collections import Counter

from app.domain.derivation import derive
from app.models import DocType, EmploymentSource, Employment, Role
from scripts.seed import seed_rivera


def _by_role(client):
    return {p.role: p for p in client.people}


def test_a1_baseline_counts(session):
    """Rivera January state: 1040 + 2 IDs + 3 W-2s (Ana 2, Luis 1); Mateo gets nothing."""
    client = seed_rivera(session)
    reqs = derive(client)

    kinds = Counter(r.doc_type for r in reqs)
    assert kinds[DocType.F1040] == 1
    assert kinds[DocType.ID] == 2       # Ana + Luis only
    assert kinds[DocType.W2] == 3       # Ana 2 + Luis 1

    household_1040 = next(r for r in reqs if r.doc_type is DocType.F1040)
    assert household_1040.person_id is None
    assert household_1040.tax_year == 2024          # tax_year - 1

    people = _by_role(client)
    mateo = people[Role.DEPENDENT]
    assert not any(r.person_id == mateo.id for r in reqs)   # dependent: no ID, no W-2

    ana = people[Role.TAXPAYER]
    ana_slots = sorted(r.slot_index for r in reqs
                       if r.doc_type is DocType.W2 and r.person_id == ana.id)
    assert ana_slots == [0, 1]


def test_a2_midyear_job_change_adds_exactly_one_w2(session):
    """The headline test: Luis's June change surfaces → +1 W-2, nothing else moves."""
    client = seed_rivera(session)
    before = derive(client)

    luis = _by_role(client)[Role.SPOUSE]
    luis.employments.append(Employment(tax_year=2025, employer_name="Initech",
                                        source=EmploymentSource.LATE_DISCLOSURE))
    session.commit()
    after = derive(client)

    luis_w2 = lambda rs: [r for r in rs if r.doc_type is DocType.W2 and r.person_id == luis.id]
    assert len(luis_w2(before)) == 1
    assert len(luis_w2(after)) == 2
    assert len(after) == len(before) + 1            # exactly one new requirement overall


def test_a3_dependent_with_a_job_gets_w2_but_no_id(session):
    """Role drives the ID rule independently of employment."""
    client = seed_rivera(session)
    mateo = _by_role(client)[Role.DEPENDENT]
    mateo.employments.append(Employment(tax_year=2025, employer_name="Burger Barn",
                                         source=EmploymentSource.DISCLOSED))
    session.commit()
    reqs = derive(client)

    mateo_reqs = [r for r in reqs if r.person_id == mateo.id]
    assert len(mateo_reqs) == 1
    assert mateo_reqs[0].doc_type is DocType.W2
    assert not any(r.doc_type is DocType.ID and r.person_id == mateo.id for r in reqs)
