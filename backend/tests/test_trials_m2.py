"""Offline tests for M2 against real PSI experimental tables (CC0, 9 Nov 2026)."""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path

import pytest
import yaml

from flame_in_freefall.psi.download import DownloadError, Target, fetch
from flame_in_freefall.trials import units
from flame_in_freefall.trials.draft import draft_config
from flame_in_freefall.trials.linking import SegmentIndex, link_trials
from flame_in_freefall.trials.mapping import MappingConfig, apply_mapping
from flame_in_freefall.trials.reader import decode, read_table
from flame_in_freefall.trials.values import header_unit, parse_cell

TABLES = Path(__file__).parent / "fixtures" / "tables"
NORMAL = TABLES / "PSI-159_Experimental table_CFI-G_Normal Flames.csv"
INVERSE = TABLES / "PSI-159_Experimental table_CFI-G_Inverse Flames.csv"
FLEX = TABLES / "PSI-69_Experimental table_FLEX.csv"
SAFFIRE2 = TABLES / "PSI-99_Experimental table_SAFFIRE-2.csv"
ACME_BRE = TABLES / "PSI-20_Experimental table_ACME BRE.csv"
FLEX2 = TABLES / "PSI-68_Experimental table_Flex2.csv"
EMPTY_INDEX = SegmentIndex([])


def config_for(path: Path, inv: str, index: SegmentIndex = EMPTY_INDEX, **overrides) -> MappingConfig:
    raw = draft_config(read_table(path), inv, path.name, "res-test", index)
    raw.update(overrides)
    # round-trip through YAML exactly as on disk
    return MappingConfig.model_validate(yaml.safe_load(yaml.safe_dump(raw)))


# --- reader -------------------------------------------------------------------


@pytest.mark.parametrize("path", sorted(TABLES.glob("*.csv")), ids=lambda p: p.name[:30])
def test_reader_is_lossless(path: Path):
    text, _ = decode(path.read_bytes())
    expected = list(csv.reader(io.StringIO(text, newline="")))
    table = read_table(path)
    assert [r.cells for r in table.rows] == expected
    assert [r.record_no for r in table.rows] == list(range(1, len(expected) + 1))


def test_reader_encodings_blanks_and_notes():
    assert read_table(FLEX).encoding == "cp1252"
    inv = read_table(INVERSE)
    assert sum(r.kind == "blank" for r in inv.rows) == 861 and len(inv.data_rows) == 154
    notes = [r for r in read_table(SAFFIRE2).rows if r.kind == "note"]
    assert [r.cells[0][:6] for r in notes] == ["Note 1", "Note 2", "Note 3", "Note 4"]


# --- values & units -------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,kind,values,unit,approx",
    [
        ("0.21", "number", [0.21], None, False),
        (".33 cm", "number", [0.33], "cm", False),
        ("30 cm/s", "number", [30.0], "cm/s", False),
        ("~ 21.5", "approx", [21.5], None, True),
        ("21.5 - 21.7", "range", [21.5, 21.7], None, False),
        ("30%-40%", "range", [30.0, 40.0], "%", False),
        ("21; 26.5; 40", "list", [21.0, 26.5, 40.0], None, False),
        ("0.5; 1.0; 1.5; 2.0; or 3.0", "list", [0.5, 1.0, 1.5, 2.0, 3.0], None, False),
        ("RAMPED", "text", [], None, False),
        ("Insignificant", "text", [], None, False),
        ("n/a", "missing", [], None, False),
        ("-", "missing", [], None, False),
        ("-0.28", "number", [-0.28], None, False),
    ],
)
def test_parse_cell(raw, kind, values, unit, approx):
    p = parse_cell(raw)
    assert (p.kind, p.values, p.cell_unit, p.approx) == (kind, values, unit, approx)


@pytest.mark.parametrize(
    "header,unit",
    [
        ("approx p (bar)", "bar"),
        ("Ambient pressure; mmHg", "mmHg"),
        ("O initial ambient composition; mole fraction", "mole fraction"),
        ("Calibrated initial O2 % by vol", "%"),
        ("Percent O2 (Note 1)", "%"),
        ("XO2 (init)", None),
        ("XO2 before test", None),
        ("burn time (sec)", "sec"),
    ],
)
def test_header_unit_only_when_explicit(header, unit):
    assert header_unit(header) == unit


