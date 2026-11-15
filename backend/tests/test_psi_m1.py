"""Offline tests for M1 against sanitized responses recorded from PSI (9 Nov 2026)."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import duckdb
import pytest

from flame_in_freefall.psi.client import PsiClient
from flame_in_freefall.psi.inventory import (
    FLAG_PATH_VERSION_CONFLICT,
    FLAG_REPEATED_IN_TREE,
    build_resource_rows,
    make_resource_id,
    run_inventory,
)
from flame_in_freefall.psi.schemas import (
    FilesResponse,
    InvestigationDetail,
    PsiSchemaError,
    SearchResponse,
    parse,
    redact,
)
from flame_in_freefall.psi.storage import read_current_run_id, save_snapshot

FIX = Path(__file__).parent / "fixtures"


def load(name: str):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


# --- fake transport ---------------------------------------------------------


class FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status
        self.headers = {"Content-Type": "application/json"}

    def json(self):
        return copy.deepcopy(self._payload)


class FakeSession:
    """Serves search pages, investigation details and trees from dicts."""

    def __init__(self, search_sources, details, trees):
        self.headers = {}
        self.search_sources = search_sources
        self.details = details
        self.trees = trees
        self.log = []

    def request(self, method, url, timeout=None, params=None, json=None):
        path = url.split("/ws", 1)[1]
        self.log.append((method, path, params, json))
        if path == "/repo/search":
            start, size = params["from"], params["size"]
            hits = [{"_source": s} for s in self.search_sources[start : start + size]]
            return FakeResponse({"hits": {"total": len(self.search_sources), "hits": hits}})
        if path.startswith("/repo/investigations/"):
            return FakeResponse(self.details[path.rsplit("/", 1)[1]])
        if path == "/files/v2":
            return FakeResponse(self.trees[json["studyId"]])
        return FakeResponse({}, status=404)


def fake_world(n_extra: int = 0):
    """PSI-142 (real fixture) plus ``n_extra`` clones to exercise paging."""
    src = next(
        h["_source"]
        for h in load("search_combustion_full.json")["hits"]["hits"]
        if h["_source"]["Accession"] == "PSI-142"
    )
    detail = load("investigation_PSI-142.json")
    tree = load("files_v2_PSI-142.json")
    sources, details, trees = [src], {"PSI-142": detail}, {"PSI-142": tree}
    for i in range(n_extra):
        acc = f"PSI-{900 + i}"
        sources.append(src | {"Accession": acc})
        details[acc] = detail | {"accession": acc}
        trees[acc] = json.loads(json.dumps(tree).replace("PSI-142", acc))
    return sources, details, trees


def make_client(session) -> PsiClient:
    return PsiClient(session=session, pause_s=0)


# --- schemas ----------------------------------------------------------------


def test_recorded_responses_validate():
    search = parse(SearchResponse, load("search_combustion_full.json"), "search")
    assert search.hits.total == 24 == len(search.hits.hits)
    types = [h.source.project_type for h in search.hits.hits]
    assert types.count("Microgravity Investigation") == 19
    assert types.count("Ground Investigation") == 5

    detail = parse(InvestigationDetail, load("investigation_PSI-142.json"), "detail")
    assert (detail.accession, detail.version, detail.projectType) == ("PSI-142", 2, "Ground Investigation")
    assert len(detail.publications) == 12

    tree = parse(FilesResponse, load("files_v2_PSI-142.json"), "tree")
    assert {n.key for n in tree.files} >= {"psi-data/PSI-142/metadata/"}


def test_file_node_without_id_is_rejected():
    bad = load("files_v2_PSI-142.json")
    del bad["files"][0]["files"][0]["id"]
    with pytest.raises(PsiSchemaError, match="lacks"):
        parse(FilesResponse, bad, "tree")


def test_missing_version_in_detail_is_rejected():
    bad = load("investigation_PSI-142.json")
    del bad["version"]
    with pytest.raises(PsiSchemaError):
        parse(InvestigationDetail, bad, "detail")


def test_redact_drops_signed_urls_and_contacts():
    raw = {"a": [{"remote_url": "https://x?sig=1", "email": "x@y", "keep": 1}], "phone": "1"}
    assert redact(raw) == {"a": [{"keep": 1}]}


# --- tree flattening ----------------------------------------------------------


def test_flatten_psi142_tree():
    tree = parse(FilesResponse, load("files_v2_PSI-142.json"), "tree")
    rows = build_resource_rows("PSI-142", 2, tree.files)
    cats = {r["category"] for r in rows}
    assert "Experimental table" in cats
    exp = next(r for r in rows if r["category"] == "Experimental table")
    assert exp["extension"] == "csv"
    assert exp["parent_folder"].startswith("psi-data/PSI-142/")
    assert all(r["quality_flags"] == [] for r in rows)
    assert len({r["resource_id"] for r in rows}) == len(rows)


def test_path_version_conflicts_are_flagged_not_resolved():
    tree = parse(FilesResponse, load("files_v2_PSI-20_conflicts_subset.json"), "tree")
    rows = build_resource_rows("PSI-20", 4, tree.files)
    conflicted = [r for r in rows if FLAG_PATH_VERSION_CONFLICT in r["quality_flags"]]
    assert len({r["path"] for r in conflicted}) == 3
    # every PSI record is kept, each with its own id/version
    assert len(conflicted) == sum(1 for r in rows if r["path_records"] > 1) > 3
    assert len({r["file_id"] for r in rows}) == len(rows)
    assert len({r["resource_id"] for r in rows}) == len(rows)
    assert all(r["tree_occurrences"] == 1 for r in rows)


def _with_repeated_node(tree: dict) -> dict:
    """Mimic PSI-106: the exact same file node listed twice in its folder."""
    tree = copy.deepcopy(tree)
    folder = tree["files"][0]["files"]
    folder.append(copy.deepcopy(folder[0]))
    return tree


def test_repeated_identical_nodes_collapse_to_one_record():
    raw = _with_repeated_node(load("files_v2_PSI-142.json"))
    rows = build_resource_rows("PSI-142", 2, parse(FilesResponse, raw, "tree").files)
    rep = [r for r in rows if FLAG_REPEATED_IN_TREE in r["quality_flags"]]
    assert len(rep) == 1 and rep[0]["tree_occurrences"] == 2
    assert FLAG_PATH_VERSION_CONFLICT not in rep[0]["quality_flags"]
    assert len({r["resource_id"] for r in rows}) == len(rows) == 3


def test_same_id_with_different_metadata_is_an_error():
    raw = _with_repeated_node(load("files_v2_PSI-142.json"))
    raw["files"][0]["files"][-1]["bytes_size"] += 1
    with pytest.raises(PsiSchemaError, match="differing metadata"):
        build_resource_rows("PSI-142", 2, parse(FilesResponse, raw, "tree").files)


def test_resource_id_is_deterministic():
    assert make_resource_id("PSI-20", "abc", 2) == make_resource_id("PSI-20", "abc", 2)
    assert make_resource_id("PSI-20", "abc", 2) != make_resource_id("PSI-20", "abc", 3)


# --- orchestration + storage --------------------------------------------------


def test_search_pages_until_total():
    session = FakeSession(*fake_world(n_extra=6))
    client = make_client(session)
    sources = client.search_investigations(field="Research Area", value="combustion science", page_size=3)
    assert len(sources) == 7
    assert [p["from"] for m, path, p, _ in session.log if path == "/repo/search"] == [0, 3, 6]


def test_full_run_snapshot_and_diff(tmp_path):
    world = fake_world(n_extra=1)
    result = run_inventory(make_client(FakeSession(*world)), page_size=50)
    assert result.scope == "full"
    assert any("survey baseline was 24" in w for w in result.warnings)
    snap = save_snapshot(result, tmp_path)
    assert read_current_run_id(tmp_path) == result.run_id

    con = duckdb.connect(str(tmp_path / "inventory.duckdb"), read_only=True)
    n_inv, n_res = con.execute(
        "SELECT (SELECT count(*) FROM investigations), (SELECT count(*) FROM resources)"
    ).fetchone()
    assert n_inv == 2 and n_res == len(result.resources)
    assert con.execute("SELECT typeof(quality_flags) FROM resources LIMIT 1").fetchone()[0] == "VARCHAR[]"
    assert con.execute("SELECT count(*) FROM versions WHERE previous_run_id IS NOT NULL").fetchone()[0] == 0
    con.close()
    assert (snap / "resources.parquet").exists()

    # Second run: PSI-142 gains a file, the clone loses one.
    sources, details, trees = copy.deepcopy(world)
    new_file = copy.deepcopy(trees["PSI-142"]["files"][0]["files"][0]) | {
        "id": "new-id-1",
        "key": "psi-data/PSI-142/metadata/new.zip",
    }
    trees["PSI-142"]["files"][0]["files"].append(new_file)
    trees["PSI-900"]["files"][0]["files"].pop()
    result2 = run_inventory(make_client(FakeSession(sources, details, trees)))
    result2.run_id += "-2"  # same-second runs in tests
    save_snapshot(result2, tmp_path)

    con = duckdb.connect(str(tmp_path / "inventory.duckdb"), read_only=True)
    diff = {
        r[0]: r[1:]
        for r in con.execute("SELECT inv_id, files_added, files_removed, files_changed FROM versions").fetchall()
    }
    assert diff["PSI-142"] == (1, 0, 0)
    assert diff["PSI-900"] == (0, 1, 0)
    assert con.execute("SELECT count(*) FROM versions_history").fetchone()[0] == 4
    assert con.execute("SELECT count(*) FROM runs").fetchone()[0] == 2
    con.close()


def test_partial_run_does_not_move_current(tmp_path):
    world = fake_world(n_extra=1)
    full = run_inventory(make_client(FakeSession(*world)))
    save_snapshot(full, tmp_path)
    part = run_inventory(make_client(FakeSession(*world)), only=["PSI-900"])
    part.run_id += "-p"
    save_snapshot(part, tmp_path)
    assert part.scope == "partial" and len(part.investigations) == 1
    assert read_current_run_id(tmp_path) == full.run_id


def test_unknown_accession_in_only_fails():
    with pytest.raises(ValueError, match="PSI-999"):
        run_inventory(make_client(FakeSession(*fake_world())), only=["PSI-999"])


def test_persisted_data_has_no_signed_urls_or_emails(tmp_path):
    result = run_inventory(make_client(FakeSession(*fake_world())))
    snap = save_snapshot(result, tmp_path)
    con = duckdb.connect()
    blob = " ".join(
        str(row)
        for t in ("investigations", "publications", "resources")
        for row in con.execute(
            f"SELECT CAST(COLUMNS(*) AS VARCHAR) FROM read_parquet('{(snap / f'{t}.parquet').as_posix()}')"
        ).fetchall()
    )
    assert "remote_url" not in blob and "@princeton.edu" not in blob and "athena/file" not in blob


# --- live (opt-in) ------------------------------------------------------------


@pytest.mark.live
def test_live_psi159(tmp_path):
    result = run_inventory(PsiClient(), only=["PSI-159"])
    assert len(result.investigations) == 1
    assert any(r["category"] == "Experimental table" for r in result.resources)
    save_snapshot(result, tmp_path)
