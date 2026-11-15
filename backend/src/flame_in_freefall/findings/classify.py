"""Sentence classifiers for candidate selection.

A classifier returns one score per label in ``LABELS`` for each sentence.
Scores for *every* classified sentence are stored (not only the passing ones),
so the threshold can be re-calibrated against the reference set without
re-running the model. Results are cached on disk by (classifier_id, text hash).
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Protocol

from .schemas import LABELS

log = logging.getLogger(__name__)

# Hypotheses are part of the classifier identity: changing one changes classifier_id.
HYPOTHESES: dict[str, str] = {
    "result": "This sentence reports an experimental, observed or measured result.",
    "method": "This sentence describes an experimental method, apparatus, procedure or test setup.",
    "motivation": "This sentence gives background, motivation or the purpose of a study.",
    "future_work": "This sentence proposes future work, an open question or a recommendation for further research.",
    "limitation": "This sentence describes a limitation, an uncertainty or a problem with the data or the experiment.",
    "other": "This sentence is administrative, a caption, a list item or otherwise not scientific content.",
}
HYPOTHESES_VERSION = hashlib.sha256(json.dumps(HYPOTHESES, sort_keys=True).encode()).hexdigest()[:8]

DEFAULT_NLI_MODEL = "MoritzLaurer/deberta-v3-base-zeroshot-v2.0"


class Classifier(Protocol):
    classifier_id: str

    def scores(self, texts: list[str]) -> list[dict[str, float]]: ...


class NullClassifier:
    """Passes everything; used to build units without a model (scores are null)."""

    classifier_id = "none"

    def scores(self, texts: list[str]) -> list[dict[str, float]]:
        return [{} for _ in texts]


METHOD = "softmax_entailment_across_labels"
MAX_LENGTH = 256


def classifier_spec(model: str = DEFAULT_NLI_MODEL, revision: str | None = None) -> dict:
    """Everything that defines the scores; identical locally and on Kaggle."""
    return {"model": model, "revision": revision or "main", "hypotheses": HYPOTHESES, "labels": list(LABELS),
            "method": METHOD, "max_length": MAX_LENGTH,
            "classifier_id": f"nli:{model}@{revision or 'main'}:h{HYPOTHESES_VERSION}:{METHOD}"}


def softmax_scores(entail_logits: list[float]) -> dict[str, float]:
    """Single-label zero-shot: softmax of the entailment logits across the label hypotheses."""
    import math

    m = max(entail_logits)
    ex = [math.exp(x - m) for x in entail_logits]
    z = sum(ex)
    return {lab: round(e / z, 6) for lab, e in zip(LABELS, ex)}


class NliClassifier:
    """Local zero-shot NLI (slow on CPU; the default path computes scores on Kaggle, see kaggle/)."""

    def __init__(self, model: str = DEFAULT_NLI_MODEL, revision: str | None = None, batch_size: int = 32,
                 threads: int | None = None):
        try:
            import torch
            from transformers import AutoModelForSequenceClassification, AutoTokenizer
        except ImportError as e:  # pragma: no cover - optional dependency
            raise RuntimeError("NLI classifier needs the optional group: uv sync --extra nli") from e
        if threads:
            torch.set_num_threads(threads)
        self._torch = torch
        self.tok = AutoTokenizer.from_pretrained(model, revision=revision)
        self.model = AutoModelForSequenceClassification.from_pretrained(model, revision=revision).eval()
        self.entail = next(i for i, lab in self.model.config.id2label.items() if lab.lower().startswith("entail"))
        self.classifier_id = classifier_spec(model, revision)["classifier_id"]
        self.batch_size = batch_size

    def scores(self, texts: list[str]) -> list[dict[str, float]]:
        torch = self._torch
        pairs = [(t, HYPOTHESES[lab]) for t in texts for lab in LABELS]
        logits: list[float] = []
        with torch.inference_mode():
            for i in range(0, len(pairs), self.batch_size):
                chunk = pairs[i : i + self.batch_size]
                enc = self.tok([p[0] for p in chunk], [p[1] for p in chunk], truncation="only_first",
                               max_length=MAX_LENGTH, padding=True, return_tensors="pt")
                logits.extend(self.model(**enc).logits[:, self.entail].tolist())
        n = len(LABELS)
        return [softmax_scores(logits[k * n : (k + 1) * n]) for k in range(len(texts))]


class CacheOnlyClassifier:
    """Reads scores imported from an external run (Kaggle); never computes."""

    def __init__(self, classifier_id: str):
        self.classifier_id = classifier_id

    def scores(self, texts: list[str]) -> list[dict[str, float]]:
        if texts:
            raise MissingScores(len(texts))
        return []


class MissingScores(RuntimeError):
    def __init__(self, n: int):
        super().__init__(f"{n} sentences have no imported scores: run `fif-findings export-classify`, "
                         "classify on Kaggle and `fif-findings import-scores`")
        self.n = n


class CachedClassifier:
    """Disk cache (JSONL, append-only) in front of any classifier."""

    def __init__(self, inner: Classifier, cache_dir: Path):
        self.inner = inner
        self.classifier_id = inner.classifier_id
        safe = hashlib.sha256(self.classifier_id.encode()).hexdigest()[:16]
        cache_dir.mkdir(parents=True, exist_ok=True)
        self.path = cache_dir / f"{safe}.jsonl"
        self._mem: dict[str, dict[str, float]] = {}
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                rec = json.loads(line)
                self._mem[rec["h"]] = rec["s"]
        self.hits = self.misses = 0

    @staticmethod
    def _h(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]

    def scores(self, texts: list[str], progress_every: int = 2000) -> list[dict[str, float]]:
        keys = [self._h(t) for t in texts]
        todo = sorted({k: t for k, t in zip(keys, texts) if k not in self._mem}.items())
        self.hits, self.misses = len(texts) - len(todo), len(todo)
        if todo and isinstance(self.inner, CacheOnlyClassifier):
            raise MissingScores(len(todo))
        if todo and self.inner.classifier_id != "none":
            with self.path.open("a", encoding="utf-8") as fh:
                for i in range(0, len(todo), 256):
                    chunk = todo[i : i + 256]
                    for (k, _), s in zip(chunk, self.inner.scores([t for _, t in chunk])):
                        self._mem[k] = s
                        fh.write(json.dumps({"h": k, "s": s}) + "\n")
                    fh.flush()
                    if (i // 256) % max(1, progress_every // 256) == 0:
                        log.info("classified %d/%d new sentences", min(i + 256, len(todo)), len(todo))
        return [self._mem.get(k, {}) for k in keys]

    def missing(self, texts: list[str]) -> list[tuple[str, str]]:
        return sorted({self._h(t): t for t in texts if self._h(t) not in self._mem}.items())

    def merge(self, scored: dict[str, dict[str, float]]) -> int:
        new = {k: v for k, v in scored.items() if k not in self._mem}
        with self.path.open("a", encoding="utf-8") as fh:
            for k, v in sorted(new.items()):
                self._mem[k] = v
                fh.write(json.dumps({"h": k, "s": v}) + "\n")
        return len(new)
