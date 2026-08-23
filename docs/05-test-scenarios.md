# 05 — Test Scenarios (End-to-End)

These are the scenarios the system must get right, written so each maps to concrete tests.
"Cover the logic that matters" = derivation, reconciliation, matching, status, plus the
awkward-document cases. All are runnable **without a browser** except the three route tests
at the end.

Legend: **G** = given, **W** = when, **T** = then.

## A. Derivation

**A1 — Baseline counts (the worked example).**
G: Rivera TY2025; Ana 2 employers, Luis 1 employer (Jan state).
W: derive.
T: requirements = {1040/2024 (household), ID/Ana, ID/Luis, W2#0/Ana, W2#1/Ana, W2#0/Luis}.
Mateo (dependent) gets **no** ID and **no** W-2. Exactly **one** 1040.

**A2 — Mid-year job change adds exactly one W-2.**
G: A1 state.
W: add `employment(Luis, 2025, source=late_disclosure)`; derive.
T: Luis now has W2#0 and W2#1; nothing else changed; count delta = +1.

**A3 — Dependent with a job.**
G: Mateo has 1 employer in 2025.
T: Mateo gets W2#0 but still no ID (role rule independent of employment).

## B. Reconciliation (the crux — four invariants)

**B1 — Idempotent.** G: derived once & stored. W: derive+reconcile again, same facts.
T: zero inserts, zero status changes; `run.summary` all-zero.

**B2 — Waiver survives re-derivation.**
G: accountant marks `ID/Luis` as **not needed** (`human_override=waived`) in February.
W: March re-derivation (still wants ID/Luis).
T: `system_required=True` **and** `human_override=waived` preserved ⇒ effective status stays
`not_needed`. *(This is the headline test — the two-months-of-edits protection.)*

**B3 — Human-added requirement is never clobbered.**
G: accountant adds a `human` requirement "prior-year state return".
W: any number of re-derivations.
T: the row persists untouched (`origin=human`).

**B4 — System drops a requirement it once wanted.**
G: an employer disclosure is retracted (employment row removed) so W2#1/Ana is no longer
derived; but a document was already matched to it.
W: re-derive.
T: row kept, `system_required=False`, link preserved, effective status `received`; it leaves
the default outstanding view but the collected doc is not lost.

**B5 — Removed-then-rederived stays removed.**
G: accountant `removed` a wrongly-derived system requirement.
W: re-derivation still derives that key.
T: it does **not** resurrect into the active list (`human_override=removed` wins).

## C. Classification & matching (real fixture files, content-based)

Person/type/year come from the document **content** (AcroForm fields or text layer), not the
filename. Filenames below are just how the fixtures are stored.

**C1 — Clean digital W-2 auto-matches from form fields.** G: `w2_ana_emp1_2025.pdf` filled
with Box e = "Ana Rivera", year 2025. T: `source=form_fields`, type=W2, year=2025, person=Ana,
confidence≥0.9, state=`matched`, fills Ana W2#0; requirement→`received`.

**C2 — Two W-2s fill two slots in arrival order.** G: Ana W2#0 open, W2#1 open; two fixtures
whose Box e both read "Ana Rivera" but different employers (Box c).
W: upload one then the other.
T: slot#0 then slot#1 filled; matched by extracted **person**, so no cross-assignment to Luis.

**C3 — Flattened form with partial extraction goes to review.**
G: `w2_flat_partial.pdf` — flattened (text layer) W-2 where type+year resolve but the name
region is missing/garbled ⇒ `person_name=None`.
T: `source=text_layer`, `confidence < 0.60` ⇒ `needs_review`; **no** requirement auto-filled
until a human accepts. (Filename is *not* used to rescue it.)

**C4 — Wrong year (from the form's printed year).** G: `w2_ana_2023.pdf` built on the TY2023
template, client TY2025.
T: extracted year=2023 ≠ 2025 ⇒ `exception: wrong_year`; not matched; in attention queue.

**C5 — Unknown person (from Box e content).** G: `w2_carlos_2025.pdf` filled with Box e =
"Carlos Mendez"; no Carlos in the client.
T: extracted person matches nobody ⇒ `guess_person_id=None` ⇒ `exception: unknown_person`.

**C6 — Unreadable scan.** G: `scan_unreadable.pdf` (a filled W-2 rasterized to an image;
0 chars, no form fields). T: `readable=False`, `exception: unreadable`, confidence≈0.05.

**C7 — Unexpected extra.** G: Ana's W2#0 and W2#1 already received.
W: upload a 3rd valid Ana 2025 W-2.
T: `exception: unexpected_extra` (no open slot) → review, not silently dropped.

**C8 — 1040 matches at household level (prior year).** G: `f1040_rivera_2024.pdf`.
T: expected 1040 year = `tax_year − 1` = 2024, so it **matches** (not wrong_year); fills the
household 1040 requirement (person=None). *(Guards the Finding-1 bug.)*

**C9 — Wrong-year 1040.** G: `f1040_rivera_2023.pdf` (2023 ≠ expected 2024).
T: `wrong_year` exception.

## D. Review-queue resolution (human actions)

**D1 — Accept a needs_review doc onto a slot.** G: C3's doc in review.
W: accountant assigns it to Luis W2#1.
T: state→`matched`, link created `by=human`, requirement→`received`, `event` logged.

**D2 — Reassign a wrong guess.** G: doc guessed Ana but is really Luis's.
W: reassign person=Luis.
T: re-runs slot-finding for Luis; matches or re-queues; event logged.

**D3 — Reject junk.** G: `w2_carlos_2025.pdf` (from C5). W: reject. T: state=`rejected`, no
link, out of the active queue, still in audit.

**D4 — Add-and-match the unanticipated.** G: a doc for a requirement the system never made.
W: accountant adds a `human` requirement and matches. T: requirement `origin=human`,
`received`; survives future re-derivation (ties to B3).

## E. Status rollup

**E1 — Header counts.** After the full Rivera flow: received/outstanding/not_needed counts
match the sum of per-requirement effective statuses; obsolete rows excluded from the default
view.

**E2 — Attention queue contents.** Queue = all `needs_review` + `exception` docs ∪ `pinned`
outstanding requirements; nothing auto-matched appears there.

## F. Route/UI smoke (browser-touching, minimal)

**F1** `GET /client/<id>` renders three sections (received / outstanding / attention) with
correct counts. **F2** `POST /client/<id>/documents` (upload) runs ingestion and redirects
with the new doc in the right bucket. **F3** `POST /documents/<id>/review` (accept) moves the
doc to `matched` and updates the requirement.

## Fixture manifest (drives the tests above)

Fixtures are **generated**, not scavenged: `scripts/fetch_samples.py` downloads the official
IRS templates (correct vintages, incl. prior-year) and `scripts/build_fixtures.py` fills them
with the Rivera scenario data and produces the awkward variants — filled-digital (form
fields), flattened (text layer), wrong-year, unknown-person, and a rasterized unreadable scan.
Output lands in `tests/fixtures/`, so the whole suite reproduces from a clean checkout. See
[02 §1](02-data-and-classifier.md).
