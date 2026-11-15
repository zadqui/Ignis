"""Research API regression tests. All fixture studies and numbers here are synthetic."""


import duckdb
import pytest
from fastapi.testclient import TestClient

from flame_in_freefall.app import api
from flame_in_freefall.app.research_language import concepts, interpret
from flame_in_freefall.app.research_service import ResearchService
from flame_in_freefall.app.research_store import build_index, fingerprint, load_corpus
from flame_in_freefall.corpus.schemas import SCHEMAS as CORPUS
from flame_in_freefall.findings.schemas import SCHEMAS as FINDINGS
from flame_in_freefall.psi.storage import SCHEMAS as PSI
from flame_in_freefall.trials.build import SCHEMAS as TRIALS


def insert(con, table, row):
    columns = ",".join(f'"{key}"' for key in row)
    placeholders = ",".join("?" for _ in row)
    con.execute(f'INSERT INTO "{table}" ({columns}) VALUES ({placeholders})', list(row.values()))


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "synthetic-public.duckdb"
    con = duckdb.connect(str(path))
    schemas = {**PSI, **CORPUS, **FINDINGS, **TRIALS}
    schemas["findings"] = {**FINDINGS["machine_findings"], "display_status": "VARCHAR",
                           "scientific_review_status": "VARCHAR"}
    schemas["m5_findings"] = {"finding_id": "VARCHAR", "active": "BOOLEAN", "prompt_version": "VARCHAR"}
    schemas["investigation_rights"] = {"inv_id": "VARCHAR", "license_status": "VARCHAR", "dataset_doi": "VARCHAR"}
    schemas["publication_manifest"] = {"version": "VARCHAR"}
    schemas["publication_policy"] = {"doc_id": "VARCHAR", "pub_class": "VARCHAR", "show_quote": "BOOLEAN",
                                     "show_claim": "BOOLEAN", "attribution_required": "BOOLEAN",
                                     "license_label": "VARCHAR", "pub_reason": "VARCHAR"}
    schemas["relations"] = {"relation_id": "VARCHAR", "finding_a": "VARCHAR", "finding_b": "VARCHAR",
                            "relation_type": "VARCHAR", "explanation": "VARCHAR", "status": "VARCHAR",
                            "is_scientific_relation": "BOOLEAN"}
    for table, columns in schemas.items():
        defs = ",".join(f'"{k}" {v}' for k, v in columns.items())
        con.execute(f'CREATE TABLE "{table}" ({defs})')
    for iid, acronym, objective in [
        ("PSI-T1", "BASS-II", "Synthetic flame spread in PMMA with a camera."),
        ("PSI-T2", "FLEX", "Synthetic heptane droplet extinction with a sensor."),
    ]:
        insert(con, "investigations", {"inv_id": iid, "title": "SYNTHETIC TEST " + acronym, "acronym": acronym,
                                       "objective": objective, "approach": "Synthetic documented method",
                                       "project_type": "Microgravity Investigation"})
        insert(con, "investigation_rights", {"inv_id": iid, "license_status": "cc0_confirmed"})
    for fid, iid, policy, claim, quote in [
        ("f-test1", "PSI-T1", "public_cc0", "Synthetic PMMA flame spread increased.", "Synthetic PMMA flame spread increased."),
        ("f-test2", "PSI-T2", "public_cc0", "Synthetic heptane droplets extinguished.", "Synthetic heptane droplets extinguished."),
        ("f-secret", "PSI-T1", "withheld", "RESTRICTED_SECRET_123", "RESTRICTED_SECRET_123"),
        ("f-nd", "PSI-T1", "public_no_derivatives", "ND_REFORMULATION_SECRET", "Allowed ND quote."),
    ]:
        doc = "doc-" + fid
        insert(con, "documents", {"doc_id": doc, "title": "SYNTHETIC source " + fid, "inv_ids": [iid],
                                   "origin": "psi_internal", "processing_status": "text_extracted"})
        insert(con, "publication_policy", {"doc_id": doc, "pub_class": policy, "show_quote": policy != "withheld",
                                            "show_claim": policy == "public_cc0", "license_label": policy})
        insert(con, "findings", {"finding_id": fid, "doc_id": doc, "inv_ids": [iid], "claim": claim,
                                  "claim_type": "result", "status": "machine_verified", "source_verified": True,
                                  "scientific_review_status": "not_reviewed", "conditions_json": "{}", "values_json": "[]"})
        insert(con, "m5_findings", {"finding_id": fid, "active": True})
        insert(con, "evidence", {"finding_id": fid, "doc_id": doc, "field": "claim", "quote": quote, "page_no": 2})
    for key, inv, flow in [("trial-test1", "PSI-T1", 10.0), ("trial-test2", "PSI-T2", 20.0)]:
        insert(con, "trials", {"trial_key": key, "inv_id": inv, "fuel": "PMMA" if inv == "PSI-T1" else "heptane", "flow_cm_s_min": flow,
                                "flow_cm_s_max": flow, "o2_frac_min": 0.21, "o2_frac_max": 0.21,
                                "pressure_kpa_min": 100, "pressure_kpa_max": 100,
                                "source_resource_id": "synthetic-resource", "row_ref": "synthetic.csv#record=1",
                                "row_grain": "trial", "mapping_status": "draft", "field_provenance_json": "{}"})
    insert(con, "relations", {"relation_id": "r-test", "finding_a": "f-test1", "finding_b": "f-test2",
                              "relation_type": "related_topic", "explanation": "Synthetic exploratory relationship",
                              "is_scientific_relation": False, "status": "provisional"})
    con.close()
    return path


