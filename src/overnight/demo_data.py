"""Synthetic marketing-campaign warehouse with deliberately planted data defects.

Everything here is generated from a fixed seed: no real customers, no real company.
The planted defects are the ground truth for the agent's hypothesis checks.
"""

from __future__ import annotations

import random
from datetime import date, timedelta
from pathlib import Path

import duckdb

SEED = 42
CAMPAIGNS = [
    # id, name, channel, start, days
    (101, "Autumn data bundle", "sms", date(2026, 9, 1), 30),
    (102, "Roaming pass promo", "push", date(2026, 9, 10), 21),
    (103, "Family plan upsell", "email", date(2026, 9, 15), 28),
    (104, "Win-back October", "sms", date(2026, 10, 1), 14),
]

# Ground truth: which defects are planted where.
PLANTED = {
    "duplicate_responses": 102,  # same response row inserted twice
    "control_leakage": 103,  # customers present in both treatment and control
    "response_before_contact": 104,  # responses dated before the contact date
}


def build(db_path: Path, seed: int = SEED) -> Path:
    rnd = random.Random(seed)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    con = duckdb.connect(str(db_path))
    con.execute(
        "CREATE TABLE campaigns(campaign_id INT, name TEXT, channel TEXT,"
        " start_date DATE, end_date DATE)"
    )
    con.execute(
        "CREATE TABLE contacts(customer_id INT, campaign_id INT, grp TEXT, contact_date DATE)"
    )
    con.execute(
        "CREATE TABLE responses(customer_id INT, campaign_id INT, response_date DATE,"
        " revenue DECIMAL(10,2))"
    )
    contacts: list[tuple[int, int, str, date]] = []
    responses: list[tuple[int, int, date, float]] = []
    for cid, name, channel, start, days in CAMPAIGNS:
        con.execute(
            "INSERT INTO campaigns VALUES (?, ?, ?, ?, ?)",
            [cid, name, channel, start, start + timedelta(days=days)],
        )
        base = cid * 10_000
        for i in range(1000):
            grp = "control" if i % 10 == 0 else "treatment"
            cdate = start + timedelta(days=rnd.randrange(days))
            contacts.append((base + i, cid, grp, cdate))
            p = 0.08 if grp == "treatment" else 0.05
            if rnd.random() < p:
                rdate = cdate + timedelta(days=rnd.randrange(1, 10))
                responses.append((base + i, cid, rdate, round(rnd.uniform(3, 40), 2)))

    # --- planted defects -------------------------------------------------------
    dup = [r for r in responses if r[1] == PLANTED["duplicate_responses"]][:15]
    responses.extend(dup)
    leak_cid = PLANTED["control_leakage"]
    leaked = [c for c in contacts if c[1] == leak_cid and c[2] == "treatment"][:25]
    contacts.extend((c[0], c[1], "control", c[3]) for c in leaked)
    early_cid = PLANTED["response_before_contact"]
    contact_date = {(c[0], c[1]): c[3] for c in contacts}
    fixed: list[tuple[int, int, date, float]] = []
    moved = 0
    for r in responses:
        if r[1] == early_cid and moved < 12:
            r = (r[0], r[1], contact_date[(r[0], r[1])] - timedelta(days=3), r[3])
            moved += 1
        fixed.append(r)

    con.executemany("INSERT INTO contacts VALUES (?, ?, ?, ?)", contacts)
    con.executemany("INSERT INTO responses VALUES (?, ?, ?, ?)", fixed)
    con.close()
    return db_path
