"""Split the current selection's Kaggle-route units into chunk unit-lists for the mass run (no repeated work).

Units already present in any imported run (finding_candidates) are skipped. Deterministic order (unit hash).
Usage: uv run python kaggle/mass_chunks.py <n_chunks> <out_dir>
"""

import hashlib
import json
import sys
from pathlib import Path

import duckdb

n_chunks, out_dir = int(sys.argv[1]), Path(sys.argv[2])
sel = Path("data/findings/CURRENT_SELECTION").read_text().strip()
con = duckdb.connect()
units = [r[0] for r in con.execute(
    f"SELECT unit_id FROM read_parquet('data/findings/selections/{sel}/units.parquet') "
    "WHERE route = 'kaggle' AND origin NOT IN ('openalex_abstract', 'semantic_scholar_abstract')").fetchall()]
done = {r[0] for r in con.execute(
    "SELECT DISTINCT unit_id FROM read_parquet('data/findings/finding_candidates.parquet')").fetchall()}
todo = sorted((u for u in units if u not in done), key=lambda u: hashlib.sha256(u.encode()).hexdigest())
out_dir.mkdir(parents=True, exist_ok=True)
size = -(-len(todo) // n_chunks)
for i in range(n_chunks):
    part = todo[i * size:(i + 1) * size]
    (out_dir / f"chunk{i + 1}.json").write_text(json.dumps(
        [{"unit_id": u, "reason": f"mass run p-6, chunk {i + 1}/{n_chunks} of selection {sel}"} for u in part]))
    print(f"chunk{i + 1}: {len(part)} units")
print(f"selection {sel}: {len(units)} kaggle units, {len(done & set(units))} already processed, {len(todo)} to run")
