# 04 — Core Algorithms

This is "the logic that matters." All four are testable with no browser.

## 1. Derivation — `derive(client) -> list[DerivedRequirement]`

Pure function of the client's facts (people, roles, employment rows). Returns *desired*
requirements as `(person, doc_type, tax_year, slot_index)` tuples — no DB writes.

```
def derive(client):
    reqs = []
    # (a) Household return: one prior-year 1040
    reqs.append(D(person=None, type="1040", year=client.tax_year - 1, slot=0))

    # (b) Government ID: one per filing adult
    for p in client.people:
        if p.role in ("taxpayer", "spouse"):
            reqs.append(D(person=p, type="ID", year=None, slot=0))

    # (c) W-2s: one per distinct employer worked during the tax year
    for p in client.people:
        employers = distinct_employers(p, client.tax_year)   # counts prior+disclosed+late
        for i in range(len(employers)):
            reqs.append(D(person=p, type="W2", year=client.tax_year, slot=i))
    return reqs
```

Worked example (Rivera, TY2025):

| Stage | Ana | Luis | Household |
|-------|-----|------|-----------|
| **Jan** (job change unknown) | ID, W2#0, W2#1 | ID, W2#0 | 1040(2024) |
| **March** (Luis's June change disclosed) | ID, W2#0, W2#1 | ID, W2#0, **W2#1** | 1040(2024) |

The only change March produces is **one new requirement** for Luis (`W2 slot#1`). Everything
else must be left exactly as the accountant left it — that's reconciliation's job.

**Why slots, not employer names:** we usually don't know employer identities up front. A slot
is a stable ordinal obligation ("Luis's 2nd W-2") that a document fills on arrival. If/when
employer names are known they annotate the slot; they don't gate matching.

## 2. Reconciliation — merge new derivation into the stored list (the crux)

Three-way merge. Inputs: `derived` (new desired set) and `existing` (rows in DB, carrying
human overrides). Keyed by `natural_key`.

```
def reconcile(client, derived, run):
    derived_by_key = {r.natural_key: r for r in derived}
    existing_by_key = {r.natural_key: r for r in client.requirements}

    # 1. New system obligations
    for key, d in derived_by_key.items():
        if key not in existing_by_key:
            insert Requirement(origin="system", system_required=True,
                               human_override="none", created_by_run_id=run.id, **d)
        else:
            existing_by_key[key].system_required = True    # re-affirm; DO NOT touch override

    # 2. Obligations the system no longer wants
    for key, r in existing_by_key.items():
        if r.origin == "system" and key not in derived_by_key:
            r.system_required = False        # deactivate, NEVER delete
            # human_override, links, note all preserved

    # 3. Human-added requirements (origin="human") are outside derivation entirely — untouched
    run.summary = diff_counts(...)
```

**The four invariants reconciliation guarantees** (each has a test in [05](05-test-scenarios.md)):

1. **Idempotent** — re-running with unchanged facts changes nothing (`unique(natural_key)`).
2. **Waivers survive** — a `waived`/`removed` system requirement stays waived/removed across
   re-derivation; the system flips `system_required`, never `human_override`.
3. **Human additions survive** — `origin=human` rows are never deleted or altered.
4. **Fulfilled-then-dropped is safe** — if the system stops wanting a requirement that already
   has a matched document, we deactivate but keep the row and its link (the document still
   exists and the accountant can see it was collected).

**Why deactivate instead of delete:** deletion loses the human's decisions, the collected
document, and the audit trail. A `system_required=False` row is invisible in the default view
but recoverable and explains history.

## 3. Ingestion & Matching — from uploaded file to a decision

Runs synchronously when a document is added.

```
def ingest(client, file):
    g = classifier.classify(file.path, file.original_filename)
    doc = Document(client, guess=g, confidence=g.confidence, readable=g.readable)

    # --- gate 1: readable? ---
    if not g.readable:
        return doc.exception("unreadable")

    # --- gate 2: confident enough? ---
    if g.confidence < LOW_CONFIDENCE:            # e.g. 0.60
        return doc.needs_review()                # human decides; never auto-acted on

    # --- gate 3: is it even for this engagement? ---
    exp = expected_year(g.doc_type, client)      # W2 -> tax_year; 1040 -> tax_year - 1; ID -> None
    if exp is not None and g.tax_year and g.tax_year != exp:
        return doc.exception("wrong_year")
    if g.guess_person_id is None and g.doc_type != "1040":
        return doc.exception("unknown_person")   # name extracted from Box e matches no client person

    # --- gate 4: find an open slot ---
    slot = find_open_slot(client, g.doc_type, g.guess_person_id, g.tax_year)
    if slot is None:
        return doc.exception("unexpected_extra")   # more W-2s than expected, or already filled

    link(slot, doc, by="system"); return doc.matched()
```

**`expected_year(doc_type, client)` — the per-type year rule (do not compare against
`client.tax_year` blindly):**

| doc_type | expected year | why |
|----------|---------------|-----|
| `W2` | `client.tax_year` | wages are for the filing year |
| `1040` | `client.tax_year - 1` | the required 1040 is *last year's* completed return |
| `ID` | `None` (not year-scoped) | a government ID has no tax year |

So for a TY2025 engagement a **2024** 1040 is correct (not `wrong_year`), a **2025** W-2 is
correct, and a 2023 W-2 or 2023 1040 is `wrong_year`.

`find_open_slot`: among that person's active requirements of this `(type, year)` with no
active link, pick the lowest free `slot_index`. Fill in **arrival order** (§2.1 independence:
one spouse's W-2 tells you nothing about the other's, so we never cross-assign between people).

**Review actions** (human resolves a `needs_review`/`exception` doc): `accept → match to a
chosen slot`, `reassign person/year`, `reject` (wrong person/junk), or `add requirement then
match` (the "system didn't anticipate it" case). Every action writes an `event`.

### 3.1 Confidence thresholds (single source of truth)

| Constant | Value | Meaning |
|----------|-------|---------|
| `MIN_CHARS` | 20 | below ⇒ unreadable |
| `LOW_CONFIDENCE` | 0.60 | below ⇒ needs_review, never auto-match |
| `AUTO_MATCH` | 0.60+ | at/above, and passes gates ⇒ auto-match |

Tuned against the fixture set so clean files auto-match and every awkward file is caught.

## 4. Status computation — the numbers on the screen

Per-requirement **effective status** (pure function, no stored column):

```
def status_of(req):
    if req.origin == "system" and not req.system_required
       and req.human_override == "none":          return "obsolete"      # hidden by default
    if req.human_override in ("waived", "removed"):return "not_needed"
    if has_active_matched_document(req):           return "received"
    if has_document_in_review_for(req):            return "pending_review"
    return "outstanding"
```

Per-client rollup for the header: counts of `received / outstanding / not_needed`, plus the
**attention queue** = documents in `needs_review` or `exception` **∪** requirements a human
`pinned` but that are still outstanding. That queue is the "needs your attention" column and
the thing the demo video centers on.
