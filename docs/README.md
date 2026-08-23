# Document Collection — Specification Set

This folder is the **complete spec** for the Document Collection assignment. Nothing is
built until these read cleanly. Read them in order.

| # | Doc | What it answers |
|---|-----|-----------------|
| 01 | [Problem & Approach](01-problem-and-approach.md) | What the problem really is, the four hard sub-problems, the components needed |
| 02 | [Data & Classifier](02-data-and-classifier.md) | Where the document files come from (generated from IRS templates) and the tiered content extractor |
| 03 | [Domain Model & Schema](03-domain-model-and-schema.md) | Every table, every column, and **why** it exists |
| 04 | [Core Algorithms](04-core-algorithms.md) | Derivation, three-way reconciliation, matching, status — the logic that matters |
| 05 | [Test Scenarios (E2E)](05-test-scenarios.md) | End-to-end scenarios and the test cases that prove each one |
| 06 | [Tech Spec & Execution Plan](06-tech-spec-and-plan.md) | Architecture, routes, UI, project layout, milestone-by-milestone build order |
| 07 | [Frontend / UX Spec](07-frontend-ux-spec.md) | Non-technical-user UI: plain-language glossary, screen-by-screen spec, guided walkthrough |

## Locked decisions (from planning)

- **Stack:** Flask + SQLAlchemy + Jinja2, SQLite, pytest. Server-rendered pages.
- **Classifier:** a *tiered content extractor* — **(1) AcroForm form fields** (primary; exact
  employee name/employer/wages/year), **(2) text layer** via `pdfplumber` (type + year +
  labelled name), **(3) OCR** (interface only; image-only ⇒ `unreadable`). **Filename is a
  last-resort tiebreaker, never the basis of a confident match.** Fixtures are *generated* by
  filling the official IRS AcroForm templates with our scenario data (reproducible). Proven
  end-to-end: `Ana`/`Rivera`/`82000.00` read back from a filled W-2. See
  [02](02-data-and-classifier.md) for the evidence.
- **Core split:** *Requirements* (derived checklist, carries provenance + human override) vs
  *Documents* (arriving files + classification); they meet only at a matching step. This is
  what makes re-derivation safe.
- **The screen** is the deliverable: *received / outstanding / needs attention* for one
  client, plus add-a-document and a review queue.

## The worked example we design against (our own, not the PDF's)

> **Rivera household**, filing jointly, **tax year 2025**
> People: **Ana** (taxpayer), **Luis** (spouse), **Mateo** (child)
> Last year: Ana had **2 jobs**, Luis had **1 job**
> This year: Luis **changed jobs in June 2025**
> Everyone: prior-year **1040**, a **government ID**
>
> The March disclosure that stresses the system: Luis's June job change is **not known in
> January**. The system first derives a list assuming Luis has 1 job; the accountant works
> that list for two months (waiving and adding items); then the job change surfaces and we
> **re-derive without destroying their edits**.
