"""Server-rendered UI (docs/06 §3–4). Routes are thin: they delegate to the domain layer."""
from __future__ import annotations

from pathlib import Path

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)

from app.db import SessionLocal
from app.domain.classifier import TieredExtractor
from app.domain.matching import (
    accept,
    add_requirement,
    can_accept,
    ingest,
    reassign,
    reject,
)
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
    flash(f"Client “{name}” created. Here's the document checklist.", "ok")
    return redirect(url_for("main.client_page", cid=cid))


@bp.get("/client/<int:cid>")
def client_page(cid):
    with SessionLocal() as s:
        client = s.get(Client, cid) or abort(404)
        reqs = visible_requirements(s, client)
        rows = [_row(r) for r in reqs]
        outstanding = [r for r in reqs if status_of(r) == OUTSTANDING]
        attention = attention_documents(s, client)
        # Only offer valid target rows for each file (suggestion.md #1).
        accept_options = {d.id: [r for r in outstanding if can_accept(d, r, client)]
                          for d in attention}
        return render_template(
            "client.html",
            client=client,
            rows=rows,
            summary=client_summary(s, client),
            attention=attention,
            accept_options=accept_options,
            outstanding=outstanding,
            people=client.people,
            doc_types=[DocType.W2, DocType.F1040, DocType.ID],
        )


@bp.post("/client/<int:cid>/documents")
def upload(cid):
    files = [f for f in request.files.getlist("file") if f and f.filename]
    if not files:
        return redirect(url_for("main.client_page", cid=cid))
    updir = Path(current_app.config["UPLOAD_DIR"])
    updir.mkdir(parents=True, exist_ok=True)
    matched = review = 0
    with SessionLocal() as s:
        client = s.get(Client, cid) or abort(404)
        for file in files:
            dest = updir / file.filename
            file.save(dest)
            doc = ingest(s, client, str(dest), file.filename, EXTRACTOR)
            if doc.state is DocState.MATCHED:
                matched += 1
            else:
                review += 1
    msg = f"Uploaded {len(files)} file(s): {matched} filed automatically"
    msg += f", {review} need your review below." if review else "."
    flash(msg, "warn" if review else "ok")
    return redirect(url_for("main.client_page", cid=cid))


@bp.post("/requirements/<int:rid>/<action>")
def override(rid, action):
    if action not in _OVERRIDES:
        abort(400)
    from app.labels import doc_name
    with SessionLocal() as s:
        req = s.get(Requirement, rid) or abort(404)
        req.human_override = _OVERRIDES[action]
        s.add(Event(client_id=req.client_id, actor=Actor.ACCOUNTANT, verb=action,
                    payload_json={"requirement_id": rid}))
        s.commit()
        cid = req.client_id
        label = doc_name(req.doc_type.value, req.slot_index)
    flash({"waive": f"Marked “{label}” as not needed.",
           "pin": f"Marked “{label}” as required.",
           "remove": f"Removed “{label}”.",
           "unset": f"Restored “{label}”."}[action], "ok")
    return redirect(url_for("main.client_page", cid=cid))


@bp.post("/client/<int:cid>/requirements")
def add_req(cid):
    with SessionLocal() as s:
        client = s.get(Client, cid) or abort(404)
        pid = request.form.get("person_id")
        add_requirement(s, client, DocType[request.form["doc_type"]],
                        person_id=int(pid) if pid else None,
                        tax_year=int(request.form["tax_year"]) if request.form.get("tax_year") else None,
                        slot_index=None,            # auto-pick a free slot
                        note=request.form.get("note") or None)
    flash("Added a document to the checklist.", "ok")
    return redirect(url_for("main.client_page", cid=cid))


@bp.post("/documents/<int:did>/review")
def review(did):
    from app.labels import doc_name
    action = request.form.get("action")
    with SessionLocal() as s:
        doc = s.get(Document, did) or abort(404)
        client = s.get(Client, doc.client_id)
        cid = doc.client_id
        if action == "accept":
            req = s.get(Requirement, int(request.form["requirement_id"]))
            if req is None or not can_accept(doc, req, client):
                flash("That file doesn't match that row — try “Change person/year” instead.", "err")
            else:
                accept(s, client, doc, req)
                who = req.person.name + " — " if req.person else ""
                flash(f"Filed “{doc.original_filename}” under {who}{doc_name(req.doc_type.value, req.slot_index)}.", "ok")
        elif action == "reject":
            reject(s, client, doc)
            flash(f"Removed “{doc.original_filename}” from this client.", "ok")
        elif action == "reassign":
            year = request.form.get("tax_year")
            reassign(s, client, doc, person_name=request.form.get("person_name") or None,
                     tax_year=int(year) if year else None)
            if doc.state is DocState.MATCHED:
                flash(f"Updated and filed “{doc.original_filename}”.", "ok")
            else:
                flash(f"Updated “{doc.original_filename}”, but it still needs review — "
                      "the person or year may not match an expected document.", "warn")
    return redirect(url_for("main.client_page", cid=cid))


@bp.post("/client/<int:cid>/rederive")
def rederive(cid):
    with SessionLocal() as s:
        client = s.get(Client, cid) or abort(404)
        pid, employer = request.form.get("late_person_id"), request.form.get("late_employer")
        who = None
        if pid and employer:
            person = s.get(Person, int(pid))
            who = person.name if person else None
            s.add(Employment(person_id=int(pid), tax_year=client.tax_year,
                             employer_name=employer, source=EmploymentSource.LATE_DISCLOSURE))
            s.commit()
        run = run_derivation(s, client, request.form.get("reason") or "manual re-derive")
        added = run.summary_json.get("added", 0)
    if who and added:
        flash(f"Checklist updated for {who} — {added} new document(s) added.", "ok")
    elif added:
        flash(f"Checklist updated — {added} new document(s) added.", "ok")
    else:
        flash("Checklist re-checked — no changes needed.", "ok")
    return redirect(url_for("main.client_page", cid=cid))
