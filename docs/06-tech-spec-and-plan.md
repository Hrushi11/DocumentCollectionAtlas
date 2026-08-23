# 06 — Tech Spec & Execution Plan

## 1. Stack

- **Web:** Flask (server-rendered Jinja2 templates).
- **ORM/DB:** SQLAlchemy + SQLite (file `app.db`).
- **PDF — three distinct capabilities the design actually uses:**
  | Capability | Library | Used by |
  |------------|---------|---------|
  | **Form-field extraction** (read AcroForm `/V`) | `pypdf` | `TieredExtractor` tier 1 |
  | **Text extraction** (text layer + word coordinates) | `pdfplumber` | `TieredExtractor` tier 2 |
  | **Fixture generation** (fill AcroForm, strip XFA) | `pypdf` | `scripts/build_fixtures.py` |
  | **Rasterize/flatten** (make the unreadable-scan fixture) | `pypdfium2` | `scripts/build_fixtures.py` |
- **Tests:** `pytest`.
- **Python:** 3.14 (the venv at `./venv`; all four PDF libs already installed).

**OCR is explicitly *not* a v1 runtime dependency.** Tier 3 is a stub: image-only input
(0 chars, no fields) is routed to review as `unreadable`. `pypdfium2` is a *build-time*
fixture tool, not a runtime requirement. So the app runs on `Flask + SQLAlchemy + pypdf +
pdfplumber`; `pypdfium2` is only needed to (re)generate fixtures.

Rationale: lightweight, minimal magic, logic trivially testable headless, fast to stand up in
the time budget. (Recorded in README.)

## 2. Planned project layout — layers, with the domain logic kept out of Flask

> **Target structure — does not exist yet.** The repo is still in the specification phase;
> `app/`, `scripts/`, and `tests/` are created during the build (milestones M0–M6). Only
> `docs/`, `sampleData/`, `README.md`, and `venv/` exist today.

```
app/
  __init__.py            # Flask app factory, config, db init
  models.py              # SQLAlchemy models (schema from doc 03)
  domain/
    derivation.py        # derive(client) -> [DerivedRequirement]        (doc 04 §1)
    reconciliation.py    # reconcile(client, derived, run)               (doc 04 §2)
    matching.py          # ingest(client, file), find_open_slot          (doc 04 §3)
    status.py            # status_of(req), client_rollup(client)         (doc 04 §4)
    classifier/
      base.py            # Classification dataclass + Classifier Protocol
      extractor.py       # TieredExtractor: form_fields -> text_layer -> ocr  (doc 02 §3)
      fields_map.py      # W-2/1040 AcroForm field-name -> semantics mapping
      stub.py            # StubClassifier for deterministic tests
  services.py            # thin orchestration used by both routes and tests
  routes.py              # Flask blueprints (thin; delegate to services/domain)
  templates/             # Jinja2
  static/                # minimal CSS
scripts/
  fetch_samples.py       # download official IRS templates (correct + prior-year vintages)
  build_fixtures.py      # fill AcroForm templates w/ Rivera data -> filled/flattened/wrong-year/unknown/unreadable
  seed.py                # create the Rivera client + Jan employment state
tests/
  fixtures/              # the real document files (doc 02 §3)
  test_derivation.py test_reconciliation.py test_matching.py
  test_status.py test_routes.py
docs/                    # this spec set
README.md
requirements.txt
```

**Key principle:** `app/domain/*` has **no Flask imports**. Routes and tests call the same
service functions, satisfying "testable without a browser."

## 3. Routes (server-rendered)

| Method & path | Purpose | Delegates to |
|---------------|---------|--------------|
| `GET /` | list clients | — |
| `GET /client/<id>` | **the screen**: received / outstanding / attention + rollup | `status.client_rollup` |
| `POST /client/<id>/documents` | upload a file → ingest | `matching.ingest` |
| `POST /client/<id>/requirements` | human adds a requirement | reconciliation-aware insert |
| `POST /requirements/<id>/waive` \| `/remove` \| `/pin` | human overrides | sets `human_override`, logs event |
| `POST /documents/<id>/review` | accept / reassign / reject | `matching` review actions |
| `POST /client/<id>/rederive` | re-run derivation (the March button) | `derivation`+`reconciliation` |

