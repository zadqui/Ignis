"""Knowledge-map regression tests. Every study, title and number here is synthetic."""

import duckdb
import pytest

from flame_in_freefall.app import queries
from flame_in_freefall.app.research_map import build_map, cluster, features, layout, suggest, unit

SMOKE = ["Smoke particle size in low gravity", "Smoke detector response to smoke particles",
         "Aerosol smoke particle measurement", "Smoke particle morphology from overheated wire",
         "Smoke detection for spacecraft cabins", "Smoke particle growth and aging"]
DROPLET = ["Heptane droplet combustion extinction", "Cool flame droplet combustion of heptane",
           "Methanol droplet burning rate", "Droplet combustion with support fibers",
           "Heptane droplet flame radiative extinction", "Droplet burning in carbon dioxide"]


@pytest.fixture
def con(tmp_path):
    c = duckdb.connect(str(tmp_path / "synthetic-public.duckdb"))
    c.execute("CREATE TABLE publication_manifest (version VARCHAR)")
    c.execute("CREATE TABLE investigations (inv_id VARCHAR, title VARCHAR, acronym VARCHAR, doi VARCHAR, "
              "objective VARCHAR, project_type VARCHAR, start_date_raw VARCHAR)")
    c.execute("CREATE TABLE investigation_rights (inv_id VARCHAR, license_status VARCHAR)")
    c.execute("CREATE TABLE works (work_id VARCHAR, doi VARCHAR, title VARCHAR, inv_ids VARCHAR[], "
              "publication_year INTEGER, work_type VARCHAR, oa_status VARCHAR, cited_by_count INTEGER, "
              "evidence_level VARCHAR)")
    c.execute("INSERT INTO investigations VALUES "
              "('PSI-T1', 'SYNTHETIC smoke aerosol test', 'SMK', '10.0/t1', 'Synthetic smoke particle objective', "
              "'Microgravity Investigation', '01-01-2010'), "
              "('PSI-T2', 'SYNTHETIC droplet combustion test', 'DRP', '10.0/t2', 'Restricted prose', "
              "'Microgravity Investigation', '01-01-2012')")
    c.execute("INSERT INTO investigation_rights VALUES ('PSI-T1', 'cc0_confirmed'), ('PSI-T2', 'unclear')")
    for k, title in enumerate(SMOKE + DROPLET):
        inv = "PSI-T1" if k < len(SMOKE) else "PSI-T2"
        c.execute("INSERT INTO works VALUES (?, ?, ?, ?, ?, 'article', ?, ?, 'title_only')",
                  [f"wrk-{k:02d}", f"10.0/w{k}", title, [inv], 2010 + k, "gold" if k % 2 else "closed", k])
    # The same paper listed twice, once without bibliographic metadata.
    c.execute("INSERT INTO works VALUES ('wrk-dup', NULL, ?, ['PSI-T2'], NULL, NULL, NULL, NULL, 'title_only')", [SMOKE[0]])
    yield c
    c.close()


def test_map_groups_documents_by_topic_and_stays_within_the_corpus(con):
    result = build_map(con, "", limit=50)
    assert result["total"] == result["corpus_size"] == 14          # 2 investigations + 12 distinct papers
    assert result["method"]["source"] == "local_public_export_only"
    by_title = {d["title"]: d for d in result["documents"]}
    assert len({by_title[t]["cluster"] for t in SMOKE} & {by_title[t]["cluster"] for t in DROPLET}) == 0
    assert sum(c["size"] for c in result["clusters"]) == result["total"]
    assert all(-1 <= c["x"] <= 1 and -1 <= c["y"] <= 1 and c["label"] for c in result["clusters"])


def test_duplicate_titles_are_merged_and_keep_every_investigation(con):
    docs = {d["title"]: d for d in build_map(con, "", limit=50)["documents"]}
    merged = docs[SMOKE[0]]
    assert merged["doi"] == "10.0/w0" and merged["year"] == 2010
    assert set(merged["inv_ids"]) == {"PSI-T1", "PSI-T2"}


def test_query_is_bilingual_and_named_investigations_bring_their_papers(con):
    spanish = build_map(con, "humo")
    assert spanish["interpreted_concepts"] == ["humo y hollín"]
    assert spanish["documents"][0]["relevance"] == 1.0
    assert {d["title"] for d in spanish["documents"]} >= set(SMOKE)
    named = build_map(con, "DRP")
    assert {d["title"] for d in named["documents"] if d["kind"] == "publication"} >= set(DROPLET)
    assert build_map(con, "xyzzy")["total"] == 0


def test_restricted_prose_is_never_exposed(con):
    docs = {d["id"]: d for d in build_map(con, "", limit=50)["documents"]}
    assert docs["PSI-T1"]["summary"] == "Synthetic smoke particle objective"
    assert docs["PSI-T2"]["summary"] is None
    assert not any(k.startswith("_") for d in docs.values() for k in d)


def test_suggestions_come_from_the_corpus(con):
    assert next(s["text"] for s in suggest(con, "smk")) == "SMK"
    assert any(s["kind"] == "topic" and "humo" in s["text"] for s in suggest(con, "hum"))
    assert all(s["kind"] == "topic" for s in suggest(con, ""))
    assert suggest(con, "zzzz") == []


def test_private_database_is_refused(tmp_path):
    from fastapi.testclient import TestClient

    from flame_in_freefall.app import api
    path = tmp_path / "private.duckdb"
    duckdb.connect(str(path)).close()
    old = api.DB
    api.DB = path
    try:
        assert TestClient(api.app).get("/research/map", params={"q": "smoke"}).status_code == 503
    finally:
        api.DB = old


def test_clustering_and_layout_are_deterministic():
    vectors = [unit(dict(features(t))) for t in SMOKE + DROPLET]
    first = cluster(vectors, 2)
    assert first == cluster(vectors, 2)
    assert len(set(first[:6])) == 1 and len(set(first[6:])) == 1 and first[0] != first[6]
    assert layout([vectors[0], vectors[6], vectors[3]]) == layout([vectors[0], vectors[6], vectors[3]])
    assert queries is not None
