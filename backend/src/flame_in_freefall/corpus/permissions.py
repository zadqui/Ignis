"""Text-use permission rules (decided 11 Nov 2026).

Every decision is one of ``allowed`` / ``metadata_only`` / ``unclear`` with the
rule id and a verifiable basis. Text is extracted and kept **only** for
``allowed``. Files and texts stay local (``data/``, git-ignored); nothing is
redistributed. Overrides need a verifiable source (``config/permission_overrides.yaml``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

ALLOWED, METADATA_ONLY, UNCLEAR = "allowed", "metadata_only", "unclear"

OPEN_LICENSES = {
    "cc0",
    "cc-0",
    "cc0-1.0",
    "public-domain",
    "pd",
    "publicdomain",
    "cc-by",
    "cc-by-sa",
    "cc-by-nc",
    "cc-by-nc-sa",
    "cc-by-nd",
    "cc-by-nc-nd",
}

# Explicit third-party rights notices. Publisher names alone (e.g. in reference
# lists) are NOT notices, nor is a bare "©" glyph (symbol fonts, garbled text):
# it must be followed by a year or the word "copyright".
NOTICE = re.compile(
    r"(©\s*((19|20)\d\d|copyright)|\(c\)\s*(19|20)\d\d|copyright\s*(©|\(c\)|(19|20)\d\d)|all rights reserved"
    r"|reprinted (with|by) permission"
    r"|export[- ]controlled|\bITAR\b|\bEAR99\b)",
    re.IGNORECASE,
)


@dataclass
class Decision:
    permission: str
    rule: str
    basis: str

    def as_row(self) -> dict[str, str]:
        return {"permission": self.permission, "permission_rule": self.rule, "permission_basis": self.basis}


# --- PSI investigations ------------------------------------------------------------


def investigation_license_status(ficha_license: str | None, datacite_rights: list[str] | None) -> tuple[str, str]:
    """(status, basis) for the documents of one investigation."""
    lic = (ficha_license or "").lower()
    dc = [r.lower() for r in (datacite_rights or [])]
    if lic.startswith("cc0") and any(r.startswith("cc0") for r in dc):
        return "cc0_confirmed", "PSI record licenseIdentifier=CC0-1.0 and DataCite rightsList=cc0-1.0"
    if lic.startswith("cc0") and datacite_rights is None:
        return "cc0_psi_only", "PSI record licenseIdentifier=CC0-1.0; DataCite record not found (no corroboration)"
    if lic.startswith("cc0"):
        return "cc0_conflict", f"PSI record CC0-1.0 but DataCite rights {dc}"
    return "license_unconfirmed", "PSI record has no license; DataCite declares no rights"


def psi_document(inv_statuses: dict[str, tuple[str, str]]) -> Decision:
    """A file may be published by several investigations: use the clearest grant."""
    for wanted in ("cc0_confirmed", "cc0_psi_only"):
        for inv, (status, basis) in sorted(inv_statuses.items()):
            if status == wanted:
                return Decision(ALLOWED, f"psi_{status}", f"{inv}: {basis}")
    inv, (status, basis) = min(inv_statuses.items())
    return Decision(METADATA_ONLY, f"psi_{status}", f"{inv}: {basis}")


def notices_in(pages: list[tuple[int, str]]) -> list[str]:
    hits = []
    for page_no, text in pages:
        for m in NOTICE.finditer(text):
            a, b = max(0, m.start() - 60), min(len(text), m.end() + 60)
            hits.append(f"p{page_no}: {' '.join(text[a:b].split())}")
    return list(dict.fromkeys(hits))


def after_notice_check(decision: Decision, notices: list[str]) -> Decision:
    if decision.permission == ALLOWED and notices:
        return Decision(
            UNCLEAR,
            "third_party_notice",
            f"dataset licence may not cover third-party content; notice: {notices[0][:160]}",
        )
    return decision


# --- remote locations ------------------------------------------------------------------


def oa_location(loc: dict[str, Any], oa_status: str | None) -> Decision:
    lic = (loc.get("license") or "").lower()
    version = loc.get("version")
    if lic in OPEN_LICENSES:
        return Decision(ALLOWED, "explicit_open_license", f"license={lic}; version={version}; via OpenAlex")
    if not lic:
        rule = {"bronze": "bronze_no_license", "green": "green_no_license"}.get(oa_status or "", "no_license")
        return Decision(
            METADATA_ONLY, rule, f"free to read but no explicit licence (oa_status={oa_status}, version={version})"
        )
    return Decision(UNCLEAR, "nonstandard_license", f"license={lic}: terms not machine-checkable")


def api_abstract(source: str) -> Decision:
    return Decision(
        ALLOWED, "abstract_from_api", f"abstract distributed by the {source} API; kept local, not redistributed"
    )


def ntrs_record(rec: dict[str, Any]) -> Decision:
    det = ((rec.get("copyright") or {}).get("determinationType")) or ""
    dist = rec.get("distribution") or ""
    if det == "PUBLIC_USE_PERMITTED" and dist == "PUBLIC":
        return Decision(ALLOWED, "ntrs_public_use", f"NTRS copyright.determinationType={det}, distribution={dist}")
    return Decision(
        METADATA_ONLY, "ntrs_not_public_use", f"NTRS determinationType={det or 'missing'}, distribution={dist}"
    )


# --- overrides ------------------------------------------------------------------------------


def load_overrides(path: Path) -> dict[str, dict[str, Any]]:
    """{target (sha256 or doi): override}; each needs permission, basis (verifiable source), reviewed_by."""
    if not path.exists():
        return {}
    out = {}
    for it in yaml.safe_load(path.read_text(encoding="utf-8")) or []:
        missing = [k for k in ("target", "permission", "basis", "reviewed_by") if not it.get(k)]
        if missing or it["permission"] not in (ALLOWED, METADATA_ONLY, UNCLEAR):
            raise ValueError(f"permission override {it} invalid (missing {missing})")
        out[it["target"].lower()] = it
    return out


def apply_override(decision: Decision, ov: dict[str, Any] | None) -> Decision:
    if not ov:
        return decision
    return Decision(ov["permission"], "reviewer_override", f"{ov['basis']} (reviewed by {ov['reviewed_by']})")
