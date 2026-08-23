"""Server-rendered UI (docs/06 §3–4). Routes are thin: they delegate to the domain layer."""
from __future__ import annotations

from pathlib import Path

from flask import (
    Blueprint,
    abort,
    current_app,
    redirect,
    render_template,
    request,
    url_for,
)

from app.db import SessionLocal
from app.domain.classifier import TieredExtractor
from app.domain.matching import accept, add_requirement, ingest, reassign, reject
from app.domain.reconciliation import run_derivation
from app.domain.status import (
    OUTSTANDING,
    attention_documents,
    client_summary,
    status_of,
    visible_requirements,
)
from app.models import (
    Actor,
    Client,
    DocState,
    DocType,
    Document,
    EmploymentSource,
    Employment,
    Event,
    FilingStatus,
    HumanOverride,
    Person,
    Requirement,
    Role,
)

bp = Blueprint("main", __name__)
EXTRACTOR = TieredExtractor()

_OVERRIDES = {"waive": HumanOverride.WAIVED, "remove": HumanOverride.REMOVED,
              "pin": HumanOverride.PINNED, "unset": HumanOverride.NONE}


def _matched_filename(req: Requirement) -> str | None:
    for link in req.links:
        if link.active and link.document.state is DocState.MATCHED:
            return link.document.original_filename
    return None


def _row(req: Requirement) -> dict:
    return {"req": req, "status": status_of(req), "filename": _matched_filename(req)}


@bp.get("/")
def index():
    with SessionLocal() as s:
        clients = s.query(Client).all()
        return render_template("clients.html", clients=clients)


@bp.get("/clients/new")
def new_client_form():
    return render_template("new_client.html", roles=list(Role),
                           filing_statuses=list(FilingStatus))


@bp.post("/clients")
def create_client():
    name = (request.form.get("name") or "").strip()
    if not name:
        return redirect(url_for("main.new_client_form"))
    with SessionLocal() as s:
        client = Client(name=name, tax_year=int(request.form.get("tax_year") or 2025),
                        filing_status=FilingStatus[request.form["filing_status"]])
        s.add(client)
        for i in range(6):                       # up to 6 people; blank rows ignored
            pname = (request.form.get(f"person_name_{i}") or "").strip()
            if not pname:
                continue
            person = Person(name=pname, role=Role[request.form.get(f"person_role_{i}", "DEPENDENT")])
            client.people.append(person)
            for _ in range(int(request.form.get(f"person_jobs_{i}") or 0)):
                person.employments.append(Employment(tax_year=client.tax_year,
                                                     source=EmploymentSource.DISCLOSED))
        s.commit()
        run_derivation(s, client, "initial derivation")
        cid = client.id
    return redirect(url_for("main.client_page", cid=cid))


@bp.get("/client/<int:cid>")
def client_page(cid):
    with SessionLocal() as s:
        client = s.get(Client, cid) or abort(404)
        reqs = visible_requirements(s, client)
        rows = [_row(r) for r in reqs]
        outstanding = [r for r in reqs if status_of(r) == OUTSTANDING]
        return render_template(
            "client.html",
            client=client,
            rows=rows,
            summary=client_summary(s, client),
            attention=attention_documents(s, client),
            outstanding=outstanding,
            people=client.people,
        )


@bp.post("/client/<int:cid>/documents")
def upload(cid):
    file = request.files.get("file")
    if not file or not file.filename:
        return redirect(url_for("main.client_page", cid=cid))
    updir = Path(current_app.config["UPLOAD_DIR"])
    updir.mkdir(parents=True, exist_ok=True)
    dest = updir / file.filename
    file.save(dest)
    with SessionLocal() as s:
        client = s.get(Client, cid) or abort(404)
        ingest(s, client, str(dest), file.filename, EXTRACTOR)
    return redirect(url_for("main.client_page", cid=cid))


@bp.post("/requirements/<int:rid>/<action>")
def override(rid, action):
    if action not in _OVERRIDES:
        abort(400)
    with SessionLocal() as s:
        req = s.get(Requirement, rid) or abort(404)
        req.human_override = _OVERRIDES[action]
        s.add(Event(client_id=req.client_id, actor=Actor.ACCOUNTANT, verb=action,
                    payload_json={"requirement_id": rid}))
        s.commit()
        cid = req.client_id
    return redirect(url_for("main.client_page", cid=cid))


@bp.post("/client/<int:cid>/requirements")
def add_req(cid):
    with SessionLocal() as s:
        client = s.get(Client, cid) or abort(404)
        pid = request.form.get("person_id")
        add_requirement(s, client, DocType[request.form["doc_type"]],
                        person_id=int(pid) if pid else None,
                        tax_year=int(request.form["tax_year"]) if request.form.get("tax_year") else None,
                        slot_index=int(request.form.get("slot_index", 0)),
                        note=request.form.get("note"))
    return redirect(url_for("main.client_page", cid=cid))


@bp.post("/documents/<int:did>/review")
def review(did):
    action = request.form.get("action")
    with SessionLocal() as s:
        doc = s.get(Document, did) or abort(404)
        client = s.get(Client, doc.client_id)
        if action == "accept":
            req = s.get(Requirement, int(request.form["requirement_id"]))
            accept(s, client, doc, req)
        elif action == "reject":
            reject(s, client, doc)
        elif action == "reassign":
            year = request.form.get("tax_year")
            reassign(s, client, doc, person_name=request.form.get("person_name") or None,
                     tax_year=int(year) if year else None)
        cid = doc.client_id
    return redirect(url_for("main.client_page", cid=cid))


@bp.post("/client/<int:cid>/rederive")
def rederive(cid):
    with SessionLocal() as s:
        client = s.get(Client, cid) or abort(404)
        pid, employer = request.form.get("late_person_id"), request.form.get("late_employer")
        if pid and employer:
            s.add(Employment(person_id=int(pid), tax_year=client.tax_year,
                             employer_name=employer, source=EmploymentSource.LATE_DISCLOSURE))
            s.commit()
        run_derivation(s, client, request.form.get("reason") or "manual re-derive")
    return redirect(url_for("main.client_page", cid=cid))
