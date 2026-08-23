"""
Seed the Rivera household in its **January** state — before Luis's June job change is known.

This is the starting point the demo works from: the system will first derive a list assuming
Luis has one job; later a late-disclosure employment row is added and we re-derive (M2/M3).

Run:  ./venv/Scripts/python.exe scripts/seed.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # allow `python scripts/seed.py`

from app.config import Config
from app.db import SessionLocal, init_engine
from app.models import (
    Client,
    Employment,
    EmploymentSource,
    FilingStatus,
    Person,
    Role,
)


def seed_rivera(session) -> Client:
    client = Client(name="Rivera household", tax_year=2025,
                    filing_status=FilingStatus.MARRIED_JOINT)
    ana = Person(name="Ana Rivera", role=Role.TAXPAYER)
    luis = Person(name="Luis Rivera", role=Role.SPOUSE)
    mateo = Person(name="Mateo Rivera", role=Role.DEPENDENT)
    client.people = [ana, luis, mateo]

    # Last year's filing → baseline expectation for this year (docs/04 §1):
    #   Ana had 2 jobs, Luis had 1. Luis's June change is NOT known yet (January state).
    ana.employments = [
        Employment(tax_year=2025, employer_name="Northwind Traders",
                   source=EmploymentSource.PRIOR_YEAR),
        Employment(tax_year=2025, employer_name="Contoso Ltd",
                   source=EmploymentSource.PRIOR_YEAR),
    ]
    luis.employments = [
        Employment(tax_year=2025, employer_name="Fabrikam Inc",
                   source=EmploymentSource.PRIOR_YEAR),
    ]

    session.add(client)
    session.commit()
    return client


def main() -> None:
    init_engine(Config.DATABASE_URL, create_all=True)
    with SessionLocal() as session:
        existing = session.query(Client).filter_by(name="Rivera household").one_or_none()
        if existing:
            print(f"Rivera household already seeded (client id={existing.id}).")
            return
        client = seed_rivera(session)
        print(f"Seeded '{client.name}' (id={client.id}, TY{client.tax_year}) with "
              f"{len(client.people)} people in January state.")


if __name__ == "__main__":
    main()
