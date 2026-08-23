# 07 — Frontend / UX Spec (for a non-technical user)

The user is a **tax accountant**, not an engineer. They should be able to sit down and *walk
through the whole thing* without a manual. This spec defines the screens, the plain language,
and the guided flow. It is the contract the templates implement.

## 1. Principles

1. **Plain words, no system jargon.** The user never sees "requirement", "derive", "slot",
   "reconcile", "exception", "confidence score", "extraction source". See the glossary (§2).
2. **Always answer "what do I do next?"** Every screen has one obvious next action.
3. **Never blame the user.** When the tool is unsure it says so in a friendly way and asks a
   simple question.
4. **Guided, not gated.** A short "How this works" strip explains the flow; it can be collapsed.
5. **Server-rendered, forgiving.** Buttons and forms only; nothing requires the user to
   understand pages reloading.

## 2. Glossary — internal term → what the user sees

| Internal | User-facing |
|----------|-------------|
| Client / household | **Client** |
| Requirement | **a document we need** (a checklist row) |
| doc_type `W2` / `1040` / `ID` | **W-2 — job 1**, **Last year's tax return (1040)**, **Government ID** |
| slot_index | shown as **job 1 / job 2** |
| status `received` / `outstanding` / `not_needed` | **Received** / **Still needed** / **Not needed** |
| document in `needs_review` / `exception` | **Needs your review** |
| exception `unreadable` | "**We couldn't read this file.**" |
| exception `wrong_year` | "**This looks like a {year} document.**" |
| exception `unknown_person` | "**This name isn't one of this client's people.**" |
| exception `unexpected_extra` | "**This looks like an extra one.**" |
| confidence < 0.6 | "**The tool wasn't sure about this.**" |
| re-derive | **Update the checklist** |
| waive / pin / unset | **Mark not needed** / **Mark as required** / **Undo** |
| origin = human | "**added by you**" |

## 3. Screens

### 3.1 Clients (`/`)
- Heading **"Your clients"** + one-line explainer.
- Table: Client · Tax year · People · an **"Open →"** link (the client name is also a link).
- Primary button **"+ New client"** (top-right).
- **Empty state:** friendly card — "No clients yet. Add your first client to get started." with
  the New client button.

### 3.2 New client (`/clients/new`)
A single simple form — no wizard needed:
- **Client / household name** (text, required).
- **Tax year** (number, default current filing year).
- **Filing status** (dropdown, plain labels: "Married — filing jointly", etc.).
- **People** — up to 6 rows, each: **Name**, **Role** (Taxpayer / Spouse / Child), and
  **Number of jobs this year** with helper text: *"How many employers did they work for? We'll
  expect one W-2 per job."*
- Helper note at top: *"We'll build the document checklist automatically from this."*
- Submit **"Create client"** → lands on that client's screen with the checklist already built.

### 3.3 Client status screen (`/client/<id>`) — the heart
Top-to-bottom:
1. **Title bar** — client name, tax year, filing status, people.
2. **"How this works"** collapsible strip (open by default): 3 steps —
   *1) Upload the documents as they arrive. 2) We sort them and flag anything odd. 3) Review
   the flagged ones and you're done.*
3. **Four summary tiles** — Received · Still needed · **Needs attention** (highlighted; counts
   both files awaiting review **and** items the accountant marked "required" that aren't in
   yet) · Not needed.
4. **"Next step" banner** — dynamic sentence:
   - review pending → "**You have N file(s) to review below.**"
   - else outstanding → "**Still waiting on N document(s).** Upload them below as they arrive."
   - else → "**All documents are in. Nothing outstanding.** ✅"
5. **Add documents** — a clear file picker (multiple files at once), one line of help.
6. **Needs your review** (only if any) — each flagged file as a friendly card: filename, a
   plain-English **doc-type-aware** reason (a wrong-year W-2 vs a wrong-year 1040 read
   differently), and clear actions. **This belongs to…** only offers rows that actually match
   the file (a misclick can't file it into the wrong person/type/year — enforced server-side
   too). **Change person/year** uses dropdowns of the client's people + valid years. **Not this
   client** rejects. Every action returns a short confirmation message.
7. **The checklist** — grouped, plain rows: Who · Document · Year · Status pill · the filed
   file *or* the actions **Mark not needed / Mark as required**. "added by you" rows are tagged;
   "required" rows show a ★.
8. **Need something the list doesn't show?** — a small panel to **add a document we need**
   (person / type / optional year / note) for the "system didn't anticipate it" case.
9. **Something changed?** — the "Update the checklist" panel: pick a person + type a new
   employer to record a mid-year job change, then **Update checklist**. Copy reassures:
   *"Your not-needed and added items are kept."*

## 4. End-to-end walkthrough (what a first-time user does)

1. Land on **Your clients** → click **+ New client** → fill name, tax year, add Ana (Taxpayer,
   2 jobs), Luis (Spouse, 1 job), Mateo (Child, 0) → **Create client**.
2. Arrive on the client screen; the checklist is already there (1040, 2 IDs, 3 W-2s). The
   "Next step" banner says *Still waiting on 6 documents.*
3. **Upload** a couple of clean W-2s and last year's return → they turn **Received** instantly.
4. Upload an odd file (old year / wrong person / unreadable) → it appears under **Needs your
   review** with a plain reason. User clicks **Not this client** or **Change person/year**.
5. User **Marks not needed** the second ID (already on file) and the checklist updates.
6. A client mentions a **June job change** → user opens **Something changed?**, picks Luis, types
   the new employer, **Update checklist** → one new W-2 row appears; the not-needed ID stays
   not-needed. Banner re-counts.
7. When the review queue is empty and everything is Received/Not needed, the banner reads
   **All documents are in.**

## 5. Acceptance (maps to route tests F1–F3 + manual)

- New client form creates the client and lands on a populated checklist.
- Upload of a clean W-2 shows it as **Received** without any review step.
- An odd file lands in **Needs your review** with a human-readable reason and resolvable actions.
- No screen shows raw enum values, hashes, or the word "requirement/derive/slot/exception".
