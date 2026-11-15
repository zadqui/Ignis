"""Quality metrics per run (block) and for the whole set, from the imported runs and the verification tables.

Usage: uv run python kaggle/mass_report.py [run_id ...]   (default: every run-mass-p6-c* imported)
Per run: units, valid JSON (unit level), truncations, candidates extracted, statuses (machine_verified, duplicate,
rejected, no_finding), rejection reasons, machine_verified (duplicates excluded) by finding type and attribution,
batch metrics.
"""

import json
import sys
from collections import Counter
from pathlib import Path

import duckdb

RUNS = Path("data/findings/runs")
run_ids = sys.argv[1:] or sorted(p.name for p in RUNS.glob("run-mass-p6-c*") if (p / "run_manifest.json").exists())
con = duckdb.connect()
cand = "read_parquet('data/findings/finding_candidates.parquet')"
mf = "read_parquet('data/findings/machine_findings.parquet')"
report, total = {}, Counter()
types_total, attr_total, reasons_total = Counter(), Counter(), Counter()
for rid in run_ids:
    raw = [json.loads(x) for x in (RUNS / rid / "raw.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    units = {r["unit_id"] for r in raw}
    trunc = sum(r.get("finish_reason") == "length" for r in raw)
    unit_parse = dict(con.execute(f"SELECT unit_id, min(parse_status) FROM {cand} WHERE run_id = ? GROUP BY 1",
                                  [rid]).fetchall())
    valid = sum(1 for u in units if unit_parse.get(u) in ("ok", "empty"))
    n_cand = con.execute(f"SELECT count(*) FROM {cand} WHERE run_id = ? AND parse_status = 'ok'", [rid]).fetchone()[0]
    status = Counter(dict(con.execute(f"SELECT status, count(*) FROM {mf} WHERE run_id = ? GROUP BY 1", [rid]).fetchall()))
    reasons = Counter()
    for (rs,) in con.execute(f"SELECT reasons FROM {mf} WHERE run_id = ? AND status = 'rejected'", [rid]).fetchall():
        reasons.update(rs or ["(none)"])
    # duplicates restate an already verified finding: counted apart (status_duplicate), never as extra evidence
    verified = "status = 'machine_verified'"
    types = Counter(dict(con.execute(f"SELECT claim_type, count(*) FROM {mf} WHERE run_id = ? AND {verified} "
                                     "GROUP BY 1", [rid]).fetchall()))
    attr = Counter(dict(con.execute(f"SELECT coalesce(attribution, 'n/a'), count(*) FROM {mf} WHERE run_id = ? AND "
                                    f"{verified} GROUP BY 1", [rid]).fetchall()))
    mp = Path("data/findings/kaggle_runs") / f"fif-m4-mass-run-{rid.split('-')[-1]}" / "logs" / "batch_metrics.jsonl"
    batches = [json.loads(x) for x in mp.read_text().splitlines() if x.strip()] if mp.exists() else []
    man = json.loads((RUNS / rid / "run_manifest.json").read_text(encoding="utf-8"))
    row = {"units": len(units), "valid_json_units": valid, "valid_json_pct": round(100 * valid / max(len(units), 1), 1),
           "truncated": trunc, "candidates_extracted": n_cand, **{f"status_{k}": v for k, v in status.items()},
           "reject_rate_pct": round(100 * status["rejected"] / max(n_cand, 1), 1),
           "types_verified": dict(types), "attribution_verified": dict(attr), "rejection_reasons": dict(reasons),
           "batches": len(batches), "worst_batch_bad_rate": max((b["bad_rate"] for b in batches), default=None),
           "stopped": man.get("stopped"), "prompt_version": man.get("prompt_version"), "seconds": man.get("seconds")}
    report[rid] = row
    total.update({"units": len(units), "valid_json_units": valid, "truncated": trunc, "candidates_extracted": n_cand,
                  **{f"status_{k}": v for k, v in status.items()}})
    types_total.update(types)
    attr_total.update(attr)
    reasons_total.update(reasons)
report["TOTAL"] = {**dict(total), "valid_json_pct": round(100 * total["valid_json_units"] / max(total["units"], 1), 1),
                   "reject_rate_pct": round(100 * total["status_rejected"] / max(total["candidates_extracted"], 1), 1),
                   "types_verified": dict(types_total), "attribution_verified": dict(attr_total),
                   "rejection_reasons": dict(reasons_total)}
out = Path("data/findings/mass_run/report.json")
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(report, indent=2), encoding="utf-8")
cols = ["units", "valid_json_pct", "truncated", "candidates_extracted", "status_machine_verified", "status_duplicate",
        "status_rejected", "reject_rate_pct", "status_no_finding"]
print("| run | " + " | ".join(cols) + " | verified by type |")
print("|" + "---|" * (len(cols) + 2))
for rid, r in report.items():
    print(f"| {rid} | " + " | ".join(str(r.get(c, 0)) for c in cols) + f" | {r['types_verified']} |")
print("\nrejection reasons (total):", dict(reasons_total.most_common()))
print("attribution of verified (total):", dict(attr_total))
