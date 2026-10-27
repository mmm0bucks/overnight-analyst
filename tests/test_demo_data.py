from __future__ import annotations

from pathlib import Path

import duckdb

from overnight import demo_data


def _rows(db: Path, sql: str) -> list[tuple[object, ...]]:
    con = duckdb.connect(str(db), read_only=True)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def test_deterministic(tmp_path: Path) -> None:
    q = "SELECT count(*), sum(revenue)::DOUBLE FROM responses"
    a = demo_data.build(tmp_path / "a.duckdb")
    b = demo_data.build(tmp_path / "b.duckdb")
    assert _rows(a, q) == _rows(b, q)


def _campaigns_with(db: Path, inner: str) -> set[object]:
    return {r[0] for r in _rows(db, f"SELECT DISTINCT campaign_id FROM ({inner})")}


def test_planted_defects_are_exactly_where_we_say(tmp_path: Path) -> None:
    db = demo_data.build(tmp_path / "w.duckdb")
    p = demo_data.PLANTED
    assert _campaigns_with(db, "SELECT customer_id, campaign_id, response_date, revenue "
                               "FROM responses GROUP BY ALL HAVING count(*) > 1") \
        == {p["duplicate_responses"]}
    assert _campaigns_with(db, "SELECT customer_id, campaign_id FROM contacts "
                               "GROUP BY 1, 2 HAVING count(DISTINCT grp) > 1") \
        == {p["control_leakage"]}
    assert _campaigns_with(db, "SELECT r.campaign_id FROM responses r JOIN contacts c "
                               "USING (customer_id, campaign_id) "
                               "WHERE r.response_date < c.contact_date") \
        == {p["response_before_contact"]}
