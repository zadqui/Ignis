"""``uv run fif-corpus {download,build}`` — M3 text corpus."""

from __future__ import annotations

import argparse
import logging
import sys
from collections import Counter
from pathlib import Path

from .build import Paths, build, download


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="M3: PSI documents + DOI works → corpus")
    p.add_argument("--psi-dir", type=Path, default=Path("data/psi"))
    p.add_argument("--out-dir", type=Path, default=Path("data/corpus"))
    p.add_argument("--config-dir", type=Path, default=Path("config"))
    p.add_argument("--include-engineering", action="store_true", help="tier 2: Engineering Documents")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("download", help="download PSI text documents (tier 1, + tier 2 with flag)")
    d.add_argument("--only", action="append", metavar="PSI-N")
    b = sub.add_parser("build", help="resolve works, extract text, classify, segment")
    b.add_argument("--no-oa-fetch", action="store_true", help="do not fetch openly licensed full texts")
    b.add_argument("--no-ntrs", action="store_true")
    args = p.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    paths = Paths(args.psi_dir.resolve(), args.out_dir.resolve(), args.config_dir.resolve())

    if args.cmd == "download":
        rep = download(paths, args.include_engineering, args.only)
        print(
            f"fetched {len(rep.fetched)} | cached {len(rep.cached)} | skipped {len(rep.skipped)} | failed {len(rep.failed)}"
        )
        for t, why in rep.skipped + rep.failed:
            print(f"  {t.path}: {why}")
        return 1 if rep.failed else 0

    out = build(
        paths, include_engineering=args.include_engineering, fetch_oa=not args.no_oa_fetch, use_ntrs=not args.no_ntrs
    )
    psi = [d for d in out["documents"] if d["origin"] == "psi_internal"]
    print("\nPSI documents by status:", dict(Counter(d["processing_status"] for d in psi)))
    print("PSI documents by content_nature:", dict(Counter(d["content_nature"] for d in psi)))
    print("PSI documents by permission rule:", dict(Counter(d["permission_rule"] for d in psi)))
    print("works by evidence_level:", dict(Counter(w["evidence_level"] for w in out["works"])))
    print("link candidates:", dict(Counter(c["kind"] for c in out["link_candidates"])))
    print(f"pages {len(out['doc_pages'])} | sentences {len(out['doc_sentences'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
