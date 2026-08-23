"""
Reconciliation — the crux (docs/04 §2). Merge a fresh derivation into the stored requirement
rows as a three-way merge, **preserving every human edit**:

  base   = what was stored last time
  theirs = the new derivation
  ours   = the accountant's overrides (waive / remove / add / pin)

Invariants (guarded by tests B1–B5):
  1. Idempotent — same facts ⇒ no changes.
  2. Waivers survive — the system flips `system_required`, never `human_override`.
  3. Human-added requirements (origin=HUMAN) are never touched.
  4. Dropped-but-fulfilled requirements are deactivated, never deleted (links preserved).
  5. A human `removed` requirement is never resurrected by re-derivation.
"""
from __future__ import annotations

from app.domain.derivation import DerivedRequirement, derive
from app.models import (
    Actor,
    DerivationRun,
    Event,
    Origin,
    Requirement,
)


def reconcile(session, client, derived: list[DerivedRequirement],
              run: DerivationRun) -> dict:
    derived_by_key = {d.natural_key: d for d in derived}
    # Query fresh (don't rely on a possibly-stale relationship collection).
    existing = session.query(Requirement).filter_by(client_id=client.id).all()
    existing_by_key = {r.natural_key: r for r in existing}

    added = reactivated = deactivated = 0

    # 1 & 2 — system obligations the derivation currently wants.
    for key, d in derived_by_key.items():
        req = existing_by_key.get(key)
        if req is None:
            session.add(Requirement(
                client_id=client.id, person_id=d.person_id, doc_type=d.doc_type,
                tax_year=d.tax_year, slot_index=d.slot_index, natural_key=key,
                origin=Origin.SYSTEM, system_required=True,
                created_by_run_id=run.id))
            added += 1
        else:
            if not req.system_required:
                reactivated += 1
            req.system_required = True          # re-affirm; NEVER touch human_override

    # 3 — system obligations no longer wanted: deactivate, never delete.
    for key, req in existing_by_key.items():
        if req.origin is Origin.SYSTEM and key not in derived_by_key and req.system_required:
            req.system_required = False
            deactivated += 1
        # origin=HUMAN rows are outside derivation entirely — left untouched.

    summary = dict(derived=len(derived_by_key), added=added,
                   reactivated=reactivated, deactivated=deactivated)
    run.summary_json = summary
    return summary


def run_derivation(session, client, reason: str = "") -> DerivationRun:
    """Create a DerivationRun, derive, reconcile, log an event, commit."""
    run = DerivationRun(client_id=client.id, reason=reason)
    session.add(run)
    session.flush()                              # assign run.id for created_by_run_id
    reconcile(session, client, derive(client), run)
    session.add(Event(client_id=client.id, actor=Actor.SYSTEM,
                      verb="derived", payload_json=dict(run.summary_json, reason=reason)))
    session.commit()
    return run
