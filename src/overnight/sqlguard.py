"""Read-only SQL guard.

Defense in depth, layer 1 of 2: a lexical validator. Layer 2 is opening DuckDB with
``read_only=True``. Neither layer trusts the other; tests cover both.
"""

from __future__ import annotations

import re

ALLOWED_FIRST = {"select", "with", "show", "describe", "explain"}
FORBIDDEN_WORDS = {
    "insert", "update", "delete", "drop", "alter", "create", "replace", "truncate",
    "attach", "detach", "copy", "export", "import", "install", "load", "pragma",
    "set", "call", "checkpoint", "vacuum", "grant", "revoke",
}
# Table functions that can read arbitrary files from disk.
FORBIDDEN_FUNCS = re.compile(r"\b(read_\w+|glob|sniff_csv|parquet_\w+)\s*\(", re.I)
LIMIT_RE = re.compile(r"\blimit\s+(\d+)\s*$", re.I)


class SQLRejected(ValueError):
    pass


def _strip(sql: str) -> str:
    sql = re.sub(r"--[^\n]*", " ", sql)
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.S)
    return " ".join(sql.split()).strip().rstrip(";").strip()


def validate(sql: str, max_rows: int = 1000) -> str:
    """Return a normalized, safe query or raise ``SQLRejected``."""
    q = _strip(sql)
    if not q:
        raise SQLRejected("empty query")
    if ";" in q:
        raise SQLRejected("only a single statement is allowed")
    no_strings = re.sub(r"'(?:[^']|'')*'", "''", q)
    first = no_strings.split(" ", 1)[0].lower()
    if first not in ALLOWED_FIRST:
        raise SQLRejected(f"statement type not allowed: {first.upper()}")
    words = set(re.findall(r"[a-z_]+", no_strings.lower()))
    bad = sorted(words & FORBIDDEN_WORDS)
    if bad:
        raise SQLRejected(f"forbidden keyword(s): {', '.join(bad)}")
    if FORBIDDEN_FUNCS.search(no_strings):
        raise SQLRejected("file-reading table functions are not allowed")
    if first in {"select", "with"}:
        m = LIMIT_RE.search(q)
        if m is None:
            q = f"{q} LIMIT {max_rows}"
        elif not 1 <= int(m.group(1)) <= max_rows:
            raise SQLRejected(f"LIMIT must be between 1 and {max_rows}")
    return q
