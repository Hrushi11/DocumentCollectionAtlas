"""M5: effective status + rollup are internally consistent (docs/05 E1–E2)."""
from pathlib import Path

from app.domain.matching import ingest
from app.domain.reconciliation import run_derivation
from app.domain.status import (
    NOT_NEEDED,
    RECEIVED,
    attention_documents,
    client_summary,
    status_of,
    visible_requirements,
)
from app.models import DocState, DocType, HumanOverride, Role
from scripts.seed import seed_rivera
from tests.test_matching import EXTRACT, FIX


def _ingest(session, client, name):
    return ingest(session, client, str(FIX / name), name, EXTRACT)


def _find_id_req(session, client, role):
    person = next(p for p in client.people if p.role is role)
    return next(r for r in visible_requirements(session, client, include_obsolete=True)
                if r.doc_type is DocType.ID and r.person_id == person.id)


def test_e1_rollup_matches_per_requirement_statuses(session):
    client = seed_rivera(session)
    run_derivation(session, client, "initial")

    _ingest(session, client, "w2_ana_emp1_2025.pdf")     # → Ana W-2 #0 received
    _ingest(session, client, "f1040_rivera_2024.pdf")    # → household 1040 received
    _find_id_req(session, client, Role.SPOUSE).human_override = HumanOverride.WAIVED
    session.commit()

    reqs = visible_requirements(session, client)
    summary = client_summary(session, client)

    assert summary[RECEIVED] == sum(1 for r in reqs if status_of(r) == RECEIVED) == 2
    assert summary[NOT_NEEDED] == sum(1 for r in reqs if status_of(r) == NOT_NEEDED) == 1
    # header counts partition the visible requirements exactly
    assert summary["total_visible"] == len(reqs)


def test_e2_attention_queue_is_review_and_exceptions_only(session):
    client = seed_rivera(session)
    run_derivation(session, client, "initial")

    _ingest(session, client, "w2_ana_emp1_2025.pdf")     # matched → NOT in attention
    _ingest(session, client, "w2_carlos_2025.pdf")       # unknown person → exception
    _ingest(session, client, "scan_unreadable.pdf")      # unreadable → exception

    queue = attention_documents(session, client)
    assert len(queue) == 2
    assert all(d.state in (DocState.NEEDS_REVIEW, DocState.EXCEPTION) for d in queue)
    assert all(d.state is not DocState.MATCHED for d in queue)
