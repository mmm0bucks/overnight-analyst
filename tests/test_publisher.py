from __future__ import annotations

from pathlib import Path

from overnight.publisher import BEGIN, END, atomic_write, redact, upsert_block


def test_managed_block_keeps_human_text() -> None:
    out = upsert_block(f"# Mine\nmine 1\n{BEGIN}\nold\n{END}\nmine 2\n", "new", "t")
    assert "mine 1" in out and "mine 2" in out and "new" in out and "old" not in out


def test_block_appended_when_markers_absent() -> None:
    out = upsert_block("# Mine\nhello\n", "gen", "t")
    assert out.startswith("# Mine\nhello") and out.rstrip().endswith(END)


def test_redacts_secrets() -> None:
    out = redact("sk-abcdefghijklmnopqrstu api_key=12345 Bearer abcdefghijklmnopqrst")
    assert "sk-abc" not in out and "12345" not in out and "Bearer abc" not in out


def test_atomic_write_backs_up_previous(tmp_path: Path) -> None:
    f = tmp_path / "n.md"
    atomic_write(f, "v1")
    atomic_write(f, "v2", backup_dir=tmp_path / "bak")
    assert f.read_text() == "v2" and (tmp_path / "bak" / "n.md").read_text() == "v1"
    assert not list(tmp_path.glob("*.tmp"))
