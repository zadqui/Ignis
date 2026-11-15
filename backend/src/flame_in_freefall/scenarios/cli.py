"""``uv run fif-scenarios {validate,build}`` — M6 scenarios, coverage and gap diagnosis."""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

from .coverage import build
from .model import ConfigError, load_scenarios, load_tolerances


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="M6: scenarios → coverage and gaps")
    p.add_argument("--psi-dir", type=Path, default=Path("data/psi"))
    p.add_argument("--scenarios-dir", type=Path, default=Path("scenarios"))
    p.add_argument("--out-dir", type=Path, default=Path("data/scenarios"))
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("validate", help="check scenario and tolerance YAML (schema, sources, status)")
    sub.add_parser("build", help="coverage from M2 trials + M4 findings layer, gap diagnosis, DuckDB views")
    a = p.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    try:
        scen, tol = load_scenarios(a.scenarios_dir), load_tolerances(a.scenarios_dir)
    except ConfigError as e:
        print(f"invalid configuration: {e}")
        return 1
    if a.cmd == "validate":
        for s in scen:
            print(f"{s['scenario_id']:<20} v{s['version']} {s['status']:<11} assumptions={s['n_assumptions']} "
                  f"all_sources_verified={s['all_sources_verified']}")
        print(f"tolerances {tol['version']} ({tol['status']}): O2 ±{tol['o2_pp']} pp, pressure ±{tol['pressure_rel']:.0%}, "
              f"flow ±{tol['flow_cm_s']} cm/s")
        return 0
    out = build(a.psi_dir.resolve(), a.scenarios_dir.resolve(), a.out_dir.resolve())
    print(f"trial x dimension rows: {len(out['scenario_trial_coverage'])} | coverage rows: {len(out['scenario_coverage'])}")
    print("gaps by family/class:", dict(Counter((g['gap_family'], g['gap_class']) for g in out["scenario_gaps"])))
    print(f"findings-layer rows: {len(out['scenario_findings_evidence'])} | declared gaps (authors): {len(out['declared_gaps'])}")
    print("All trial-based results are PROVISIONAL (draft M2 mappings); scenarios provisional; tolerances exploratory.")
    return 0
