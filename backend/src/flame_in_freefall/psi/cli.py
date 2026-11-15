"""``uv run fif-inventory`` — build the PSI metadata inventory (M1)."""

from __future__ import annotations

import argparse
import logging
import sys
from collections import defaultdict
from pathlib import Path

from .client import PsiClient
from .inventory import DEFAULT_AREA, InventoryResult, run_inventory
from .storage import save_snapshot


def _fmt_bytes(n: float) -> str:
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if n < 1024 or unit == "TiB":
            return f"{n:,.1f} {unit}"
        n /= 1024
    return str(n)


def print_summary(result: InventoryResult, snapshot: Path) -> None:
    v = {row["inv_id"]: row for row in result.versions}
    types = {i["inv_id"]: i["project_type"] or "?" for i in result.investigations}
    exp = defaultdict(int)
    for r in result.resources:
        exp[r["inv_id"]] += r["category"] == "Experimental table"
    print(
        f"\n{'inv_id':<9} {'project_type':<28} {'nodes':>7} {'records':>7} {'size':>11} "
        f"{'exp.tab':>7} {'v.confl':>7} {'repeat':>6}"
    )
    for inv in sorted(v, key=lambda a: int(a.split("-")[-1])):
        s = v[inv]
        print(
            f"{inv:<9} {types[inv]:<28} {s['n_tree_nodes']:>7} {s['n_files']:>7} "
            f"{_fmt_bytes(s['unique_record_bytes']):>11} {exp[inv]:>7} "
            f"{s['n_path_version_conflicts']:>7} {s['n_repeated_records']:>6}"
        )
    tot = lambda k: sum(s[k] for s in v.values())
    print(
        f"\n{len(result.investigations)} investigations | {tot('n_tree_nodes')} tree nodes | "
        f"{tot('n_files')} unique records | {tot('n_unique_paths')} unique paths | "
        f"{_fmt_bytes(tot('tree_node_bytes'))} as listed (totalFileSize) | "
        f"{_fmt_bytes(tot('unique_record_bytes'))} unique | "
        f"{sum(exp.values())} experimental-table files | "
        f"{tot('n_path_version_conflicts')} path-version conflicts | {result.api_calls} API calls"
    )
    for w in result.warnings:
        print(f"WARNING: {w}")
    print(f"snapshot: {snapshot}  (scope={result.scope})")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Inventory PSI investigations and file metadata (no downloads).")
    p.add_argument("--area", default=DEFAULT_AREA, help="PSI Research Area filter value")
    p.add_argument("--only", action="append", metavar="PSI-N", help="limit to these accessions (partial snapshot)")
    p.add_argument("--data-dir", type=Path, default=Path("data/psi"))
    p.add_argument("--page-size", type=int, default=50)
    p.add_argument("--pause", type=float, default=0.5, help="seconds between API calls")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    client = PsiClient(pause_s=args.pause)
    result = run_inventory(client, area=args.area, only=args.only, page_size=args.page_size)
    snapshot = save_snapshot(result, args.data_dir.resolve())
    print_summary(result, snapshot)
    return 0


if __name__ == "__main__":
    sys.exit(main())
