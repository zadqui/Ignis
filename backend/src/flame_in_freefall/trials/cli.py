"""``uv run fif-trials {download,draft,build}`` — M2 experimental tables → Ensayos."""

from __future__ import annotations

import argparse
import logging
import sys
from collections import Counter
from pathlib import Path

from ..psi.client import PsiClient
from ..psi.download import DEFAULT_MAX_BYTES, download_selected
from .build import build, draft_all


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="M2: experimental tables → trials")
    p.add_argument("--psi-dir", type=Path, default=Path("data/psi"))
    p.add_argument("--mappings-dir", type=Path, default=Path("mappings/experimental_tables"))
    p.add_argument("--out-dir", type=Path, default=Path("data/trials"))
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("download", help="download experimental tables listed in the inventory")
    d.add_argument("--only", action="append", metavar="PSI-N")
    d.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    dr = sub.add_parser("draft", help="write draft mapping YAMLs (never overwrites unless --force)")
    dr.add_argument("--force", action="store_true")
    sub.add_parser("build", help="parse, map and link all downloaded tables")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    psi_dir = args.psi_dir.resolve()

    if args.cmd == "download":
        rep = download_selected(PsiClient(), psi_dir, only=args.only, max_bytes=args.max_bytes)
        print(
            f"fetched {len(rep.fetched)} | cached {len(rep.cached)} | skipped {len(rep.skipped)} | failed {len(rep.failed)}"
        )
        for t, why in rep.skipped + rep.failed:
            print(f"  {t.path}: {why}")
        if rep.failed:
            return 1
    elif args.cmd == "draft":
        res = draft_all(psi_dir, args.mappings_dir, force=args.force)
        for name, wrote in res:
            print(("written  " if wrote else "kept     ") + name)
    else:
        out = build(psi_dir, args.mappings_dir, args.out_dir.resolve())
        print(f"\n{'table':<52} {'grain':<17} {'status':<8} {'trials':>6} {'linked':>6} {'unlinked':>8}")
        for t in out["tables"]:
            print(
                f"{t['file_name'][:52]:<52} {t['grain']:<17} {t['mapping_status']:<8} "
                f"{t['n_trials']:>6} {t['n_linked']:>6} {t['n_unlinked']:>8}"
            )
        grains = Counter(t["row_grain"] for t in out["trials"])
        print(
            f"\n{len(out['tables'])} tables | {len(out['table_rows'])} CSV records | "
            f"{len(out['trials'])} observations {dict(grains)} | {len(out['trial_resource_links'])} links"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
