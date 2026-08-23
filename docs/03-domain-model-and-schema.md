# 03 — Domain Model & Schema

SQLite via SQLAlchemy. Every table and column below has a **why**. The design's spine is the
[Requirement vs Document split](01-problem-and-approach.md#3-the-core-conceptual-split).

## 1. Entity map

```
Client (household)
 ├─ Person (Ana, Luis, Mateo)
 │    └─ Employment (person × tax_year × employer)      ← facts that drive derivation
 ├─ Requirement (the checklist item)                    ← derived and/or human-edited
 │    └─ RequirementDocument (link) ─┐
 ├─ Document (uploaded file + guess) ┘                  ← files that arrive
 ├─ DerivationRun (audit of each re-derivation)
 └─ Event (append-only audit of everything a human/system did)
```

## 2. Tables

### `client`
| col | type | why |
|-----|------|-----|
| id | pk | |
| name | str | "Rivera household" |
| tax_year | int | The year being filed (2025). Scopes derivation & year-matching. |
| filing_status | enum | `single`/`married_joint`/… — affects who needs an ID and the single 1040. |
| created_at | ts | |

### `person`
| col | type | why |
|-----|------|-----|
| id | pk | |
| client_id | fk | |
| name | str | Matched against the employee name the extractor pulls from the document (W-2 Box e / 1040 name row). |
| role | enum | `taxpayer`/`spouse`/`dependent`. Drives rules: only `taxpayer`+`spouse` need a gov ID; dependents don't file. |

**Why store `role`:** the "who needs what" rules are role-based. Keeping role explicit makes
derivation a clean lookup, not a special case.

### `employment` — *the fact that makes W-2 counts derivable*
| col | type | why |
|-----|------|-----|
| id | pk | |
| person_id | fk | |
| tax_year | int | Which year this job counts toward. |
| employer_name | str? | May be unknown at first ("job #1"); filled when known. |
| ended_midyear | bool | A mid-year *end* still yields a W-2 for the partial year. |
| source | enum | `prior_year` (carried baseline) / `disclosed` (told this year) / `late_disclosure` (the March surprise). |
| disclosed_at | ts | Lets us reproduce "known in January vs surfaced in March". |

**Why this is the input to derivation:** the W-2 count for a person-year is simply *the
number of distinct employers they worked for during that year.* "Ana had 2 jobs" = 2
employment rows. "Luis changed jobs in June" = his 1 baseline row **+** 1 late-disclosed row
= 2 employers = 2 W-2s. The rule becomes counting, not branching. **The March re-derivation
is modeled as inserting one `employment` row with `source=late_disclosure` and re-running.**

### `requirement` — *the checklist item; the reconciliation-aware core*
| col | type | why |
|-----|------|-----|
| id | pk | |
| client_id | fk | |
| person_id | fk? | Null for household-level items (the single 1040). |
| doc_type | enum | `W2`/`1040`/`ID`. |
| tax_year | int? | Year the doc must be for (null for gov ID). |
| slot_index | int | Ordinal for multi-W-2 people (W-2 #1, #2). Part of identity. |
| **natural_key** | str (unique per client) | **Stable identity** = hash of `(person, doc_type, tax_year, slot_index)`. This is how re-derivation re-finds a requirement instead of duplicating it. |
| **origin** | enum | `system` or `human`. Human-added requirements are never removed by derivation. |
| **system_required** | bool | Set by the *latest* derivation: does the system currently want this? Re-derivation flips this; it does **not** delete rows. |
| **human_override** | enum | `none` / `waived` (marked "not needed") / `removed` (human deleted a system item) / `pinned` (human insists it's needed). The human's will; derivation **never** writes this column. |
| note | str? | Free text for the accountant. |
| created_by_run_id | fk? | Which derivation first created it (audit). |
| created_at / updated_at | ts | |

**Why the four state columns instead of a status enum:** status must be *reconstructable*
after any re-derivation. Separating **who wants it** (`origin`, `system_required`) from
**what the human decided** (`human_override`) from **what arrived** (the link below) is what
lets a re-run change the system's opinion without erasing the human's. Effective status is
*computed* from these — see [04 §2.3](04-core-algorithms.md). Collapsing them into one
mutable `status` is the exact bug the assignment is probing for.

### `document` — *a file that arrived + the classifier's guess*
| col | type | why |
|-----|------|-----|
| id | pk | |
| client_id | fk | |
| original_filename | str | What the client named it; a classifier input. |
| stored_path | str | Where the file lives on disk. |
| uploaded_at | ts | Arrival order for filling slots. |
| **guess_type / guess_year / guess_person_id / guess_person_name** | | Classifier output. `guess_person_name` is **extracted from content** (Box e); `guess_person_id` null when it matches nobody (→ unknown-person). |
| **extracted_employer / extracted_wages** | str? / num? | Real fields pulled from the form (Box c / Box 1); shown in the UI and useful for future employer-level matching. |
| **extraction_source** | enum | `form_fields` / `text_layer` / `ocr` / `filename` — which tier produced the guess (drives confidence + the "why"). |
| **confidence** | float | Gate for auto-match vs review. |
| **readable** | bool | False ⇒ unreadable exception. |
| signals_json | json | Why the classifier decided (raw fields/anchors), shown in UI. |
| **state** | enum | `matched` / `needs_review` / `exception` / `rejected`. |
| **exception_reason** | enum? | `unreadable` / `wrong_year` / `unknown_person` / `unexpected_extra` / null. |
| resolved_by / resolved_at | | Audit of the human review action. |

### `requirement_document` — the link (a document *fulfills* a requirement)
| col | type | why |
|-----|------|-----|
| id | pk | |
| requirement_id | fk | |
| document_id | fk | |
| linked_by | enum | `system` (auto-match) / `human` (review action). |
| linked_at | ts | |

**Why a join table, not a `document_id` on requirement:** keeps the two lifecycles
independent, lets a human re-point a mis-matched doc, and preserves history. One requirement
is fulfilled by (at most) one *active* link, but past links stay for audit.

### `derivation_run` — audit of each re-derivation
| col | type | why |
|-----|------|-----|
| id | pk | |
| client_id | fk | |
| created_at | ts | When we re-derived (Jan vs March). |
| reason | str | "initial" / "late job disclosure" — narrates the history the reviewers read. |
| summary_json | json | Diff: added / re-activated / deactivated counts. Proves reconciliation ran and shows what it did. |

### `event` — append-only audit log
| col | type | why |
|-----|------|-----|
| id | pk | |
| client_id | fk | |
| at | ts | |
| actor | enum | `system` / `accountant`. |
| verb | str | `derived`, `waived`, `removed`, `added`, `document_received`, `auto_matched`, `reviewed_accept`, `reviewed_reject`, `reassigned`. |
| payload_json | json | Details. |

**Why an event log:** the story ("marked not needed in Feb, job change in March") is the
whole point; the log makes it inspectable and gives the demo video something to narrate.

## 3. Effective status is *derived*, never stored

There is intentionally **no** `requirement.status` column. Status is a pure function of
(`system_required`, `human_override`, active link presence, matched-document year) computed
at read time. See [04 §2.3](04-core-algorithms.md). This guarantees a re-derivation can
never leave a stale status behind.

## 4. Indices & constraints

- `unique(client_id, natural_key)` on `requirement` — makes re-derivation idempotent.
- `index(document.client_id, state)` — the review queue query.
- `index(employment.person_id, tax_year)` — derivation lookup.
