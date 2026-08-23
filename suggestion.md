# Suggestions

Review scope: current Flask UI and frontend logic in `app/`, compared against
`docs/07-frontend-ux-spec.md`, with the user assumed to be a non-technical tax accountant.

## Overall

The tone is mostly right. The UI already uses plain language, the screens are simple, and the
main flow is understandable without engineering context. The biggest remaining issues are not
styling problems; they are places where the current UI allows a non-technical user to make the
wrong choice or where the UX spec promises a guided action that the implementation does not yet
support.

## Findings

### 1. High: a reviewed file can be attached to the wrong checklist row with no validation

Why this matters for a non-technical user:

- In the "Needs your review" area, the **This belongs to:** dropdown offers **every**
  outstanding row, not only the valid matches for that document.
- One mistaken click can silently file a W-2 into the wrong person's row or the wrong document
  type, which breaks trust in the checklist.

Where this happens:

- [app/templates/client.html](/D:/TheAtlasAiAssignment/app/templates/client.html:55) loops over
  all outstanding rows for the accept dropdown.
- [app/routes.py](/D:/TheAtlasAiAssignment/app/routes.py:165) accepts any posted
  `requirement_id`.
- [app/domain/matching.py](/D:/TheAtlasAiAssignment/app/domain/matching.py:142) links the
  document to the chosen requirement without checking that the requirement is compatible with the
  document's type, person, year, or even the same client.

Suggested fix:

- Filter the dropdown to only valid target rows for that document.
- Add a server-side guard in `accept()` so the route rejects invalid matches even if the form is
  manipulated or the UI regresses later.

## 2. High: the UX spec assumes the user can add an unexpected requirement, but the UI does not expose that flow

Why this matters for a non-technical user:

- The broader product logic supports "the system didn't anticipate it; add one yourself".
- That is a real accountant workflow.
- The current client screen shows "added by you" tags, and routes exist for adding a
  requirement, but there is no visible UI for doing it.

Where this mismatch shows up:

- [docs/07-frontend-ux-spec.md](/D:/TheAtlasAiAssignment/docs/07-frontend-ux-spec.md:74) says
  "added by you" rows are tagged, implying the user can create them.
- [app/routes.py](/D:/TheAtlasAiAssignment/app/routes.py:146) implements `POST /client/<id>/requirements`.
- [app/domain/matching.py](/D:/TheAtlasAiAssignment/app/domain/matching.py:180) supports
  `add_requirement(...)`.
- [app/templates/client.html](/D:/TheAtlasAiAssignment/app/templates/client.html) contains no
  control for adding one.

Suggested fix:

- Add a small "Add a document we need" panel on the client page.
- Make it simple: person, document type, year if relevant, optional note.

## 3. Medium: the "Change person/year" flow is not guided enough for a non-technical user

Why this matters:

- The UX spec promises a friendly correction flow.
- The current implementation asks the user to type a free-text person name and optionally a year.
- A typo, nickname, or blank value can keep the file in review with no explanation of what went
  wrong.

Where this happens:

- [docs/07-frontend-ux-spec.md](/D:/TheAtlasAiAssignment/docs/07-frontend-ux-spec.md:70)
  describes a guided "Change person/year" action.
- [app/templates/client.html](/D:/TheAtlasAiAssignment/app/templates/client.html:62) uses raw
  text and number inputs with placeholders `person` and `year`.
- [app/domain/matching.py](/D:/TheAtlasAiAssignment/app/domain/matching.py:162) silently
  re-routes based on whatever was typed.

Suggested fix:

- Replace free-text person entry with a dropdown of client people.
- Keep year as a constrained choice where possible.
- Add a short confirmation/error message after reassigning so the user knows what happened.

## 4. Medium: the wrong-year message is clear for W-2s but misleading for prior-year 1040s

Why this matters:

- A non-technical user should be told what was expected, not just what filing year they are in.
- For a 1040, the expected year is last year, not the filing year.

Where this happens:

- [app/labels.py](/D:/TheAtlasAiAssignment/app/labels.py:32) says:
  "This looks like a {year} document, but you're filing {client.tax_year}."

Why that is weak:

- For a 2025 case, a wrong-year 1040 is wrong because the system needed the **2024** return,
  not because the user is "filing 2025".

Suggested fix:

- Make the explanation doc-type aware.
- Example:
  - for W-2: "This looks like a 2023 W-2, but we need a 2025 W-2."
  - for 1040: "This looks like a 2023 tax return, but we need last year's return (2024)."

## 5. Medium: "Needs your review" does not include accountant-pinned required items, even though the wider logic treats them as attention-worthy

Why this matters:

- If the accountant explicitly marks something as required, that is a high-signal "follow up on
  this" action.
- The current summary tile only counts documents that are in review/exception states.

Where this happens:

- [app/domain/status.py](/D:/TheAtlasAiAssignment/app/domain/status.py:45) defines attention as
  documents in `NEEDS_REVIEW` or `EXCEPTION`.
- [app/domain/status.py](/D:/TheAtlasAiAssignment/app/domain/status.py:52) uses that count for
  the summary tiles.
