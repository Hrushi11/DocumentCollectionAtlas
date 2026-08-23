"""M4: classification + matching + review actions (docs/05 C1–C9, D1–D4)."""
from pathlib import Path

from app.domain.classifier import Classification, StubClassifier, TieredExtractor
from app.domain.matching import (
    accept,
    add_requirement,
    find_open_slot,
    ingest,
    reassign,
    reject,
)
from app.domain.reconciliation import run_derivation
from app.models import DocState, DocType, ExceptionReason, Requirement, Role
from scripts.seed import seed_rivera

FIX = Path(__file__).parent / "fixtures"
EXTRACT = TieredExtractor()


def prepared(session):
    client = seed_rivera(session)
    run_derivation(session, client, "initial")
    return client


def ingest_fix(session, client, name, classifier=EXTRACT):
    return ingest(session, client, str(FIX / name), name, classifier)


def person(client, role):
    return next(p for p in client.people if p.role is role)


# --------------------------------------------------------------- classification & matching
def test_c1_clean_w2_auto_matches_from_form_fields(session):
    client = prepared(session)
    doc = ingest_fix(session, client, "w2_ana_emp1_2025.pdf")
    assert doc.state is DocState.MATCHED
    assert doc.guess_type is DocType.W2 and doc.guess_year == 2025
    assert doc.extraction_source.value == "form_fields"
    ana = person(client, Role.TAXPAYER)
    assert doc.guess_person_id == ana.id
    assert doc.confidence >= 0.9


def test_c2_two_w2s_fill_two_slots_in_arrival_order(session):
    client = prepared(session)
    d1 = ingest_fix(session, client, "w2_ana_emp1_2025.pdf")
    d2 = ingest_fix(session, client, "w2_ana_emp2_2025.pdf")
    assert d1.state is d2.state is DocState.MATCHED
    ana = person(client, Role.TAXPAYER)
    filled_slots = sorted(
        link.requirement.slot_index
        for doc in (d1, d2) for link in doc.links if link.active
    )
    assert filled_slots == [0, 1]
    # nothing cross-assigned to Luis
    assert all(link.requirement.person_id == ana.id for doc in (d1, d2) for link in doc.links)


def test_c3_low_confidence_goes_to_review_not_matched(session):
    client = prepared(session)
    stub = StubClassifier(Classification(DocType.W2, 2025, "Ana Rivera", confidence=0.4,
                                         source="text_layer"))
    doc = ingest(session, client, "x.pdf", "x.pdf", stub)
    assert doc.state is DocState.NEEDS_REVIEW
    assert not any(link.active for link in doc.links)


def test_c4_wrong_year_w2(session):
    client = prepared(session)
    doc = ingest_fix(session, client, "w2_ana_2023.pdf")
    assert doc.state is DocState.EXCEPTION
    assert doc.exception_reason is ExceptionReason.WRONG_YEAR


def test_c5_unknown_person(session):
    client = prepared(session)
    doc = ingest_fix(session, client, "w2_carlos_2025.pdf")
    assert doc.state is DocState.EXCEPTION
    assert doc.exception_reason is ExceptionReason.UNKNOWN_PERSON


def test_c6_unreadable_scan(session):
    client = prepared(session)
    doc = ingest_fix(session, client, "scan_unreadable.pdf")
    assert doc.readable is False
    assert doc.state is DocState.EXCEPTION
    assert doc.exception_reason is ExceptionReason.UNREADABLE


def test_c7_unexpected_extra(session):
    client = prepared(session)
    ingest_fix(session, client, "w2_ana_emp1_2025.pdf")
    ingest_fix(session, client, "w2_ana_emp2_2025.pdf")   # both Ana slots now filled
    stub = StubClassifier(Classification(DocType.W2, 2025, "Ana Rivera", employer_name="Acme",
                                         confidence=0.95, source="form_fields"))
    doc = ingest(session, client, "x.pdf", "x.pdf", stub)   # a 3rd Ana W-2
    assert doc.state is DocState.EXCEPTION
    assert doc.exception_reason is ExceptionReason.UNEXPECTED_EXTRA


def test_c8_prior_year_1040_matches(session):
    client = prepared(session)
    doc = ingest_fix(session, client, "f1040_rivera_2024.pdf")
    assert doc.guess_type is DocType.F1040 and doc.guess_year == 2024
    assert doc.state is DocState.MATCHED           # 2024 == tax_year-1, NOT wrong_year


def test_c9_wrong_year_1040(session):
    client = prepared(session)
    doc = ingest_fix(session, client, "f1040_rivera_2023.pdf")
    assert doc.state is DocState.EXCEPTION
    assert doc.exception_reason is ExceptionReason.WRONG_YEAR


def test_c_textlayer_adp_sample_is_wrong_year(session):
    """The real ADP earnings summary: tier-2 text extraction, 2018 → wrong year."""
    client = prepared(session)
    doc = ingest_fix(session, client, "w2_textlayer_adp_tara_2018.pdf")
    assert doc.extraction_source.value == "text_layer"
    assert doc.guess_type is DocType.W2 and doc.guess_year == 2018
    assert doc.state is DocState.EXCEPTION and doc.exception_reason is ExceptionReason.WRONG_YEAR


# --------------------------------------------------------------- review-queue actions
def test_d1_accept_needs_review_onto_slot(session):
    client = prepared(session)
    luis = person(client, Role.SPOUSE)
    stub = StubClassifier(Classification(DocType.W2, 2025, "Luis Rivera", confidence=0.4,
                                         source="text_layer"))
    doc = ingest(session, client, "x.pdf", "x.pdf", stub)
    assert doc.state is DocState.NEEDS_REVIEW
    slot = find_open_slot(session, client, DocType.W2, luis.id, 2025)
    accept(session, client, doc, slot)
    assert doc.state is DocState.MATCHED
    assert any(link.active and link.requirement.person_id == luis.id for link in doc.links)


def test_d2_reassign_corrects_person(session):
    client = prepared(session)
    stub = StubClassifier(Classification(DocType.W2, 2025, "Ana Rivera", confidence=0.4,
                                         source="text_layer"))
    doc = ingest(session, client, "x.pdf", "x.pdf", stub)          # parked in review
    reassign(session, client, doc, person_name="Luis Rivera")
    luis = person(client, Role.SPOUSE)
    assert doc.state is DocState.MATCHED
    assert any(link.active and link.requirement.person_id == luis.id for link in doc.links)


def test_d3_reject_junk(session):
    client = prepared(session)
    doc = ingest_fix(session, client, "w2_carlos_2025.pdf")        # unknown person
    reject(session, client, doc)
    assert doc.state is DocState.REJECTED
    assert not any(link.active for link in doc.links)


def test_d4_add_requirement_then_match(session):
    client = prepared(session)
    # A document for something the system never derived (e.g. a state return).
    stub = StubClassifier(Classification(DocType.F1040, 2024, "Ana Rivera", confidence=0.9,
                                         source="form_fields"))
    doc = ingest(session, client, "x.pdf", "x.pdf", stub)          # matches the real 1040 slot
    # Now the human adds a brand-new requirement and points a fresh doc at it.
    req = add_requirement(session, client, DocType.F1040, tax_year=2024, slot_index=99,
                          note="prior-year state return")
    doc2 = ingest(session, client, "y.pdf", "y.pdf", stub)
    accept(session, client, doc2, req)
    assert doc2.state is DocState.MATCHED
    assert req.origin.value == "human"
    assert any(link.active and link.requirement_id == req.id for link in doc2.links)
