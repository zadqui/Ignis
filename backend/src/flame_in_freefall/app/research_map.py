"""Knowledge map: turn a text query into clustered, labelled bubbles of the corpus' own documents.

Pipeline (deterministic, standard library only, read-only, public export only):
  1. retrieval   - rank investigations and their publications against the query (bilingual concept expansion)
  2. similarity  - TF-IDF vectors over titles (plus the investigation objective when its licence allows prose)
  3. clustering  - spherical k-means with farthest-first seeding
  4. labelling   - the most distinctive terms of each cluster
  5. layout      - classical MDS of the cluster centroids, so related areas sit closer together

Nothing is fetched from the network: every field comes from the DuckDB export served by this API.
Clusters and labels are computed aids for navigation. They are not scientific classifications.
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict

from fastapi import APIRouter, Query

from . import queries
from .research_language import CONCEPTS, concepts, matches, normalize
from .research_store import require_public

MAP_VERSION = "research-map-1"
router = APIRouter(tags=["Knowledge map"])

STOP = set("""
a an and are as at be been between both but by can could de del did do does during each el en for from had has have
how in into is it its la las los may more most new non not of on one only or other our over than that the their
these this those through to two under upon use used using via was were what when which while with within without
y study studies effect effects investigation investigations experiment experiments experimental result results
analysis based paper report research preliminary overview part some toward towards about after also among
""".split())  # noqa: SIM905 - a word list reads better as text
# Shown to people instead of the raw concept key, and used as topic suggestions.
TOPIC_LABELS = {
    "flame_spread": "propagación de llama", "flammability": "inflamabilidad", "detection": "detección de humo",
    "suppression": "supresión de incendios", "modeling": "modelado y simulación", "smoke": "humo y hollín",
    "safety": "seguridad contra incendios", "extinction": "extinción", "ignition": "ignición",
    "droplet": "combustión de gotas", "oxygen": "oxígeno", "pressure": "presión", "flow": "flujo de aire",
    "pmma": "PMMA (acrílico)", "cellulose": "celulosa", "heptane": "heptano", "methane": "metano",
    "microgravity": "microgravedad", "space_station": "estación espacial",
}
OPEN_ACCESS = {"gold", "green", "hybrid", "bronze", "diamond"}


def stem(token: str) -> str:
    if len(token) > 4 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 4 and token.endswith("s") and not token.endswith(("ss", "us", "is")):
        return token[:-1]
    return token


def words(text: str) -> list[str]:
    """Normalised content tokens, in order. A stop word yields "" so bigrams never bridge it."""
    return [stem(t) if t not in STOP and len(t) > 2 and not t.isdigit() else ""
            for t in re.findall(r"[a-z0-9]+", normalize(text or ""))]


def features(text: str, surface: Counter | None = None) -> Counter:
    raw = re.findall(r"[a-z0-9]+", normalize(text or ""))
    toks = words(text)
    out: Counter = Counter()
    for i, t in enumerate(toks):
        if not t:
            continue
        out[t] += 1
        if surface is not None:
            surface[(t, raw[i])] += 1
        if i + 1 < len(toks) and toks[i + 1]:
            bigram = t + " " + toks[i + 1]
            out[bigram] += 1
            if surface is not None:
                surface[(bigram, raw[i] + " " + raw[i + 1])] += 1
    return out


def unit(vector: dict[str, float]) -> dict[str, float]:
    length = math.sqrt(sum(v * v for v in vector.values())) or 1.0
    return {k: v / length for k, v in vector.items()}


def dot(a: dict[str, float], b: dict[str, float]) -> float:
    if len(a) > len(b):
        a, b = b, a
    return sum(v * b.get(k, 0.0) for k, v in a.items())


# ------------------------------------------------------------------ corpus


def load_documents(con) -> list[dict]:
    """Investigations and their publications, exactly as stored. No text is invented or fetched."""
    views = queries._views(con)
    invs = queries.rows(con, "SELECT inv_id, title, acronym, doi, objective, project_type, start_date_raw "
                        "FROM investigations ORDER BY inv_id")
    prose = set()
    if "investigation_rights" in views:
        prose = {r["inv_id"] for r in queries.rows(
            con, "SELECT inv_id FROM investigation_rights WHERE license_status = 'cc0_confirmed'")}
    by_inv = {i["inv_id"]: i for i in invs}
    docs = []
    for i in invs:
        year = re.search(r"(19|20)\d\d", i.get("start_date_raw") or "")
        docs.append({
            "id": i["inv_id"], "kind": "investigation", "title": i["title"], "authors": None,
            "year": int(year[0]) if year else None, "type": i.get("project_type"), "oa_status": "cc0",
            "open_access": True, "doi": i.get("doi"), "cited_by": None, "inv_ids": [i["inv_id"]],
            "evidence_level": "metadata", "n_findings": 0,
            "summary": i["objective"] if i["inv_id"] in prose else None,
            "_text": " ".join(filter(None, [i["title"], i["acronym"], i["objective"] if i["inv_id"] in prose else None])),
        })
    if "works" not in views:
        return finish(docs, by_inv)
    authors: dict[str, str] = {}
    if {"work_investigations", "publications"} <= views:
        for r in queries.rows(con, "SELECT wi.work_id, p.author_list FROM work_investigations wi "
                              "JOIN publications p ON p.inv_id = wi.inv_id AND p.pub_index = wi.pub_index "
                              "WHERE p.author_list IS NOT NULL ORDER BY wi.work_id, wi.inv_id, wi.pub_index"):
            authors.setdefault(r["work_id"], r["author_list"])
    found: dict[str, int] = {}
    if {"findings", "documents", "publication_policy"} <= views:
        found = {r["work_id"]: r["n"] for r in queries.rows(
            con, "SELECT d.work_id, count(DISTINCT f.finding_id) n FROM findings f JOIN documents d USING (doc_id) "
                 "JOIN publication_policy p USING (doc_id) "
                 "WHERE d.work_id IS NOT NULL AND p.pub_class <> 'withheld' AND p.show_quote GROUP BY 1")}
    # The same paper can be listed by several investigations, with and without bibliographic metadata.
    # Show it once: keep the richest record and remember every investigation that cites it.
    merged: dict[str, dict] = {}
    for w in queries.rows(con, "SELECT work_id, doi, title, inv_ids, publication_year, work_type, oa_status, "
                          "cited_by_count, evidence_level FROM works WHERE title IS NOT NULL ORDER BY work_id"):
        key = normalize(w["title"])
        seen = merged.get(key)
        if seen is None:
            merged[key] = dict(w, inv_ids=list(w["inv_ids"] or []), _ids=[w["work_id"]])
            continue
        ids = seen["_ids"] + [w["work_id"]]
        invs = list(dict.fromkeys(seen["inv_ids"] + list(w["inv_ids"] or [])))
        best = w if (w["doi"], w["publication_year"]) != (None, None) and seen["doi"] is None else seen
        merged[key] = dict(best, inv_ids=invs, _ids=ids)
    for w in merged.values():
        w["authors"] = next((authors[i] for i in w["_ids"] if i in authors), None)
        w["n_findings"] = sum(found.get(i, 0) for i in w["_ids"])
        docs.append({
            "id": w["work_id"], "kind": "publication", "title": w["title"], "authors": w["authors"],
            "year": w["publication_year"], "type": w["work_type"], "oa_status": w["oa_status"],
            "open_access": w["oa_status"] in OPEN_ACCESS, "doi": w["doi"], "cited_by": w["cited_by_count"],
            "inv_ids": w["inv_ids"], "evidence_level": w["evidence_level"],
            "n_findings": w["n_findings"], "summary": None, "_text": w["title"],
        })
    return finish(docs, by_inv)


def finish(docs: list[dict], by_inv: dict[str, dict]) -> list[dict]:
    for d in docs:
        d["investigations"] = [{"inv_id": i, "acronym": by_inv[i]["acronym"], "title": by_inv[i]["title"]}
                               for i in d["inv_ids"] if i in by_inv]
    return docs


class Index:
    """TF-IDF space over the whole corpus, so term weights do not depend on the query."""

    def __init__(self, docs: list[dict]):
        self.docs = docs
        self.surface: Counter = Counter()
        counts = [features(d["_text"], self.surface) for d in docs]
        df = Counter(term for c in counts for term in c)
        n = max(1, len(docs))
        self.df = df
        self.idf = {t: math.log((1 + n) / (1 + f)) + 1 for t, f in df.items()}
        self.vectors = [unit({t: (1 + math.log(tf)) * self.idf[t] * (1.25 if " " in t else 1.0)
                              for t, tf in c.items()}) for c in counts]
        self.by_inv = defaultdict(list)
        for k, d in enumerate(docs):
            if d["kind"] == "investigation":
                self.by_inv[d["id"]].append(k)

    def display(self, term: str) -> str:
        """Most frequent surface form of a stemmed term, e.g. 'flame' -> 'flames' if that is what titles say."""
        forms = [(n, s) for (t, s), n in self.surface.items() if t == term]
        return max(forms)[1] if forms else term

    def query_vector(self, query: str) -> dict[str, float]:
        text = query + " " + " ".join(a for key in concepts(query) for a in CONCEPTS[key])
        return unit({t: self.idf[t] for t in features(text) if t in self.idf})


# ------------------------------------------------------------------ pipeline


def retrieve(index: Index, query: str, limit: int) -> tuple[list[int], list[float]]:
    docs = index.docs
    if not query.strip():
        order = sorted(range(len(docs)), key=lambda k: (docs[k]["kind"] != "investigation",
                                                         -(docs[k]["cited_by"] or 0), docs[k]["id"]))[:limit]
        return order, [0.0] * len(order)
    qv = index.query_vector(query)
    named = {d["id"] for d in docs if d["kind"] == "investigation" and (
        matches(query, d["id"]) or any(i["acronym"] and matches(query, i["acronym"]) for i in d["investigations"]))}
    own = [dot(qv, v) for v in index.vectors]
    scores = []
    for k, d in enumerate(docs):
        # A publication inherits part of the match of the investigation it belongs to: titles alone are short.
        parent = max((own[j] for i in d["inv_ids"] for j in index.by_inv.get(i, [])), default=0.0)
        score = own[k] + (0.35 * parent if d["kind"] == "publication" else 0.0)
        if named & set(d["inv_ids"]):
            score += 1.0
        scores.append(score)
    order = sorted((k for k in range(len(docs)) if scores[k] > 1e-9), key=lambda k: (-scores[k], docs[k]["id"]))[:limit]
    return order, [scores[k] for k in order]


def cluster(vectors: list[dict[str, float]], k: int, rounds: int = 20) -> list[int]:
    n = len(vectors)
    if n == 0:
        return []
    k = max(1, min(k, n))
    seeds = [0]                                             # farthest-first: deterministic and well spread
    nearest = [dot(vectors[0], v) for v in vectors]
    while len(seeds) < k:
        nxt = min(range(n), key=lambda i: (nearest[i], i))
        if nxt in seeds:
            break
        seeds.append(nxt)
        nearest = [max(nearest[i], dot(vectors[nxt], vectors[i])) for i in range(n)]
    centroids = [dict(vectors[s]) for s in seeds]
    assign = [0] * n
    for _ in range(rounds):
        new = [max(range(len(centroids)), key=lambda c: (dot(vectors[i], centroids[c]), -c)) for i in range(n)]
        if new == assign and _:
            break
        assign = new
        for c in range(len(centroids)):
            total: dict[str, float] = defaultdict(float)
            for i in range(n):
                if assign[i] == c:
                    for t, w in vectors[i].items():
                        total[t] += w
            if total:
                centroids[c] = unit(total)
    # Fold singletons into their closest area when there is enough material: one-paper bubbles say little.
    sizes = Counter(assign)
    if n >= 12:
        for i in range(n):
            if sizes[assign[i]] == 1:
                options = [c for c in sizes if sizes[c] > 1]
                if options:
                    best = max(options, key=lambda c: (dot(vectors[i], centroids[c]), -c))
                    sizes[assign[i]] -= 1
                    sizes[best] += 1
                    assign[i] = best
    remap = {c: j for j, c in enumerate(sorted({a for a in assign}))}
    return [remap[a] for a in assign]


def label(index: Index, members: list[list[int]], vectors: list[dict[str, float]], skip: set[str]) -> list[list[str]]:
    spread = Counter()                                      # in how many clusters a term appears
    weight: list[dict[str, float]] = []
    for group in members:
        total: dict[str, float] = defaultdict(float)
        seen = Counter()
        for i in group:
            for t, w in vectors[i].items():
                total[t] += w
                seen[t] += 1
        scored = {t: w * math.sqrt(seen[t] / len(group)) * (1.5 if " " in t else 1.0) for t, w in total.items()}
        weight.append(scored)
        spread.update(scored.keys())
    labels = []
    for scored in weight:
        ranked = sorted(scored, key=lambda t: (-scored[t] * math.log(1 + len(members) / spread[t]), t))
        chosen: list[str] = []
        for t in ranked:
            parts = set(t.split())
            if t in skip or parts <= skip:
                continue
            if any(parts <= set(c.split()) or set(c.split()) <= parts for c in chosen):
                continue
            chosen.append(t)
            if len(chosen) == 3:
                break
        labels.append([index.display(t).capitalize() if n == 0 else index.display(t) for n, t in enumerate(chosen)]
                      or ["Otros"])
    return labels


def layout(centroids: list[dict[str, float]]) -> list[tuple[float, float]]:
    """Classical MDS on cosine distance, by power iteration. Returns coordinates in [-1, 1]."""
    k = len(centroids)
    if k == 1:
        return [(0.0, 0.0)]
    if k == 2:
        return [(-0.5, 0.0), (0.5, 0.0)]
    d2 = [[(1 - dot(centroids[i], centroids[j])) ** 2 if i != j else 0.0 for j in range(k)] for i in range(k)]
    row = [sum(r) / k for r in d2]
    mean = sum(row) / k
    b = [[-0.5 * (d2[i][j] - row[i] - row[j] + mean) for j in range(k)] for i in range(k)]
    axes = []
    for axis in range(2):
        v = [math.sin(1.7 * (i + 1) + axis) for i in range(k)]
        value = 0.0
        for _ in range(200):
            w = [sum(b[i][j] * v[j] for j in range(k)) for i in range(k)]
            for prev in axes:                               # deflation keeps the second axis orthogonal
                proj = sum(x * y for x, y in zip(w, prev))
                w = [x - proj * y for x, y in zip(w, prev)]
            value = math.sqrt(sum(x * x for x in w))
            if value < 1e-12:
                w = [math.cos(2.3 * (i + 1) + axis) for i in range(k)]
                value = math.sqrt(sum(x * x for x in w))
            v = [x / value for x in w]
        axes.append(v)
    span = max(max(abs(x) for x in axes[0]), max(abs(y) for y in axes[1])) or 1.0
    return [(axes[0][i] / span, axes[1][i] / span) for i in range(k)]


def build_map(con, query: str, limit: int = 80) -> dict:
    index = Index(load_documents(con))
    order, scores = retrieve(index, query, limit)
    vectors = [index.vectors[k] for k in order]
    n = len(order)
    k = 1 if n < 4 else max(2, min(12, round(math.sqrt(n) * 1.15)))
    assign = cluster(vectors, k)
    members: list[list[int]] = [[] for _ in range(max(assign, default=-1) + 1)]
    for i, c in enumerate(assign):
        members[c].append(i)
    skip = set(features(query + " " + " ".join(a for key in concepts(query) for a in CONCEPTS[key])))
    labels = label(index, members, vectors, skip) if members else []
    centroids = []
    for group in members:
        total: dict[str, float] = defaultdict(float)
        for i in group:
            for t, w in vectors[i].items():
                total[t] += w
        centroids.append(unit(total))
    positions = layout(centroids) if centroids else []
    top = max(scores, default=0.0) or 1.0
    documents = []
    for i, key in enumerate(order):
        d = {f: v for f, v in index.docs[key].items() if not f.startswith("_")}
        d.update(cluster=assign[i], relevance=round(scores[i] / top, 4),
                 url=f"https://doi.org/{d['doi']}" if d["doi"] else None)
        documents.append(d)
    clusters = [{"id": c, "label": ", ".join(labels[c]), "terms": labels[c], "size": len(group),
                 "open_access": sum(documents[i]["open_access"] for i in group),
                 "x": round(positions[c][0], 4), "y": round(positions[c][1], 4)}
                for c, group in enumerate(members)]
    warnings = [("Las áreas y sus etiquetas se calculan automáticamente a partir de títulos y metadatos. "
                 "Son una ayuda para explorar, no una clasificación científica.")]
    if not n:
        warnings.append("Sin coincidencias en el corpus. Que un tema no aparezca no significa que no se haya estudiado.")
    return {"query": query, "interpreted_concepts": [TOPIC_LABELS[c] for c in concepts(query) if c in TOPIC_LABELS],
            "documents": documents, "clusters": clusters, "total": n, "corpus_size": len(index.docs),
            "limit": limit, "warnings": warnings,
            "method": {"version": MAP_VERSION, "retrieval": "tfidf_cosine+concept_expansion",
                       "similarity": "tfidf_titles", "clustering": "spherical_kmeans", "layout": "classical_mds",
                       "source": "local_public_export_only"}}


def suggest(con, query: str, limit: int = 8) -> list[dict]:
    index = Index(load_documents(con))
    q = normalize(query)
    pool: list[dict] = []
    for d in index.docs:
        if d["kind"] == "investigation":
            acronym = d["investigations"][0]["acronym"] if d["investigations"] else None
            pool.append({"text": acronym or d["title"], "detail": d["title"] if acronym else d["id"],
                         "kind": "investigation", "weight": 1000 + (1 if acronym else 0)})
    hits = Counter(key for d in index.docs for key in concepts(d["_text"]))
    for key, text in TOPIC_LABELS.items():
        if hits[key]:
            pool.append({"text": text, "detail": None, "kind": "topic", "weight": 500 + hits[key],
                         "_aliases": CONCEPTS[key], "count": hits[key]})
    for term, freq in index.df.items():
        if " " in term and freq >= 3:
            pool.append({"text": index.display(term), "detail": None, "kind": "term", "weight": freq, "count": freq})
    if not q:
        chosen = sorted((p for p in pool if p["kind"] == "topic"), key=lambda p: -p["weight"])[:limit]
    else:
        def rank(p):
            hay = [normalize(p["text"]), normalize(p.get("detail") or ""), *map(normalize, p.get("_aliases", []))]
            if any(h.startswith(q) for h in hay):
                return 0
            if any(w.startswith(q) for h in hay for w in h.split()):
                return 1
            return 2 if any(q in h for h in hay) else None
        ranked = [(rank(p), -p["weight"], p["text"], p) for p in pool]
        chosen, seen = [], set()
        for r, _, _, p in sorted((x for x in ranked if x[0] is not None), key=lambda x: x[:3]):
            if normalize(p["text"]) not in seen:
                seen.add(normalize(p["text"]))
                chosen.append(p)
            if len(chosen) == limit:
                break
    return [{k: v for k, v in p.items() if k in ("text", "detail", "kind", "count")} for p in chosen]


# ------------------------------------------------------------------ routes


def _wrap(con, data):
    result = queries.wrap(con, data)
    result["meta"]["versions"].update(research_map=MAP_VERSION)
    return result


def _public(con):
    from .research_service import ResearchError
    try:
        require_public(con)
    except ValueError as exc:
        raise ResearchError("public_export_required", "Estas rutas necesitan una exportación pública.", 503) from exc


@router.get("/research/map")
def knowledge_map(q: str = Query(default="", max_length=300), limit: int = Query(default=80, ge=1, le=150)):
    """Query -> retrieved documents grouped into labelled areas with 2-D positions."""
    from . import api
    with api._con() as con:
        _public(con)
        return _wrap(con, build_map(con, q, limit))


@router.get("/research/suggest")
def suggestions(q: str = Query(default="", max_length=100), limit: int = Query(default=8, ge=1, le=20)):
    """Search suggestions taken from the corpus: investigations, documented topics and frequent title terms."""
    from . import api
    with api._con() as con:
        _public(con)
        return _wrap(con, suggest(con, q, limit))