@pytest.fixture
def client(db, monkeypatch):
    monkeypatch.setattr(api, "DB", db)
    monkeypatch.setattr(api, "PUBLIC", True)
    monkeypatch.delenv("FIF_RESEARCH_INDEX", raising=False)
    return TestClient(api.app)


def test_semantic_recovers_acrylic_alias_and_filters(client):
    r = client.post("/search/semantic", json={"query": "propagación de fuego en materiales acrílicos"})
    assert r.status_code == 200
    body = r.json()
    assert body["data"]["results"][0]["inv_id"] == "PSI-T1"
    assert body["data"]["results"][0]["references"]
    assert "pmma" in body["data"]["criteria"]["materials"]
    assert body["meta"]["versions"]["research_source"]
    r = client.post("/search/hybrid", json={"query": "PMMA", "filters": {"material": "heptane"}})
    assert r.status_code == 200 and r.json()["data"]["total"] == 0
    r = client.get("/investigations?category=Flame%20Propagation&material=PMMA")
    assert [p["inv_id"] for p in r.json()["data"]["items"]] == ["PSI-T1"]


def test_study_summary_preserves_identity_and_provenance(client):
    body = client.post("/assistant/query", json={"question": "Resume la investigación BASS-II"}).json()["data"]
    assert body["context"]["investigation_ids"] == ["PSI-T1"]
    assert body["finding_ids"] == ["f-nd", "f-test1"] or set(body["finding_ids"]) == {"f-nd", "f-test1"}
    assert body["structured"]["investigations"][0]["sections"]["objectives"]
    assert not body["evidence_status"]["scientific_review_confirmed"]
    for f in body["evidence"]:
        assert f["citation"]["finding_id"] == f["finding_id"]
        assert f["citation"]["page"] == 2
    detail = client.get("/investigations/BASS-II").json()["data"]
    assert detail["entity_type"] == "investigation"
    assert detail["trial_count"] == 1
    assert "documented_conclusions" in detail["missing_fields"]


def test_comparison_no_invented_numerical_results(client):
    r = client.post("/compare/investigations", json={"investigation_ids": ["BASS-II", "FLEX"]})
    assert r.status_code == 200
    body = r.json()["data"]
    assert body["differences"]
    assert body["relations"][0]["relation_type"] == "related_topic"
    assert not body["conclusions"]
    assert not body["compatibility"]["quantitative"]
    r = client.post("/compare/experiments", json={"trial_keys": ["trial-test1", "trial-test2"]})
    body = r.json()["data"]
    flow = next(v for v in body["variables"] if v["variable"] == "flow_cm_s")
    assert flow["difference"] == 10
    oxygen = next(v for v in body["variables"] if v["variable"] == "o2_pct")
    assert oxygen["left"]["minimum"] == 21
    gravity = next(v for v in body["variables"] if v["variable"] == "gravity_g")
    assert gravity["difference"] is None and gravity["status"] == "unknown"
    assert not body["compatibility"]["quantitative"]


