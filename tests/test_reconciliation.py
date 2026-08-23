"""M3: reconciliation preserves human edits across re-derivation (docs/05 B1–B5) — the crux."""
from app.domain.reconciliation import run_derivation
from app.models import (
    DocType,
    EmploymentSource,
    Employment,
    HumanOverride,
    Origin,
    Requirement,
    Role,
    make_natural_key,
)
from scripts.seed import seed_rivera


def _reqs(session, client):
    return session.query(Requirement).filter_by(client_id=client.id).all()


def _find(session, client, person_id, doc_type, tax_year, slot=0):
    key = make_natural_key(person_id, doc_type, tax_year, slot)
    return session.query(Requirement).filter_by(client_id=client.id, natural_key=key).one()


def _person(client, role):
    return next(p for p in client.people if p.role is role)


def test_b1_idempotent(session):
    client = seed_rivera(session)
    run_derivation(session, client, "initial")
    count1 = len(_reqs(session, client))
    run2 = run_derivation(session, client, "again, unchanged facts")
    assert run2.summary_json["added"] == 0
    assert run2.summary_json["deactivated"] == 0
    assert len(_reqs(session, client)) == count1


def test_b2_waiver_survives_rederivation(session):
    """Headline: the accountant waives Luis's ID; a later re-derivation must not undo it."""
    client = seed_rivera(session)
    run_derivation(session, client, "initial")
    luis = _person(client, Role.SPOUSE)

    luis_id = _find(session, client, luis.id, DocType.ID, None)
    luis_id.human_override = HumanOverride.WAIVED      # "not needed"
    session.commit()

    run_derivation(session, client, "march re-derivation")   # still derives ID/Luis

    luis_id = _find(session, client, luis.id, DocType.ID, None)
    assert luis_id.system_required is True             # system still wants it
    assert luis_id.human_override is HumanOverride.WAIVED   # but the human's call stands


def test_b3_human_added_requirement_untouched(session):
    client = seed_rivera(session)
    run_derivation(session, client, "initial")
    extra = Requirement(client_id=client.id, doc_type=DocType.F1040, tax_year=2024,
                        slot_index=99, natural_key="human-state-return",
                        origin=Origin.HUMAN, system_required=False, note="prior-year state return")
    session.add(extra)
    session.commit()

    run_derivation(session, client, "re-derive")
    still = session.query(Requirement).filter_by(natural_key="human-state-return").one()
    assert still.origin is Origin.HUMAN
    assert still.note == "prior-year state return"


def test_b4_dropped_requirement_is_deactivated_not_deleted(session):
    client = seed_rivera(session)
    run_derivation(session, client, "initial")
    ana = _person(client, Role.TAXPAYER)
    slot1_key = make_natural_key(ana.id, DocType.W2, 2025, 1)

    # Ana loses her second employer → only 1 W-2 derived now.
    ana.employments.pop()
    session.commit()
    run_derivation(session, client, "employer retracted")

    slot1 = session.query(Requirement).filter_by(natural_key=slot1_key).one()  # still exists
    assert slot1.system_required is False              # deactivated, not deleted


def test_b5_removed_stays_removed(session):
    client = seed_rivera(session)
    run_derivation(session, client, "initial")
    ana = _person(client, Role.TAXPAYER)
    ana_id = _find(session, client, ana.id, DocType.ID, None)
    ana_id.human_override = HumanOverride.REMOVED
    session.commit()

    run_derivation(session, client, "re-derive still wants ID/Ana")
    ana_id = _find(session, client, ana.id, DocType.ID, None)
    assert ana_id.human_override is HumanOverride.REMOVED   # not resurrected
