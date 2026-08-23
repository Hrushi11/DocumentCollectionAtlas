"""M1: schema stands up — persistence, defaults, and the reconciliation-critical unique key."""
import pytest
from sqlalchemy.exc import IntegrityError

from app.models import (
    Client,
    DocType,
    FilingStatus,
    HumanOverride,
    Origin,
    Requirement,
    Role,
    make_natural_key,
)
from scripts.seed import seed_rivera


def test_seed_creates_rivera_january_state(session):
    client = seed_rivera(session)
    assert client.filing_status is FilingStatus.MARRIED_JOINT
    assert client.tax_year == 2025

    by_role = {p.role: p for p in client.people}
    assert set(by_role) == {Role.TAXPAYER, Role.SPOUSE, Role.DEPENDENT}
    # Baseline employment: Ana 2 jobs, Luis 1 (June change not yet known), Mateo none.
    assert len(by_role[Role.TAXPAYER].employments) == 2
    assert len(by_role[Role.SPOUSE].employments) == 1
    assert len(by_role[Role.DEPENDENT].employments) == 0


def test_requirement_defaults(session):
    client = Client(name="X", tax_year=2025, filing_status=FilingStatus.SINGLE)
    session.add(client)
    session.flush()
    req = Requirement(client_id=client.id, doc_type=DocType.F1040, tax_year=2024,
                      natural_key=make_natural_key(None, DocType.F1040, 2024, 0))
    session.add(req)
    session.commit()
    assert req.origin is Origin.SYSTEM
    assert req.system_required is True
    assert req.human_override is HumanOverride.NONE


def test_natural_key_unique_per_client(session):
    """Idempotent re-derivation depends on this uniqueness (docs/04 §2)."""
    client = Client(name="X", tax_year=2025, filing_status=FilingStatus.SINGLE)
    session.add(client)
    session.flush()
    key = make_natural_key(None, DocType.F1040, 2024, 0)
    session.add(Requirement(client_id=client.id, doc_type=DocType.F1040,
                            tax_year=2024, natural_key=key))
    session.commit()
    session.add(Requirement(client_id=client.id, doc_type=DocType.F1040,
                            tax_year=2024, natural_key=key))
    with pytest.raises(IntegrityError):
        session.commit()


def test_make_natural_key_is_stable_and_distinct():
    a = make_natural_key(1, DocType.W2, 2025, 0)
    assert a == make_natural_key(1, DocType.W2, 2025, 0)          # stable
    assert a != make_natural_key(1, DocType.W2, 2025, 1)          # slot matters
    assert a != make_natural_key(2, DocType.W2, 2025, 0)          # person matters
