"""M0 smoke tests: the app boots and the generated fixture set is present & extractable."""
from pathlib import Path

from app import create_app
from app.config import TestConfig

FIXTURES = Path(__file__).parent / "fixtures"


def test_app_boots():
    client = create_app(TestConfig).test_client()
    assert client.get("/health").get_json() == {"status": "ok"}


def test_core_fixtures_present():
    expected = [
        "w2_ana_emp1_2025.pdf", "w2_ana_emp2_2025.pdf", "w2_luis_2025.pdf",
        "w2_carlos_2025.pdf", "w2_ana_2023.pdf",
        "f1040_rivera_2024.pdf", "f1040_rivera_2023.pdf",
        "w2_textlayer_adp_tara_2018.pdf", "scan_unreadable.pdf",
    ]
    missing = [n for n in expected if not (FIXTURES / n).exists()]
    assert not missing, f"missing fixtures: {missing} (run scripts/build_fixtures.py)"


def test_w2_fixture_is_extractable():
    """The generated W-2 carries real, readable form-field values (tier-1)."""
    from pypdf import PdfReader

    fields = PdfReader(str(FIXTURES / "w2_ana_emp1_2025.pdf")).get_fields()
    # A W-2 has several copies sharing short field names (CopyB/C/D all have f2_05[0]);
    # the real extractor reads the *filled* fields, so keep only non-empty values.
    filled = {k.split(".")[-1]: v.get("/V") for k, v in fields.items() if v.get("/V")}
    assert filled.get("f2_05[0]") == "Ana"
    assert filled.get("f2_06[0]") == "Rivera"
    assert filled.get("f2_03[0]") == "Northwind Traders"
