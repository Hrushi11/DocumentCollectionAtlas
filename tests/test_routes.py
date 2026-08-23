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


def test_f2_upload_ingests_and_shows_matched(app):
    cid = app.config["CID"]
    c = app.test_client()
    assert _upload(c, cid, "w2_ana_emp1_2025.pdf").status_code == 302
    body = c.get(f"/client/{cid}").get_data(as_text=True)
    assert "w2_ana_emp1_2025.pdf" in body            # appears as a matched file in the checklist


def test_f3_review_accept_moves_doc_to_matched(app):
    cid = app.config["CID"]
    c = app.test_client()
    _upload(c, cid, "w2_carlos_2025.pdf")            # unknown person → attention queue
    with SessionLocal() as s:
        did = s.query(Document).filter_by(original_filename="w2_carlos_2025.pdf").one().id
        client = s.get(Client, cid)
        luis = next(p for p in client.people if p.role is Role.SPOUSE)
        rid = s.query(Requirement).filter_by(
            client_id=cid,
            natural_key=make_natural_key(luis.id, DocType.W2, 2025, 0)).one().id

    resp = c.post(f"/documents/{did}/review", data={"action": "accept", "requirement_id": rid})
    assert resp.status_code == 302
    with SessionLocal() as s:
        assert s.get(Document, did).state.value == "matched"