@pytest.mark.parametrize(
    "value,unit,expected",
    [
        (1, "atm", 101.325),
        (1, "bar", 100.0),
        (760, "mmHg", 101.325),
        (21, "%", 0.21),
        (2, "min", 120.0),
        (5, "mm/s", 0.5),
        (25, "C", 298.15),
    ],
)
def test_unit_conversions(value, unit, expected):
    got, _ = units.convert(value, unit)
    assert got == pytest.approx(expected, rel=1e-6)


def test_unknown_unit_is_not_converted():
    assert units.convert(1.0, "furlongs") is None
    assert not units.in_domain("fraction", [34.0])


# --- mapping ------------------------------------------------------------------------


def test_psi159_normal_draft_and_trials():
    cfg = config_for(NORMAL, "PSI-159")
    assert cfg.review.status == "draft" and cfg.review.priority == "high"
    assert cfg.grain == "trial" and cfg.trial_id.column == "Test"
    assert cfg.fields["pressure"].unit == "bar" and cfg.fields["pressure"].unit_source == "header"
    assert cfg.fields["o2"].unit is None and "mole fraction" in cfg.fields["o2"].suggestion
    trials = apply_mapping(cfg, "v-test", read_table(NORMAL), "res-test")
    assert len(trials) == 179
    t = trials[1]
    assert (t["trial_id_raw"], t["trial_id"], t["trial_id_normalization"]) == (
        "21088 B1",
        "21088B1",
        "strip_whitespace",
    )
    assert t["o2_frac_min"] is None  # XO2 has no explicit unit: not converted
    assert t["pressure_kpa_min"] == pytest.approx(94.43956)
    assert t["gravity_g"] is None and t["o2_location"] == "unknown"
    assert t["termination"] == "self_extinguished" and t["ignition"] is True
    assert t["conversion_verified"] is True and t["interpretation_verified"] is False
    prov = json.loads(t["field_provenance_json"])
    assert prov["o2"]["parts"][0]["not_converted_reason"] == "no explicit unit"
    assert json.loads(t["original_columns_json"])["XO2 before test"] == "0.389822946"


def test_reviewer_declared_unit_converts_and_is_traceable():
    cfg = config_for(NORMAL, "PSI-159")
    cfg.fields["o2"].unit, cfg.fields["o2"].unit_source = "fraction", "reviewer: X denotes mole fraction (doc ref)"
    t = apply_mapping(cfg, "v", read_table(NORMAL), "res-test")[0]
    assert t["o2_frac_min"] == pytest.approx(0.389822946) and t["o2_frac_max"] == pytest.approx(0.3939)
    assert json.loads(t["field_provenance_json"])["o2"]["parts"][0]["unit_source"].startswith("reviewer")


def test_conflicting_or_out_of_domain_values_are_not_converted():
    cfg = config_for(ACME_BRE, "PSI-20")
    assert cfg.grain == "test_day" and cfg.fields["o2"].unit == "percent"
    trials = apply_mapping(cfg, "v", read_table(ACME_BRE), "res-test")
    weird = [t for t in trials if "3400%" in t["original_columns_json"]]
    assert weird and all(t["o2_frac_max"] is None for t in weird)
    lists = [t for t in trials if json.loads(t["original_columns_json"])["Oxygen Conc (percent)"] == "21; 26.5; 40"]
    assert (lists[0]["o2_frac_min"], lists[0]["o2_frac_max"]) == (pytest.approx(0.21), pytest.approx(0.40))


def test_condition_matrix_grain():
    assert config_for(FLEX2, "PSI-68").grain == "condition_matrix"


def test_lost_subscript_header_is_not_guessed_as_o2():
    # FLEX header reads literally "O initial ambient composition" (subscript lost at source).
    flex = config_for(FLEX, "PSI-69")
    assert "o2" not in flex.fields and flex.o2_location == "unknown"
    assert flex.fields["pressure"].unit == "mmHg"


