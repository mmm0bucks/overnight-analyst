from __future__ import annotations

from pathlib import Path

from overnight.publisher import BEGIN, END, atomic_write, redact, upsert_managed_block


def test_managed_block_preserves_human_text() -> None:
    human = f"# Mine\n\nmy notes\n\n{BEGIN}\nold\n{END}\n\nmore of my notes\n"
    out = upsert_managed_block(human, "new", "t")
    assert "my notes" in out and "more of my notes" in out
    assert "new" in out and "old" not in out


def test_managed_block_appended_when_markers_absent() -> None:
    out = upsert_managed_block("# Mine\nhello\n", "gen", "t")
    assert out.startswith("# Mine\nhello") and out.rstrip().endswith(END)


def test_redacts_secrets() -> None:
    text = "key sk-abcdefghijklmnopqrstu and api_key=12345 and Bearer abcdefghijklmnopqrst"
    out = redact(text)
    assert "sk-abc" not in out and "12345" not in out and "Bearer abc" not in out


def test_atomic_write_backs_up_previous(tmp_path: Path) -> None:
    f = tmp_path / "n.md"
    atomic_write(f, "v1")
    atomic_write(f, "v2", backup_dir=tmp_path / "bak")
    assert f.read_text() == "v2"
    assert (tmp_path / "bak" / "n.md").read_text() == "v1"
    assert not list(tmp_path.glob("*.tmp"))
