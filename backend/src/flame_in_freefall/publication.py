"""Publication policy (config/publication_policy.yaml): what may leave the private workspace.

Applies to COPIES only (public export of the demo database, uploads to Kaggle); internal data and scientific
results are never modified. Every decision carries the rule that produced it, for traceability.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

DEFAULT_POLICY = Path(__file__).resolve().parents[2] / "config" / "publication_policy.yaml"
WITHHELD = "withheld"
_LICENSE_RE = re.compile(r"license=([a-z0-9.\-]+)", re.IGNORECASE)


@dataclass(frozen=True)
class Display:
    pub_class: str
    quote: bool
    claim: bool
    attribution_required: bool
    license_label: str
    reason: str

    def as_row(self) -> dict[str, Any]:
        return {"pub_class": self.pub_class, "show_quote": self.quote, "show_claim": self.claim,
                "attribution_required": self.attribution_required, "license_label": self.license_label,
                "pub_reason": self.reason}


class Policy:
    def __init__(self, path: Path = DEFAULT_POLICY):
        raw = path.read_bytes()
        self.cfg = yaml.safe_load(raw)
        self.version = self.cfg["version"]
        self.sha256 = hashlib.sha256(raw).hexdigest()
        for cls in list(self.cfg["rules"].values()) + list(self.cfg["licenses"].values()):
            if cls != "by_license" and cls not in self.cfg["classes"]:
                raise ValueError(f"publication policy: unknown class {cls!r}")

    def _display(self, cls: str, label: str, reason: str) -> Display:
        c = self.cfg["classes"][cls]
        return Display(cls, c["quote"], c["claim"], c["attribution_required"], label, reason)

    def classify(self, doc: dict[str, Any]) -> Display:
        """doc: a row of `documents` (origin, permission, permission_rule, permission_basis, license_status)."""
        origin, perm, rule = doc.get("origin"), doc.get("permission"), doc.get("permission_rule")
        if origin in self.cfg["withheld_origins"]:
            return self._display(WITHHELD, "redistribution not permitted / unverified",
                                 f"origin {origin} is always withheld")
        if perm != "allowed":
            return self._display(WITHHELD, "unknown or restricted", f"permission={perm} ({rule})")
        cls = self.cfg["rules"].get(rule or "")
        if cls is None:
            return self._display(WITHHELD, "unknown", f"rule {rule} not in publication policy")
        if cls == "by_license":
            m = _LICENSE_RE.search(doc.get("permission_basis") or "")
            lic = m.group(1).lower() if m else ""
            cls = self.cfg["licenses"].get(lic)
            if cls is None:
                return self._display(WITHHELD, lic or "unknown", f"licence {lic or '(none)'} not in policy")
            return self._display(cls, lic.upper(), f"{rule}: licence {lic}")
        label = {"psi_cc0_confirmed": "CC0 (PSI record + DataCite)",
                 "psi_cc0_psi_only": "CC0 (PSI record; DataCite corroboration pending)"}.get(rule, rule)
        return self._display(cls, label, f"rule {rule}")

    def kaggle_allowed(self, doc: dict[str, Any]) -> bool:
        return self.classify(doc).pub_class in self.cfg["kaggle_upload_classes"]

    def withheld_investigation(self, license_status: str | None) -> bool:
        return (license_status or "") in self.cfg["withheld_investigation_license_status"]
