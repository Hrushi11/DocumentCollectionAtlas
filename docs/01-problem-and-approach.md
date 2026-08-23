# 01 — Problem & Approach

## 1. Understand the problem (in one paragraph)

A tax accountant cannot file a client's return until a **client-specific set of documents**
is in hand. The system must, at any moment, answer three questions for one client:
**what has been received, what is still outstanding, and what needs my attention.** The
required set is *computed* from facts about the client, it is *re-computed* as the client
discloses things late, documents *arrive noisily* over weeks and are *machine-classified*
with a confidence, and the accountant is *editing the list by hand the whole time*. The
screen is simple; the machinery under it is not.

## 2. Break the problem down — the four hard parts

Anyone can build a checkbox list. The assignment is really testing whether we notice these
four things and handle them honestly.

### 2.1 Derivation — the list is *computed*, not typed

Rules:

- **Everyone** needs: prior-year **1040** (one per household return) and a **government ID**
  (we decide: one per *adult* — taxpayer + spouse; children who don't file don't need one).
- **W-2s: one per employer, per person, per tax year.** The expected number equals the
  number of *distinct employers a person worked for during the year.*
  - Ana: 2 jobs last year, unchanged this year ⇒ **2 W-2s**.
  - Luis: 1 job, changed jobs in June ⇒ worked for **2 employers** in 2025 ⇒ **2 W-2s**.

The count depends on **last year's filing** (baseline) and **what changed this year**
(mid-year changes *add* a W-2 because both the old and new employer issue one).

→ Modeled as a **pure function** `derive(client_facts) -> set[Requirement]`. Testable with
no browser. See [04 §1](04-core-algorithms.md).

### 2.2 Re-derivation without clobbering the human — *the crux*

The list is derived **more than once**. A job change nobody mentioned in January surfaces
in March. By then the accountant has, for two months:

- marked items **not needed** (waived),
- **removed** entries that were wrong,
- **added** items the system never anticipated.

Re-running derivation must **preserve every one of those edits.** This is a **three-way
merge**: `base` (previous derivation) vs `theirs` (new derivation) vs `ours` (human edits).
Naively regenerating the list would throw away two months of work — the single biggest trap
in this assignment.

Our answer: every requirement has a **stable natural key**, an **origin** (system|human),
a **system-required flag** that re-derivation flips, and a **human override** that
re-derivation never touches. Effective status is a *layered function* of these. See
[04 §2](04-core-algorithms.md).

### 2.3 Noisy intake & classification — *don't act on a bad guess*

Documents arrive over ~6 weeks, out of order, from different family members, each one
independent (Ana's W-2 says nothing about Luis's). A tool guesses
`{type, tax_year, whose, confidence}`. It is usually right, occasionally badly wrong.

- **Low confidence ⇒ never auto-acted on** — it waits in a review queue for a human.
- Explicit awkward cases we must handle: **wrong tax year**, **person nobody asked about**,
  **unreadable scan**.

See classifier design in [02](02-data-and-classifier.md), thresholds in
[04 §3](04-core-algorithms.md).

### 2.4 Matching — attach a document to the right slot, or escalate

A confidently-classified document must be attached to the correct **requirement slot**
(this person, this type, this year). Anything ambiguous — low confidence, no matching
requirement, wrong year, unknown person — goes to the **attention queue** instead of being
force-fit. Matching is by `(person, type, tax_year)` into that person's pool of open slots;
surplus documents beyond the expected count are surfaced, not silently dropped. See
[04 §3](04-core-algorithms.md).

## 3. The core conceptual split (the idea everything hangs on)

> **Requirements** (the checklist) and **Documents** (files that arrive) are *separate
> lifecycles that meet only at a matching step.*

- A **Requirement** is an *obligation*: "Ana needs a 2025 W-2 (slot #1)." It is born from
  derivation or from a human, carries provenance and override state, and survives
  re-derivation.
- A **Document** is a *fact on the ground*: a file plus a classifier guess plus a state
  (`matched | needs_review | exception | rejected`).

Keeping them separate is what makes re-derivation safe (you can recompute obligations
without touching the files that arrived) and what makes the review queue possible (a
document can exist with no obligation to attach to yet).

## 4. Components needed

| Component | Responsibility | Testable headless? |
|-----------|----------------|--------------------|
| **DB / schema** | Persist households, people, employment facts, requirements, documents, links, events | — |
| **Derivation engine** | `client_facts → required set` (pure) | ✅ pure unit tests |
| **Reconciliation service** | Three-way merge of new derivation into existing list, preserving overrides | ✅ pure-ish, DB-backed |
| **Classifier** (`TieredExtractor`, pluggable) | `file → {type, year, person?, confidence}` content-first: form fields → text layer → OCR stub; filename only a last-resort tiebreaker | ✅ fixture files |
| **Ingestion / matching** | Run classifier, decide auto-match vs review vs exception, link doc↔requirement | ✅ |
| **Status / view-model** | Per-requirement effective status + per-client rollup + attention queue | ✅ |
| **Web UI (Flask/Jinja)** | Status screen, add-document, review queue actions | manual + a few route tests |
| **Tests** | Cover derivation, reconciliation, matching, status, key routes | — |
| **README** | Run steps, decisions, omissions, next steps | — |

## 5. What we deliberately leave out (recorded here, expanded in README)

- No auth / multi-tenant / users — single-accountant assumption.
- No real ML/OCR — the content-first `TieredExtractor` reads AcroForm fields + text layer; OCR
  is a stubbed tier, not a model.
- No background job runner — ingestion runs synchronously on upload.
- No employer-identity resolution — W-2 slots are ordinal per person until a doc fills them.
- Government ID is not year-scoped and not machine-validated beyond type.

These are choices, not oversights; each is defensible for a 5–6h build and each has an
obvious "what I'd do next."