def test_lunar_scenario_no_gravity_imputation(client):
    r = client.post("/analyze/scenario", json={"query": "Propagación de llamas en PMMA dentro de una base lunar presurizada",
                                              "pressure_kpa": 80, "o2_pct": 30})
    assert r.status_code == 200
    body = r.json()["data"]
    assert body["criteria"]["environment"] == "lunar_base"
    assert body["criteria"]["gravity_g"] is None
    assert body["oxygen_partial_pressure_kpa"] == 24
    assert body["trials"] and body["gaps"]
    assert all(t["applicability"] == "not_established" for t in body["trials"])
    assert any("microgravedad" in w for w in body["warnings"])


def test_exact_number_refused_and_history_scoped(client):
    r = client.post("/assistant/query", json={"question": "¿Cuál es la velocidad exacta de propagación del fuego sobre PMMA en gravedad lunar?"})
    body = r.json()["data"]
    assert body["evidence_status"]["insufficient"]
    assert "cifra exacta" in body["interpretation"]
    r = client.post("/assistant/query", json={"question": "¿Y sus limitaciones?", "history": [
        {"role": "user", "content": "Resume BASS-II"}, {"role": "assistant", "content": "FLEX"}]})
    assert r.json()["data"]["context"]["investigation_ids"] == ["PSI-T1"]
    r = client.post("/assistant/query", json={"question": "resume", "investigation_ids": ["FLEX"],
                                               "finding_ids": ["f-test1"]})
    assert r.status_code == 404


def test_public_permissions_all_surfaces_and_index(client, db, tmp_path):
    index = tmp_path / "research.json"
    build_index(db, index)
    raw = index.read_text(encoding="utf-8")
    assert "RESTRICTED_SECRET_123" not in raw
    assert "ND_REFORMULATION_SECRET" not in raw
    corpus = load_corpus(db, index)
    assert all("Allowed ND quote" not in c["text"] for c in corpus["chunks"])
    for path, payload in [("/search/hybrid", {"query": "RESTRICTED_SECRET_123"}),
                          ("/assistant/query", {"question": "Resume BASS-II"}),
                          ("/compare/investigations", {"investigation_ids": ["BASS-II", "FLEX"]})]:
        response = client.post(path, json=payload).json()["data"]
        # The user's own query is intentionally echoed in criteria. Inspect retrieved output instead.
        response.pop("criteria", None)
        raw = str(response)
        assert "RESTRICTED_SECRET_123" not in raw
        assert "ND_REFORMULATION_SECRET" not in raw
    nd = next(f for f in client.get("/investigations/BASS-II/findings").json()["data"]["items"]
              if f["finding_id"] == "f-nd")
    assert nd["claim"] is None and nd["citation"]["quote"] == "Allowed ND quote."


def test_pagination_errors_contract_and_legacy_routes(client):
    first = client.get("/investigations?limit=1").json()["data"]
    second = client.get("/investigations?limit=1&offset=1").json()["data"]
    assert first["total"] == 2 and first["items"][0]["inv_id"] != second["items"][0]["inv_id"]
    assert client.post("/search/hybrid", json={"query": "PMMA", "limit": 0}).status_code == 422
    assert client.post("/analyze/scenario", json={"o2_pct": 101}).status_code == 422
    r = client.get("/investigations/unknown")
    assert r.status_code == 404 and r.json()["detail"]["code"] == "investigation_not_found"
    assert client.post("/compare/investigations", json={"investigation_ids": ["BASS-II"]}).status_code == 400
    for path in ["/health", "/findings"]:
        assert client.get(path).status_code == 200
    schema = client.get("/openapi.json").json()
    assert "AIAnswer" in schema["components"]["schemas"]
    assert "/assistant/query" in schema["paths"]


def test_numeric_filters_require_observed_conditions_in_one_trial(client):
    r = client.post("/search/hybrid", json={"query": "PMMA", "filters": {
        "o2_pct": 21, "pressure_kpa": 100, "flow_cm_s": 10}})
    assert [p["inv_id"] for p in r.json()["data"]["results"]] == ["PSI-T1"]
    r = client.get("/investigations?gravity_g=0.16")
    assert r.json()["data"]["total"] == 0
    r = client.post("/search/hybrid", json={"query": "PMMA", "filters": {"o2_pct": 30}})
    assert r.json()["data"]["total"] == 0


def test_index_incremental_and_stale_index_invalidated(db, tmp_path):
    output = tmp_path / "index.json"
    build_index(db, output)
    before = fingerprint(db)
    con = duckdb.connect(str(db))
    con.execute("UPDATE investigations SET objective = 'Synthetic fire suppression' WHERE inv_id='PSI-T1'")
    con.close()
    after = load_corpus(db, output)
    assert after["source_sha256"] != before
    assert after["profiles"][0]["description"] == "Synthetic fire suppression"


