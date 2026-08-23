"""M6: route/UI smoke tests (docs/05 F1–F3)."""
import io
from pathlib import Path

import pytest

from app import create_app
from app.config import TestConfig
from app.db import SessionLocal
from app.domain.reconciliation import run_derivation
from app.models import Client, DocType, Document, Requirement, Role, make_natural_key
from scripts.seed import seed_rivera

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture
def app():
    application = create_app(TestConfig)
    updir = Path(__file__).parent / "_uploads"
    updir.mkdir(exist_ok=True)
    application.config["UPLOAD_DIR"] = str(updir)
    with SessionLocal() as s:
        client = seed_rivera(s)
        run_derivation(s, client, "initial")
        application.config["CID"] = client.id
    return application


def _upload(client_, cid, name):
    data = {"file": (io.BytesIO((FIX / name).read_bytes()), name)}
    return client_.post(f"/client/{cid}/documents", data=data,
                        content_type="multipart/form-data")


def test_f1_client_page_renders_sections_and_counts(app):
    cid = app.config["CID"]
    resp = app.test_client().get(f"/client/{cid}")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "Rivera household" in body
    assert "Checklist" in body and "Received" in body and "Needs attention" in body
    assert "How this works" in body                 # guided walkthrough
    assert "W-2 — job 1" in body                     # plain-language labels, not raw enums


def test_f4_new_client_builds_checklist(app):
    c = app.test_client()
    resp = c.post("/clients", data={
        "name": "Test Household", "tax_year": "2025", "filing_status": "MARRIED_JOINT",
        "person_name_0": "Pat Test", "person_role_0": "TAXPAYER", "person_jobs_0": "2",
        "person_name_1": "Sam Test", "person_role_1": "SPOUSE", "person_jobs_1": "1",
    })
    assert resp.status_code == 302
    with SessionLocal() as s:
        cid = s.query(Client).filter_by(name="Test Household").one().id
    body = c.get(f"/client/{cid}").get_data(as_text=True)
    assert "Test Household" in body and "W-2 — job 1" in body and "W-2 — job 2" in body


def test_f2_upload_ingests_and_shows_matched(app):
    cid = app.config["CID"]
    c = app.test_client()
    assert _upload(c, cid, "w2_ana_emp1_2025.pdf").status_code == 302
    body = c.get(f"/client/{cid}").get_data(as_text=True)
    assert "w2_ana_emp1_2025.pdf" in body            # appears as a matched file in the checklist


def test_f3_invalid_accept_is_blocked(app):
    """A misclick can't file an unknown-person file onto someone else's row (suggestion.md #1)."""
    cid = app.config["CID"]
    c = app.test_client()
    _upload(c, cid, "w2_carlos_2025.pdf")            # unknown person → attention queue
    with SessionLocal() as s:
        did = s.query(Document).filter_by(original_filename="w2_carlos_2025.pdf").one().id
        ana = next(p for p in s.get(Client, cid).people if p.role is Role.TAXPAYER)
        rid = s.query(Requirement).filter_by(
            client_id=cid,
            natural_key=make_natural_key(ana.id, DocType.W2, 2025, 0)).one().id
    resp = c.post(f"/documents/{did}/review", data={"action": "accept", "requirement_id": rid})
    assert resp.status_code == 302
    with SessionLocal() as s:
        assert s.get(Document, did).state.value == "exception"   # blocked, still needs attention


def test_f3b_reassign_files_unknown_person_doc(app):
    """The guided correction: reassign an unknown-person file to a real person → it files."""
    cid = app.config["CID"]
    c = app.test_client()
    _upload(c, cid, "w2_carlos_2025.pdf")
    with SessionLocal() as s:
        did = s.query(Document).filter_by(original_filename="w2_carlos_2025.pdf").one().id
    c.post(f"/documents/{did}/review", data={"action": "reassign", "person_name": "Ana Rivera"})
    with SessionLocal() as s:
        assert s.get(Document, did).state.value == "matched"


def test_f5_add_a_document_we_need(app):
    cid = app.config["CID"]
    c = app.test_client()
    resp = c.post(f"/client/{cid}/requirements",
                  data={"person_id": "", "doc_type": "F1040", "tax_year": "2024",
                        "note": "prior-year state return"})
    assert resp.status_code == 302
    body = c.get(f"/client/{cid}").get_data(as_text=True)
    assert "added by you" in body and "prior-year state return" in body
