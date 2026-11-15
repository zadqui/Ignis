"""Validation models for the observed (non-contractual) PSI geode-py responses.

Only the fields M1 relies on are declared; everything else is tolerated
(``extra="allow"``) so harmless upstream additions do not break the inventory,
while missing or mistyped required fields raise ``PsiSchemaError``.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


class PsiSchemaError(RuntimeError):
    """A PSI response did not match the schema observed during the survey."""


class _Loose(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)


# --- GET /repo/search -------------------------------------------------------


class SearchSource(_Loose):
    accession: str = Field(alias="Accession")
    title: str = Field(alias="Title")
    research_area: str = Field(alias="Research Area")
    project_type: str | None = Field(default=None, alias="Project Type")


class SearchHit(_Loose):
    source: SearchSource = Field(alias="_source")


class SearchHits(_Loose):
    total: int
    hits: list[SearchHit]


class SearchResponse(_Loose):
    hits: SearchHits


# --- GET /repo/investigations/{accession} -----------------------------------


class Publication(_Loose):
    title: str | None = None
    doi: str | None = None
    authorList: str | None = None
    pubMedID: str | None = None


class InvestigationDetail(_Loose):
    accession: str
    title: str
    version: int
    totalFileSize: float
    researchArea: str
    projectType: str | None = None
    subResearchArea: str | None = None
    flightProgram: str | None = None
    investigationAcronym: str | None = None
    experimentHardware: str | None = None
    doi: str | None = None
    releaseDate: str | None = None
    submissionDate: str | None = None
    modifiedDate: str | None = None
    versionReason: str | None = None
    investigationStartDate: str | None = None
    investigationEndDate: str | None = None
    managingNasaCenter: str | None = None
    spaceProgram: str | None = None
    funding: str | None = None
    related_glds: str | None = None
    licenseIdentifier: str | None = None
    restricted: bool | None = None
    public: bool | None = None
    objective: str | None = None
    hypothesis: str | None = None
    approach: str | None = None
    researchImpacts: str | None = None
    publications: list[Publication] = Field(default_factory=list)
    experimentalTable: list[dict[str, Any]] = Field(default_factory=list)


# --- POST /files/v2 ---------------------------------------------------------


class TreeNode(_Loose):
    """A folder or a file in the /files/v2 tree.

    Files carry ``directory: false``; folders omit ``directory`` and carry
    ``displayName``. Both may nest further nodes in ``files``.
    """

    key: str
    files: list[TreeNode] = Field(default_factory=list)
    directory: bool | None = None
    id: str | None = None
    bytes_size: float | None = None
    size: str | int | None = None
    version: int | None = None
    sortingCategory: str | None = None
    subcategory: str | None = None
    status: str | None = None
    updated: str | None = None
    restricted: bool | None = None
    restrictedAccess: bool | None = None
    visible: bool | None = None
    displayName: str | None = None

    @property
    def is_file(self) -> bool:
        return self.directory is False

    @model_validator(mode="after")
    def _files_have_identity(self) -> TreeNode:
        if self.is_file:
            missing = [f for f in ("id", "bytes_size", "version") if getattr(self, f) is None]
            if missing:
                raise ValueError(f"file node {self.key!r} lacks {missing}")
        return self


class FilesResponse(_Loose):
    files: list[TreeNode]


def parse(model: type[BaseModel], payload: Any, context: str) -> Any:
    """Validate ``payload`` against ``model`` or raise ``PsiSchemaError``."""
    try:
        return model.model_validate(payload)
    except ValidationError as exc:
        raise PsiSchemaError(f"{context}: unexpected response schema\n{exc}") from exc


# Keys that may hold signed URLs or personal contact data; never persisted.
REDACTED_KEYS = frozenset({"remote_url", "email", "phone", "fax"})


def redact(obj: Any) -> Any:
    """Return a deep copy of ``obj`` without ``REDACTED_KEYS`` at any depth."""
    if isinstance(obj, dict):
        return {k: redact(v) for k, v in obj.items() if k not in REDACTED_KEYS}
    if isinstance(obj, list):
        return [redact(v) for v in obj]
    return obj