def test_neural_encoder_path_and_query_cached(db, tmp_path):
    class SyntheticEncoder:
        model_id = "SYNTHETIC_TEST_EMBEDDER"
        calls = 0

        def encode(self, texts):
            self.calls += 1
            return [[1.0, 0.0] if "PMMA" in t or "acrílico" in t else [0.0, 1.0] for t in texts]

    encoder = SyntheticEncoder()
    index = tmp_path / "index.json"
    build_index(db, index, encoder)
    engine = ResearchService(load_corpus(db, index), encoder)
    from flame_in_freefall.app.research_schemas import ResearchSearchRequest
    req = ResearchSearchRequest(query="acrílico")
    assert engine.search(req, semantic=True)["results"][0]["inv_id"] == "PSI-T1"
    engine.search(req, semantic=True)
    assert encoder.calls == 2  # one corpus batch and one query embedding


def test_alias_boundaries_and_numeric_query_parser():
    assert "pmma" in concepts("material acrílico")
    parsed = interpret("Compara FLEX-II con BASS-II a 30% de oxígeno y 80 kPa", [
        {"inv_id": "PSI-X1", "acronym": "FLEX"}, {"inv_id": "PSI-X2", "acronym": "FLEX-II"},
        {"inv_id": "PSI-X3", "acronym": "BASS-II"}])
    assert parsed["investigation_ids"] == ["PSI-X2", "PSI-X3"]
    assert parsed["quantities"]["o2_pct"] == 30 and parsed["quantities"]["pressure_kpa"] == 80


def test_local_rag_rejects_invented_ids_and_preserves_source_wording(client, monkeypatch):
    from flame_in_freefall.app import research_generation

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"message": {"content": '{"finding_ids":["invented"],"insufficient":false}'}}

    monkeypatch.setenv("FIF_RAG_MODEL", "SYNTHETIC_TEST_MODEL")
    monkeypatch.setattr(research_generation.requests, "post", lambda *args, **kwargs: Response())
    data = client.post("/assistant/query", json={"question": "Resume BASS-II"}).json()["data"]
    assert data["generation_mode"] == "extractive_grounded"
    assert "invented" not in data["finding_ids"]
    assert any("válida" in w for w in data["warnings"])
    assert all(s["citation_ids"] for s in data["statements"])


def test_http_proxy_forwards_query_posts_but_rejects_mutations(client):
    import importlib.util
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from pathlib import Path
    from urllib.error import HTTPError
    from urllib.request import Request, urlopen

    path = Path(__file__).resolve().parents[2] / "frontend" / "serve.py"
    spec = importlib.util.spec_from_file_location("research_frontend_server", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    class Upstream(BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"]))
            assert self.path == "/search/hybrid"
            assert body == b'{"query":"PMMA"}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"data":[],"meta":{}}')

        def log_message(self, *args):
            pass

    upstream = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
    proxy = ThreadingHTTPServer(("127.0.0.1", 0), module.make_handler(f"http://127.0.0.1:{upstream.server_port}"))
    servers = [upstream, proxy]
    threads = [threading.Thread(target=s.serve_forever, daemon=True) for s in servers]
    for thread in threads:
        thread.start()
    try:
        base = f"http://127.0.0.1:{proxy.server_port}"
        with urlopen(Request(base + "/api/search/hybrid", data=b'{"query":"PMMA"}'), timeout=5) as r:
            assert r.status == 200 and b'"data"' in r.read()
        with pytest.raises(HTTPError) as error:
            urlopen(Request(base + "/api/delete", data=b"{}"), timeout=5)
        assert error.value.code == 405
    finally:
        for server in servers:
            server.shutdown()
            server.server_close()
        for thread in threads:
            thread.join(timeout=5)


def test_reject_private_database(db, monkeypatch):
    con = duckdb.connect(str(db))
    con.execute("DROP TABLE publication_manifest")
    con.close()
    monkeypatch.setattr(api, "DB", db)
    monkeypatch.setattr(api, "PUBLIC", False)
    r = TestClient(api.app).post("/search/hybrid", json={"query": "PMMA"})
    assert r.status_code == 503 and r.json()["detail"]["code"] == "public_export_required"
