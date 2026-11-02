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


def test_hard_hypotheses_ground_truth(tmp_path: Path) -> None:
    """expected.json for the hard cases is checked against the data, not trusted."""
    db = demo_data.build(tmp_path / "w.duckdb")
    dup = ("SELECT customer_id, campaign_id, response_date, revenue FROM responses "
           "GROUP BY ALL HAVING count(*) > 1")
    assert 101 not in _campaigns_with(db, dup)  # H6 rejected: duplicates live in 102 only
    late = ("SELECT r.campaign_id FROM responses r JOIN campaigns c USING (campaign_id) "
            "WHERE r.response_date > c.end_date + INTERVAL 30 DAY")
    assert _campaigns_with(db, late) == {demo_data.PLANTED["late_response"]}  # H7 confirmed
    same_grp = ("SELECT customer_id, campaign_id FROM contacts GROUP BY customer_id, "
                "campaign_id, grp HAVING count(*) > 1")
    assert _campaigns_with(db, same_grp) == set()  # H9 rejected...
    naive = ("SELECT customer_id, campaign_id FROM contacts GROUP BY 1, 2 "
             "HAVING count(*) > 1")
    assert _campaigns_with(db, naive) == {103}  # ...though its suggested_sql finds rows