def test_ambient_location_only_from_explicit_header_text():
    raw = draft_config(read_table(FLEX), "PSI-69", FLEX.name, "r", EMPTY_INDEX)
    assert raw["o2_location_source"] is None
    table = read_table(FLEX)
    table.header = [h.replace("O initial", "O2 initial") for h in table.header]
    patched = draft_config(table, "PSI-69", FLEX.name, "r", EMPTY_INDEX)
    assert patched["o2_location"] == "ambient" and "ambient" in patched["o2_location_source"]


@pytest.mark.parametrize(
    "patch,msg",
    [
        ({"o2_location": "burner_flow", "o2_location_source": None}, "o2_location_source"),
        ({"grain": "per_week"}, "unknown grain"),
    ],
)
def test_config_validation(patch, msg):
    raw = draft_config(read_table(NORMAL), "PSI-159", NORMAL.name, "r", EMPTY_INDEX) | patch
    with pytest.raises(ValueError, match=msg):
        MappingConfig.model_validate(raw)


def test_unit_without_source_is_rejected():
    raw = draft_config(read_table(NORMAL), "PSI-159", NORMAL.name, "r", EMPTY_INDEX)
    raw["fields"]["o2"]["unit"] = "fraction"
    with pytest.raises(ValueError, match="unit_source"):
        MappingConfig.model_validate(raw)


# --- linking --------------------------------------------------------------------------


def test_linking_is_exact_after_declared_normalization():
    index = SegmentIndex(
        [
            ("PSI-159", "r1", "psi-data/PSI-159/Raw Data/Reduced Gravity/21088/21088B1/TP.txt"),
            ("PSI-159", "r2", "psi-data/PSI-159/Raw Data/Reduced Gravity/21088/21088A1/TP.txt"),
        ]
    )
    cfg = config_for(NORMAL, "PSI-159", index)
    trials = apply_mapping(cfg, "v", read_table(NORMAL), "res-test")[:3]  # 21088A1, "21088 B1", "21088 C1"
    links, status = link_trials(trials, index)
    by_id = {link["trial_id_raw"]: link for link in links}
    assert by_id["21088A1"]["match_type"] == "exact_literal" and by_id["21088A1"]["normalization"] is None
    assert by_id["21088 B1"]["match_type"] == "exact_after_normalization"
    assert by_id["21088 B1"]["normalization"] == "strip_whitespace"
    assert list(status.values()) == ["linked", "linked", "unlinked"]


def test_short_ids_are_not_path_matched():
    index = SegmentIndex([("PSI-99", "r", "psi-data/PSI-99/Raw Data/2-1/x.txt")])
    trials = apply_mapping(config_for(SAFFIRE2, "PSI-99"), "v", read_table(SAFFIRE2), "r")
    _, status = link_trials(trials, index)
    assert status[trials[0]["trial_key"]] == "id_too_short"


# --- download safety --------------------------------------------------------------------


class _Resp:
    def __init__(self, body: bytes):
        self.status_code, self._body = 200, body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def iter_content(self, n):
        yield self._body


class _Client:
    timeout = (1, 1)

    def __init__(self, body: bytes):
        self.session = type("S", (), {"get": lambda _s, url, **kw: _Resp(body)})()

    def get_download_url(self, *a):
        return "https://bucket.example/x.csv?X-Amz-Signature=SECRET"


def _target(size: int) -> Target:
    return Target("res-1", "PSI-1", "Experimental table", "psi-data/PSI-1/t.csv", "t.csv", 1, size)


def test_fetch_checks_size_and_never_leaks_url(tmp_path):
    dest = tmp_path / "t.csv"
    assert len(fetch(_Client(b"abc"), _target(3), dest, 100)) == 64 and dest.read_bytes() == b"abc"
    with pytest.raises(DownloadError) as exc:
        fetch(_Client(b"abcd"), _target(3), tmp_path / "u.csv", 100)
    assert "SECRET" not in str(exc.value) and not (tmp_path / "u.csv").exists()
    with pytest.raises(DownloadError, match="cap"):
        fetch(_Client(b"x" * 10), _target(10), tmp_path / "v.csv", 5)
