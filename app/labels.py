"""
Plain-language helpers (docs/07). Keeps every system term out of the UI — templates call
these instead of showing raw enum values.
"""
from __future__ import annotations

STATUS_LABEL = {"received": "Received", "outstanding": "Still needed",
                "not_needed": "Not needed", "obsolete": "Inactive"}

FILING_LABEL = {"single": "Single", "married_joint": "Married — filing jointly",
                "married_separate": "Married — filing separately",
                "head_of_household": "Head of household"}

ROLE_LABEL = {"taxpayer": "Taxpayer", "spouse": "Spouse", "dependent": "Child / dependent"}


def doc_name(doc_type_value: str, slot_index: int = 0) -> str:
    if doc_type_value == "W2":
        return f"W-2 — job {slot_index + 1}"
    if doc_type_value == "1040":
        return "Last year's tax return (1040)"
    if doc_type_value == "ID":
        return "Government ID"
    return doc_type_value


def why_text(doc, client) -> str:
    """One friendly sentence explaining why a file needs the accountant's attention."""
    reason = doc.exception_reason.value if doc.exception_reason else None
    if reason == "unreadable":
        return "We couldn't read this file — it may be a photo, a blank page, or a bad scan."
    if reason == "wrong_year":
        year, kind = doc.guess_year, (doc.guess_type.value if doc.guess_type else None)
        if kind == "W2":
            return f"This looks like a {year} W-2, but we need a {client.tax_year} W-2."
        if kind == "1040":
            return (f"This looks like a {year} tax return, "
                    f"but we need last year's return ({client.tax_year - 1}).")
        return f"This looks like a {year} document, but we need {client.tax_year}."
    if reason == "unknown_person":
        who = doc.guess_person_name or "the name on this file"
        return f"“{who}” isn't one of this client's people."
    if reason == "unexpected_extra":
        return "This looks like an extra one — everything expected is already in."
    return "The tool wasn't sure about this file. Please tell it what to do."


def register(app):
    """Expose the helpers to every template."""
    @app.context_processor
    def _inject():
        return dict(doc_name=doc_name, why_text=why_text,
                    STATUS_LABEL=STATUS_LABEL, FILING_LABEL=FILING_LABEL,
                    ROLE_LABEL=ROLE_LABEL)
