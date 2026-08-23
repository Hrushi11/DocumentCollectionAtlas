# 02 — Data & Classifier

The assignment says: *supply your own real document files, name them as a client would, and
include the awkward cases.* Because we're building for a **real-life use case**, the identity
of a document must come from **its own content** (the employee name in Box e, the employer in
Box c, the year on the form) — **not** from the filename. This doc records where the data
comes from, how we make it realistic and reproducible, and the **tiered content extractor**
that pulls real fields out — every claim below is backed by extraction we actually ran.

## 1. How we get realistic, *filled* data (and why not internet samples)

We tried scavenging filled samples off the web. Lesson learned, recorded as evidence:

- Blank IRS templates carry **no name/employer/wages** — useless for identity.
- The ADP "Sample W-2" (`support.adp.com/.../W2_Interactive.pdf`) looked filled but is an
  **interactive tooltip demo**: 54 form fields, **all values empty**; extraction returns only
  boilerplate prose. Typical of "sample" hits — blank, tooltip-only, or flat scanned images.

The robust, reproducible source is hiding in plain sight: **the official IRS PDFs are fully
fillable AcroForms.** We verified:

| Template | Pages | AcroForm fields | Notable |
|----------|-------|-----------------|---------|
| `f1040.pdf` | 2 | **229** | fillable |
| `fw2.pdf` | 11 | **819** | **semantically named**: `FirstName_ReadOrder`, `LastName_ReadOrder`, `Box1_ReadOrder`, … |

So we **generate our own realistic filled forms** by populating the official templates with
the Rivera scenario data. This gives fixtures that are (a) genuinely filled with real fields,
(b) fully reproducible from a script, (c) exactly matched to our test scenario. Proven fill →
read-back on the W-2:

```
filled: FirstName=Ana, LastName=Rivera, Box1 wages=82000.00
read back via AcroForm /V:  f2_05='Ana'  f2_06='Rivera'  f2_09='82000.00'   ✅
```

(Gotcha we already solved: the terminal field is `…FirstName_ReadOrder[0].f2_05[0]`, not the
parent node; and IRS forms carry an **XFA** layer that must be dropped so AcroForm values are
authoritative. Both handled in `scripts/build_fixtures.py`.)

### Correct tax years

The form's year is **static text on the template**, so we pull the right vintage per fixture:

| Need | Source |
|------|--------|
| TY2025 W-2 (correct-year) | `https://www.irs.gov/pub/irs-prior/fw2--2025.pdf` |
| TY2024 1040 (prior return) | `https://www.irs.gov/pub/irs-prior/f1040--2024.pdf` |
| TY2023 W-2 (wrong-year case) | `https://www.irs.gov/pub/irs-prior/fw2--2023.pdf` |

`scripts/fetch_samples.py` downloads templates; `scripts/build_fixtures.py` fills them with
scenario data and produces the awkward variants. The whole fixture set regenerates from a
clean checkout.

## 2. What the real files contain (evidence for the extractor)

| Signal | 1040 | W-2 | How we get it |
|--------|------|-----|---------------|
| **Type** | "U.S. Individual Income Tax Return" / "Form 1040" static text | "Wage and Tax Statement" / "Form W-2" static text | **text layer** (reliable even on blank templates) |
| **Tax year** | "2025" static near title | year static on form pages; **page 0 is a "DO NOT FILE" cover with no year**; stray years (2014, 2027) elsewhere | **text layer**, most-frequent year, skip cover |
| **Whose / employer / wages** | filled fields | filled fields (Box e name, Box c employer, Box 1 wages) | **AcroForm `/V`** when filled digitally; **text layer** when flattened; **OCR** when scanned |
| **Readability** | — | image-only render ⇒ **0 chars, no fields** | triggers `unreadable` |

### 2.1 Real vendor-format sample (validated)

`W2_Multi_Sample_Data_input_ADP1_clean_15500.pdf` is a real **ADP "W-2 & Earnings Summary"
(Copy C)** with synthetic PII — flattened (no AcroForm), 6.1k chars of text layer, layout
unlike the IRS template. Extraction run confirms: **type** (W-2), **year** (2018),
**employer** ("Lewis Ltd and Sons"), **SSN/EIN** all pull cleanly; **employee name**
("Tara Wilson") and **Box 1 wages** (193,488.36) need coordinate-aware parsing. Two design
rules come from it:

