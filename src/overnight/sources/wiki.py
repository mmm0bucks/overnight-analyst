"""Read-only access to a folder of markdown pages (stand-in for a team wiki)."""

from __future__ import annotations

from pathlib import Path


class Wiki:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def pages(self) -> list[str]:
        return sorted(p.stem for p in self.root.glob("*.md"))

    def read(self, page: str) -> str:
        path = (self.root / f"{page}.md").resolve()
        if path.parent != self.root or not path.exists():  # blocks ../ traversal
            raise KeyError(f"unknown page: {page}")
        return path.read_text(encoding="utf-8")

    def search(self, query: str) -> list[dict[str, str]]:
        terms = [t.lower() for t in query.split() if t]
        hits = []
        for name in self.pages():
            text = self.read(name)
            low = text.lower()
            if terms and all(t in low for t in terms):
                i = low.find(terms[0])
                hits.append({"page": name, "snippet": text[max(0, i - 80) : i + 160]})
        return hits
