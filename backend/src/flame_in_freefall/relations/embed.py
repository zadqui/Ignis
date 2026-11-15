"""Local CPU embeddings (multilingual-e5-small, pinned revision). Used ONLY to retrieve candidates.

e5 input procedure (model card): every text is prefixed ("query: " for symmetric similarity), token embeddings
are averaged over the attention mask and L2-normalised. Vectors are cached by (model, revision, prefix, text).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Protocol


class Embedder(Protocol):
    model_id: str

    def encode(self, texts: list[str]) -> list[list[float]]: ...


def embedder_id(cfg: dict[str, Any]) -> str:
    e = cfg["embedding"]
    return f"{e['model']}@{e['revision']}:{e['pooling']}:prefix={e['prefix'].strip()}"


class E5Embedder:
    def __init__(self, cfg: dict[str, Any], *, local_files_only: bool = False, cache_dir: Path | None = None):
        import torch
        from transformers import AutoModel, AutoTokenizer

        e = cfg["embedding"]
        self.model_id, self.prefix, self.max_length = embedder_id(cfg), e["prefix"], int(e["max_length"])
        self.tok = AutoTokenizer.from_pretrained(e["model"], revision=e["revision"], local_files_only=local_files_only,
                                                 cache_dir=cache_dir)
        self.model = AutoModel.from_pretrained(e["model"], revision=e["revision"], dtype=torch.float32,
                                               local_files_only=local_files_only, cache_dir=cache_dir).eval()
        self.torch = torch

    def encode(self, texts: list[str], prefix: str | None = None) -> list[list[float]]:
        """``prefix`` overrides the configured one (similarity evaluation only)."""
        pre = self.prefix if prefix is None else prefix
        out: list[list[float]] = []
        with self.torch.inference_mode():
            for i in range(0, len(texts), 32):
                batch = [pre + t for t in texts[i:i + 32]]
                enc = self.tok(batch, max_length=self.max_length, padding=True, truncation=True, return_tensors="pt")
                h = self.model(**enc).last_hidden_state
                mask = enc["attention_mask"].unsqueeze(-1).to(h.dtype)
                v = (h * mask).sum(1) / mask.sum(1)
                v = self.torch.nn.functional.normalize(v, p=2, dim=1)
                out.extend(v.tolist())
        return out


class CachedEmbedder:
    def __init__(self, inner: Embedder, cache_dir: Path):
        self.inner, self.model_id = inner, inner.model_id
        cache_dir.mkdir(parents=True, exist_ok=True)
        self.path = cache_dir / (hashlib.sha256(self.model_id.encode()).hexdigest()[:16] + ".jsonl")
        self.cache: dict[str, list[float]] = {}
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    r = json.loads(line)
                    self.cache[r["h"]] = r["v"]

    @staticmethod
    def key(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]

    def encode(self, texts: list[str]) -> list[list[float]]:
        todo = sorted({t for t in texts if self.key(t) not in self.cache})
        if todo:
            vecs = self.inner.encode(todo)
            with self.path.open("a", encoding="utf-8") as fh:
                for t, v in zip(todo, vecs):
                    self.cache[self.key(t)] = [round(x, 6) for x in v]
                    fh.write(json.dumps({"h": self.key(t), "v": self.cache[self.key(t)]}) + "\n")
        return [self.cache[self.key(t)] for t in texts]


def cosine(a: list[float], b: list[float]) -> float:
    return float(sum(x * y for x, y in zip(a, b)))  # vectors are L2-normalised
