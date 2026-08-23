"""
Status & view-model (docs/04 §4). Effective status is COMPUTED from the layered columns +
links — never stored — so a re-derivation can never leave a stale status behind.
"""
from __future__ import annotations

from app.models import (
    DocState,
    Document,
    HumanOverride,
    Origin,
    Requirement,
)

# Effective requirement statuses
RECEIVED = "received"
OUTSTANDING = "outstanding"
NOT_NEEDED = "not_needed"
OBSOLETE = "obsolete"          # system no longer wants it and no human opinion → hidden


def _has_matched_doc(req: Requirement) -> bool:
    return any(link.active and link.document.state is DocState.MATCHED for link in req.links)


def status_of(req: Requirement) -> str:
    if (req.origin is Origin.SYSTEM and not req.system_required
            and req.human_override is HumanOverride.NONE):
        return OBSOLETE
    if req.human_override in (HumanOverride.WAIVED, HumanOverride.REMOVED):
        return NOT_NEEDED
    if _has_matched_doc(req):
        return RECEIVED
    return OUTSTANDING


def visible_requirements(session, client, include_obsolete: bool = False) -> list[Requirement]:
    reqs = session.query(Requirement).filter_by(client_id=client.id).all()
    reqs = [r for r in reqs if include_obsolete or status_of(r) != OBSOLETE]
    # Stable display order: household items first, then by person, type, slot.
    reqs.sort(key=lambda r: (r.person_id or 0, r.doc_type.value, r.slot_index))
    return reqs


def attention_documents(session, client) -> list[Document]:
    return (session.query(Document)
            .filter(Document.client_id == client.id,
                    Document.state.in_([DocState.NEEDS_REVIEW, DocState.EXCEPTION]))
            .order_by(Document.uploaded_at).all())


def client_summary(session, client) -> dict:
    counts = {RECEIVED: 0, OUTSTANDING: 0, NOT_NEEDED: 0}
    for req in visible_requirements(session, client):
        counts[status_of(req)] += 1
    counts["attention"] = len(attention_documents(session, client))
    counts["total_visible"] = counts[RECEIVED] + counts[OUTSTANDING] + counts[NOT_NEEDED]
    return counts
