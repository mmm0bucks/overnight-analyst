from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from overnight.sqlguard import SQLRejected, validate


@pytest.mark.parametrize("q", [
    "SELECT 1", "with t as (select 1) select * from t", "DESCRIBE contacts",
    "SELECT * FROM t WHERE note = 'please delete me'",  # keyword inside a string is fine
    "SELECT updated_at FROM t",  # identifier containing a keyword is fine
])
def test_allows_read_queries(q: str) -> None:
    validate(q)


@pytest.mark.parametrize("q", [
    "DELETE FROM contacts", "DROP TABLE contacts", "INSERT INTO t VALUES (1)",
    "SELECT 1; DROP TABLE contacts", "ATTACH 'x.db'", "COPY contacts TO 'out.csv'",
    "SELECT * FROM read_csv('/etc/passwd')", "SELECT * FROM glob('*')",
    "/* SELECT */ DELETE FROM contacts", "PRAGMA database_list", "", "   ;  ",
    "SELECT 1 FROM t -- \n; DELETE FROM t",
])
def test_rejects_dangerous(q: str) -> None:
    with pytest.raises(SQLRejected):
        validate(q)


def test_adds_limit_when_missing() -> None:
    assert validate("SELECT * FROM t", max_rows=50).endswith("LIMIT 50")


def test_rejects_limit_above_cap() -> None:
    with pytest.raises(SQLRejected):
        validate("SELECT * FROM t LIMIT 5000", max_rows=1000)


def test_second_layer_read_only_connection(tmp_path: Path) -> None:
    db = tmp_path / "x.duckdb"
    duckdb.connect(str(db)).execute("CREATE TABLE t(a INT)").close()
    con = duckdb.connect(str(db), read_only=True)
    with pytest.raises(duckdb.Error):
        con.execute("INSERT INTO t VALUES (1)")  # even if the guard were bypassed
    con.close()