- **Type detection uses a flexible token-set** (`w-2` + `wages, tips` + `social security
  wages` + `medicare`, ≥3/4), **not** exact multiword anchors — vendor layouts reflow text so
  `"wage and tax statement"` splits across lines and fails.
- **Name and box amounts are extracted positionally** via `pdfplumber.extract_words()` (locate
  the value by x/y near its box label), because two-column earnings summaries interleave
  reading order. Label-anchored regex still handles SSN/EIN/employer.

Because it's Tara Wilson / 2018, this file doubles as an **authentic `wrong_year` +
`unknown_person` exception fixture** when loaded against the Rivera (TY2025) client — no
fabrication needed. Rivera-named TY2025 forms (generated per §1) cover the happy-path
matching tests.

## 3. The classifier = a tiered content extractor (pluggable)

### 3.1 Interface

```python
@dataclass
class Classification:
    doc_type: Literal["W2","1040","ID","UNKNOWN"]
    tax_year: int | None
    person_name: str | None       # extracted from CONTENT, not filename
    employer_name: str | None
    wages: float | None
    confidence: float
    readable: bool
    source: Literal["form_fields","text_layer","ocr","filename"]   # which tier fired
    signals: dict                 # for the UI "why"

class Classifier(Protocol):
    def classify(self, file_path: str, original_filename: str) -> Classification: ...
```

### 3.2 The three tiers (each proven above)

1. **Structured form fields (primary, highest confidence).** If the PDF has AcroForm fields
   with values, read them directly and map field→semantics. For the W-2 the names are
   semantic (`FirstName_ReadOrder`→given name, `LastName_ReadOrder`→surname,
   `Box1_ReadOrder`→wages, Box c fields→employer). The 1040's field names are opaque
   (`f1_04…`), so we keep a **small positional map** built once against the official template.
   Exact values ⇒ `confidence ≈ 0.95`, `source="form_fields"`. *(Implementation note from M0:
   a W-2 has several copies (CopyB/C/D) that **share short field names** like `f2_05[0]`; the
   extractor must read the **filled** field and ignore the empty duplicates.)*
2. **Text layer (fallback).** Flattened/printed PDFs bake values into content. Detect **type**
   and **year** from anchor phrases (robust), and pull the name via labelled regex
   (`Employee's name`, `Box e`). `source="text_layer"`, `confidence ≈ 0.7–0.85` depending on
   how much resolves.
3. **OCR (interface only for now).** Image-only PDFs/JPEGs yield no text and no fields. We
   **don't** implement OCR in the time budget; we route these to review as `unreadable` and
   note "OCR would go here" behind the same interface.

Resolution order per field: **form_fields → text_layer → ocr**. **Filename is only a
last-resort tiebreaker** (e.g. to disambiguate which person when content is partial) and is
never the sole basis for a confident match — the opposite of the earlier blank-form design.

### 3.3 Person resolution (now content-driven)

Extracted `person_name` is matched against the client's known people (case-insensitive, light
fuzzy). Outcomes:

- Matches a client person ⇒ `guess_person_id` set.
- Extracted a name that matches **nobody** (e.g. "Carlos Mendez") ⇒ `guess_person_id=None`
  ⇒ **`unknown_person`** exception. This is now a *real* signal ("the form is genuinely for
  someone we don't have"), not a filename guess.
- No name extractable at all (flattened badly / scan) ⇒ low confidence ⇒ review.

### 3.4 Confidence → routing (full rules in [04 §3](04-core-algorithms.md))

| Situation | Outcome |
|-----------|---------|
| no text **and** no form fields | `exception: unreadable` |
| `confidence < LOW` (0.60) | `needs_review` (never auto-matched) |
| extracted year ≠ **expected year for its type** (W-2 = `tax_year`, 1040 = `tax_year − 1`; ID unscoped) | `exception: wrong_year` |
| extracted person matches no client person | `exception: unknown_person` |
| confident + matches an open slot | `matched` automatically |
| confident but no open slot | `exception: unexpected_extra` |

### 3.5 Why this satisfies the brief

- It extracts **real data from the form itself** — employee name, employer, wages, year — so a
  real client's digital W-2/1040 is understood without relying on how they named the file.
- The awkward cases become *authentic content signals*: wrong-year = the year printed on the
  form; unknown-person = the name printed in Box e; unreadable = a real image with no text.
- It degrades honestly across the tiers and stays **pluggable** — a production OCR/NLP model
  slots in as tier 3 behind the same `Classifier` protocol.