- [app/templates/client.html](/D:/TheAtlasAiAssignment/app/templates/client.html:21) displays
  that count as **Needs your review**.

Suggested fix:

- Decide whether pinned outstanding rows should appear in the attention count and banner.
- If yes, update both the summary logic and the UX spec language so they match.

## 6. Medium: the UI gives almost no explicit success feedback after important actions

Why this matters:

- Non-technical users benefit from small confirmations.
- Right now most actions just redirect back to the page and require the user to notice that a
  count or row changed.

Where this shows up:

- Upload, reject, reassign, mark not needed, mark required, and update checklist all redirect
  immediately from [app/routes.py](/D:/TheAtlasAiAssignment/app/routes.py:116),
  [app/routes.py](/D:/TheAtlasAiAssignment/app/routes.py:132),
  [app/routes.py](/D:/TheAtlasAiAssignment/app/routes.py:159), and
  [app/routes.py](/D:/TheAtlasAiAssignment/app/routes.py:178).

Suggested fix:

- Add flash messages such as:
  - "2 files uploaded"
  - "Marked as not needed"
  - "Checklist updated for Luis"
  - "Filed under Ana - W-2 job 2"

## 7. Low: a few UX spec promises are still more polished than the implementation

These are not major, but they are noticeable.

- [docs/07-frontend-ux-spec.md](/D:/TheAtlasAiAssignment/docs/07-frontend-ux-spec.md:41) says
  the whole row/name is a link on the clients page. In
  [app/templates/clients.html](/D:/TheAtlasAiAssignment/app/templates/clients.html:15), only the
  name and the "Open" text link are clickable.
- [docs/07-frontend-ux-spec.md](/D:/TheAtlasAiAssignment/docs/07-frontend-ux-spec.md:60) says
  the "How this works" strip is open by default the first time. In
  [app/templates/client.html](/D:/TheAtlasAiAssignment/app/templates/client.html:9), it is always
  open.
- [docs/07-frontend-ux-spec.md](/D:/TheAtlasAiAssignment/docs/07-frontend-ux-spec.md:69) calls
  for a prominent drop zone / file picker. The current implementation is a standard file input,
  which is acceptable, but less guided than the doc suggests.

Suggested fix:

- Either simplify the doc so it matches the current implementation, or finish the remaining UX
  polish so the implementation matches the doc.

## What is already working well

- The templates mostly avoid internal jargon, which aligns well with
  [docs/07-frontend-ux-spec.md](/D:/TheAtlasAiAssignment/docs/07-frontend-ux-spec.md:9).
- The main client screen has a clear top-to-bottom flow:
  summary, next step, upload, review, checklist, then change handling.
- The "How this works" explainer is short and readable.
- The document labels are plain enough for an accountant:
  [app/labels.py](/D:/TheAtlasAiAssignment/app/labels.py:17) does a good job here.

## Suggested priority order

1. Prevent invalid "File it here" matches in both UI and backend.
2. Add a visible UI for "Add a document we need".
3. Replace free-text reassign with guided controls.
4. Improve the wrong-year explanation text.
5. Add small success confirmations after actions.

## Resolution (author) — all acted on, 39 tests green

| # | Finding | What changed |
|---|---------|--------------|
| 1 | Invalid "File it here" match | `matching.can_accept()` guard (same client/type/year/person; 1040 = household); `accept()` raises on mismatch; the dropdown is now filtered to valid rows only (`accept_options` in `routes.client_page`), with an empty-state hint. Tests: `test_accept_rejects_incompatible_row`, route `test_f3_invalid_accept_is_blocked`. |
| 2 | No UI to add a requirement | New **"Need something the list doesn't show?"** panel (person / type / year / note) → `POST /client/<id>/requirements`; `add_requirement` now auto-picks a free slot so it can't collide with the unique key. Tests: `test_add_requirement_autoslots_without_collision`, `test_f5_add_a_document_we_need`. |
| 3 | Free-text reassign | Reassign now uses a **people dropdown** + a **year dropdown** (this year / last year); a confirmation message states whether it filed or still needs review. Route `test_f3b_reassign_files_unknown_person_doc`. |
| 4 | Wrong-year text weak for 1040 | `labels.why_text` is doc-type aware: W-2 → "…but we need a 2025 W-2"; 1040 → "…but we need last year's return (2024)". |
| 5 | Pinned items not counted as attention | `status.client_summary` now `attention = review docs + pinned-outstanding`; `pinned_outstanding()` added; tile relabelled **Needs attention**, banner breaks down both, checklist shows **★ required**. |
| 6 | No success feedback | Flash messages on upload / accept / reject / reassign / waive / pin / undo / add / update-checklist / create-client (`SECRET_KEY` added; rendered in `base.html`). |
| 7 | Spec vs impl polish | Reconciled `docs/07` wording (clients link, help strip "open by default", file picker) and documented the new add-document step + attention definition. |

No disagreements — several were genuine correctness/trust issues (esp. #1). All findings closed.
