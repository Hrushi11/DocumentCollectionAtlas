"""
PoC: generate a filled Rivera-household 1040 from the official IRS TY2024 template,
then prove we can read the identity back out of the document content.

This is the seed of the real `scripts/build_fixtures.py` (milestone M0). It demonstrates
the "1040 source = A (generate from IRS template + synthetic data)" decision end to end:
  fill AcroForm  ->  strip XFA  ->  extract structured values  ->  render a preview.

Run:  ./venv/Scripts/python.exe scripts/poc_fill_1040.py
"""
from pathlib import Path
from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject, BooleanObject

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "sampleData" / "f1040_prior_2024.pdf"
OUT_PDF = ROOT / "sampleData" / "poc_f1040_rivera_2024.pdf"
OUT_PNG = ROOT / "sampleData" / "poc_f1040_rivera_2024.png"

# Per-template positional field map for the TY2024 1040 (located by widget coordinates;
# the fields themselves are opaque `f1_NN` with no tooltips — see docs/02 §1).
FIELDS_1040_2024 = {
    "taxpayer_first": "f1_04[0]",
    "taxpayer_last":  "f1_05[0]",
    "taxpayer_ssn":   "f1_06[0]",
    "spouse_first":   "f1_07[0]",
    "spouse_last":    "f1_08[0]",
    "spouse_ssn":     "f1_09[0]",
    "home_address":   "f1_10[0]",
}

# Rivera household — our worked example (synthetic data).
RIVERA = {
    "taxpayer_first": "Ana",
    "taxpayer_last":  "Rivera",
    "taxpayer_ssn":   "123-45-6789",
    "spouse_first":   "Luis",
    "spouse_last":    "Rivera",
    "spouse_ssn":     "987-65-4321",
    "home_address":   "42 Maple Street, Springfield IL 62704",
}


def fill(template: Path, field_map: dict, data: dict, out: Path) -> None:
    reader = PdfReader(str(template))
    fq = {k.split(".")[-1]: k for k in reader.get_fields()}  # short -> fully-qualified
    values = {fq[field_map[key]]: val for key, val in data.items() if key in field_map}

    writer = PdfWriter()
    writer.append(reader)
    acro = writer._root_object["/AcroForm"]
    if "/XFA" in acro:                       # XFA would shadow AcroForm values
        del acro["/XFA"]
    acro[NameObject("/NeedAppearances")] = BooleanObject(True)
    for page in writer.pages:
        try:
            writer.update_page_form_field_values(page, values, auto_regenerate=False)
        except Exception:
            pass
    with open(out, "wb") as fh:
        writer.write(fh)


def extract_identity(pdf_path: Path) -> dict:
    """Tier-1 (form fields) read-back — what the classifier would do on a digital 1040."""
    fields = PdfReader(str(pdf_path)).get_fields()
    short = {k.split(".")[-1]: (v.get("/V") or None) for k, v in fields.items()}
    inv = {v: k for k, v in FIELDS_1040_2024.items()}
    return {inv[fn]: short.get(fn) for fn in inv}


def render_preview(pdf_path: Path, png_path: Path) -> None:
    import pypdfium2 as pdfium
    pdf = pdfium.PdfDocument(str(pdf_path))
    pdf[0].render(scale=1.6).to_pil().save(str(png_path))


if __name__ == "__main__":
    fill(TEMPLATE, FIELDS_1040_2024, RIVERA, OUT_PDF)
    print(f"wrote {OUT_PDF.relative_to(ROOT)}")

    ident = extract_identity(OUT_PDF)
    print("\n--- structured read-back (tier 1: form fields) ---")
    for k, v in ident.items():
        print(f"  {k:16} = {v!r}")

    render_preview(OUT_PDF, OUT_PNG)
    print(f"\nrendered preview -> {OUT_PNG.relative_to(ROOT)}")
