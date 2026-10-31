from __future__ import annotations

import json
from pathlib import Path

from conftest import TODAY

from overnight.evaluate import rag_summary
from overnight.rag import HashEmbedder, WikiIndex, chunk_pages
from overnight.tools import Toolbox


def test_pages_are_chunked_by_section(ws: Path) -> None:
    chunks = chunk_pages(ws / "wiki")
    att = [c for c in chunks if c.page == "response-attribution"]
    assert [c.text.splitlines()[0] for c in att] == ["## Window", "## Deduplication",
                                                    "## Overlapping campaigns"]


def test_bm25_finds_exact_terms(ws: Path) -> None:
    index = WikiIndex(chunk_pages(ws / "wiki"), HashEmbedder())
    assert index.search("VAT rubles", k=1, mode="bm25")[0].page == "revenue-metrics"
    assert index.search("cvm_daily_load", k=1, mode="hybrid")[0].page == "etl-schedule"


def test_search_wiki_is_a_traceable_source(ws: Path) -> None:
    box = Toolbox(ws, TODAY)
    out = json.loads(box.call(["search_wiki"], "search_wiki", {"query": "holdout size"}))
    assert out["source"] == "S1"
    assert "control-group-policy" in [hit["page"] for hit in out["result"]]


def test_rag_summary_reports_all_modes(ws: Path) -> None:
    text = rag_summary(ws, HashEmbedder())
    assert "| bm25 |" in text and "| dense |" in text and "| hybrid |" in text


def test_http_embedder_batches_and_counts_tokens() -> None:
    import httpx

    from overnight.rag import HttpEmbedder

    calls: list[dict[str, object]] = []

    def handler(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content)
        calls.append(body)
        data = [{"index": i, "embedding": [float(i), 1.0]} for i in range(len(body["input"]))]
        return httpx.Response(200, json={"data": data[::-1], "usage": {"total_tokens": 7}})

    emb = HttpEmbedder("https://e.test/v1", "k", transport=httpx.MockTransport(handler))
    vectors = emb.embed([f"t{i}" for i in range(40)])
    assert [len(c["input"]) for c in calls] == [32, 8]  # type: ignore[arg-type]
    assert calls[0]["model"] == "bge-m3"
    assert vectors[1] == [1.0, 1.0]  # order restored by "index"
    assert emb.tokens == 14