`POST /client/<id>/rederive` with a form field to add the late employment row is how the demo
triggers the "job change surfaces in March" moment live.

## 4. UI — three views, plain and legible

1. **Client status screen** (`/client/<id>`): header rollup (received N · outstanding N ·
   not needed N · **needs attention N**); then a table grouped by person, each requirement row
   showing type, year, slot, effective status, and the matched filename or an "Add/Upload"
   action; obsolete rows hidden behind a "show inactive" toggle.
2. **Attention panel** (same page or `/client/<id>/attention`): each review/exception document
   with the classifier's guess, confidence, the "why" signals, and buttons Accept / Reassign /
   Reject.
3. **Add document**: a file input on the client page (multi-file allowed) that POSTs to
   ingestion and drops each file into the correct bucket.

No JS framework; a little CSS. Forms post and re-render — enough to be usable and to
demonstrate every case in the video.

## 5. Testing strategy

- **Unit (bulk):** derivation, reconciliation, matching, status — pure/DB-backed, use
  `StubClassifier` for determinism and the `TieredExtractor` against real fixtures for C-series.
- **Route smoke (few):** F-series with Flask test client.
- Scenarios in [05](05-test-scenarios.md) map 1:1 to test functions. Target: every A–E
  scenario has a test; B2 (waiver survives) and A2 (job change +1) are the must-pass ones.

## 6. Seed / demo narrative (what the video shows)

1. `scripts/fetch_samples.py` → real IRS fixtures. `scripts/seed.py` → Rivera in **January**
   state (Luis 1 job). Screen shows Luis needing 1 W-2.
2. Upload clean W-2s → auto-match. Upload the awkward files → land in attention (wrong year,
   unknown person, unreadable, low-confidence).
3. Accountant **waives** Luis's gov ID (say it's on file) and **adds** a state-return
   requirement — simulating two months of edits.
4. Click **re-derive** with Luis's June job change → **exactly one** new W-2 appears; the
   waiver and the added requirement are **still there**. This is the whole point, on screen.
5. Resolve the review queue; header counts settle.

## 7. Milestone-by-milestone build order (post-approval)

| M | Deliverable | Proves |
|---|-------------|--------|
| **M0** | repo scaffold, `requirements.txt`, app factory, `fetch_samples.py` + `build_fixtures.py`, generated fixtures committed | data is real, filled & reproducible |
| **M1** | models + migrations/create_all; `seed.py` | schema stands up |
| **M2** | `derivation.py` + tests A1–A3 | counts are right |
| **M3** | `reconciliation.py` + tests B1–B5 | **the crux** holds |
| **M4** | `classifier/extractor.py` + `fields_map.py` + `matching.py` + tests C1–C9, D1–D4 | noisy intake handled |
| **M5** | `status.py` + tests E1–E2 | the screen's numbers |
| **M6** | routes + templates + tests F1–F3 | usable UI |
| **M7** | README (run/decisions/omissions/next) + record 3–5 min video | submission |

Each milestone is independently testable; M2–M5 need no browser. Order front-loads the risky
logic (derivation, reconciliation) and defers UI polish.

## 8. Open decisions already resolved (for the README's decision log)

- Gov ID = per filing adult, not year-scoped, type-checked only.
- One 1040 per household (joint), for `tax_year − 1`.
- W-2 obligations are **ordinal slots**, filled in arrival order; employer identity optional.
- Re-derivation **deactivates, never deletes**; human overrides always win.
- Classifier is a content-first `TieredExtractor` (form fields → text layer → OCR stub);
  filename is only a last-resort tiebreaker; pluggable for a future OCR/ML model.
- Ingestion is synchronous; single-accountant; no auth.
