"""Hybrid search over the wiki: BM25 + dense vectors in Qdrant, fused with RRF.

Chunks are the "## " sections of each page. Dense vectors come from an
OpenAI-compatible /embeddings endpoint (default model bge-m3, multilingual) or,
offline and in CI, from a deterministic hashing embedder that is NOT semantic
(it only tests the plumbing).
"""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import httpx
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

RRF_K = 60


@dataclass(frozen=True)
class Chunk:
    page: str
    title: str
    text: str


class Embedder(Protocol):
    tokens: int  # spent so far, for the key's budget

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class HashEmbedder:
    """Bag of hashed words. Deterministic, dependency-free, not semantic."""

    dim, tokens = 256, 0

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for t in texts:
            v = [0.0] * self.dim
            for w in tokens(t):
                v[int(hashlib.md5(w.encode()).hexdigest(), 16) % self.dim] += 1.0
            n = math.sqrt(sum(x * x for x in v)) or 1.0
            out.append([x / n for x in v])
        return out


class HttpEmbedder:
    """OpenAI-compatible POST /embeddings, e.g. bge-m3 at neuraldeep (no prefixes needed)."""

    def __init__(self, base_url: str, api_key: str, model: str = "bge-m3",
                 transport: httpx.BaseTransport | None = None) -> None:
        self.model, self.tokens = model, 0
        self.http = httpx.Client(base_url=base_url, timeout=60, transport=transport,
                                 headers={"Authorization": f"Bearer {api_key}"})

    def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), 32):  # stays far below the provider's request size limit
            r = self.http.post("/embeddings", json={"model": self.model, "input": texts[i:i + 32]})
            r.raise_for_status()
            data = r.json()
            self.tokens += int((data.get("usage") or {}).get("total_tokens", 0))
            out += [d["embedding"] for d in sorted(data["data"], key=lambda d: d["index"])]
        return out


def tokens(text: str) -> list[str]:
    return re.findall(r"\w+", text.lower())


def chunk_pages(wiki: Path) -> list[Chunk]:
    chunks = []
    for path in sorted(wiki.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        title = text.splitlines()[0].lstrip("# ").strip() if text else path.stem
        for section in re.split(r"\n(?=## )", text):
            body = section.strip()
            if body and not (body.startswith("# ") and "\n" not in body):  # skip title-only
                chunks.append(Chunk(path.stem, title, body))
    return chunks


class WikiIndex:
    def __init__(self, chunks: list[Chunk], embedder: Embedder) -> None:
        self.chunks, self.embedder = chunks, embedder
        # BM25 statistics
        self.docs = [tokens(f"{c.title} {c.text}") for c in chunks]
        self.avg_len = sum(map(len, self.docs)) / max(len(self.docs), 1)
        df = Counter(w for d in self.docs for w in set(d))
        n = len(self.docs)
        self.idf = {w: math.log(1 + (n - f + 0.5) / (f + 0.5)) for w, f in df.items()}
        self.tf = [Counter(d) for d in self.docs]
        # dense vectors in an in-memory Qdrant collection
        vectors = embedder.embed([f"{c.title}\n{c.text}" for c in chunks])
        self.qdrant = QdrantClient(":memory:")
        self.qdrant.create_collection("wiki", vectors_config=VectorParams(
            size=len(vectors[0]), distance=Distance.COSINE))
        self.qdrant.upsert("wiki", points=[PointStruct(id=i, vector=v)
                                           for i, v in enumerate(vectors)])

    def bm25(self, query: str, k: int, k1: float = 1.5, b: float = 0.75) -> list[int]:
        q = tokens(query)
        scores = []
        for i, (tf, doc) in enumerate(zip(self.tf, self.docs, strict=True)):
            norm = k1 * (1 - b + b * len(doc) / self.avg_len)
            s = sum(self.idf.get(w, 0) * tf[w] * (k1 + 1) / (tf[w] + norm) for w in q if w in tf)
            scores.append((s, i))
        return [i for s, i in sorted(scores, reverse=True)[:k] if s > 0]

    def dense(self, query: str, k: int) -> list[int]:
        vector = self.embedder.embed([query])[0]
        hits = self.qdrant.query_points("wiki", query=vector, limit=k).points
        return [int(h.id) for h in hits]

    def search(self, query: str, k: int = 4, mode: str = "hybrid") -> list[Chunk]:
        if mode == "bm25":
            ids = self.bm25(query, k)
        elif mode == "dense":
            ids = self.dense(query, k)
        else:  # reciprocal rank fusion of both lists
            fused: dict[int, float] = {}
            for ranking in (self.bm25(query, 20), self.dense(query, 20)):
                for rank, i in enumerate(ranking):
                    fused[i] = fused.get(i, 0.0) + 1 / (RRF_K + rank + 1)
            ids = sorted(fused, key=fused.__getitem__, reverse=True)[:k]
        return [self.chunks[i] for i in ids]
