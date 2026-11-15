"""Versioned contracts for the evidence-based research API."""

from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class EvidenceStatus(Contract):
    source_located: bool = False
    quote_verified: bool = False
    claim_checked: bool = False
    scientific_review_confirmed: bool = False
    insufficient: bool = True


class Citation(Contract):
    citation_id: str
    inv_ids: list[str]
    doc_id: str | None = None
    finding_id: str | None = None
    title: str
    authors: str | None = None
    year: int | None = None
    doi: str | None = None
    url: str | None = None
    page: int | None = None
    quote: str | None = None
    license: str | None = None
    status: EvidenceStatus = Field(default_factory=EvidenceStatus)


class ScientificFinding(Contract):
    finding_id: str
    inv_ids: list[str]
    kind: str
    claim: str | None = None
    attribution: str | None = None
    variable: str | None = None
    effect_on: str | None = None
    direction: str | None = None
    conditions: dict[str, Any] = Field(default_factory=dict)
    values: list[dict[str, Any]] = Field(default_factory=list)
    citation: Citation


class ExperimentalMeasurement(Contract):
    variable: str
    minimum: float | None = None
    maximum: float | None = None
    unit: str | None = None
    role: str = "recorded_condition"
    provenance: dict[str, Any] = Field(default_factory=dict)
    uncertainty: str = "not_reported_in_normalized_data"


class Experiment(Contract):
    trial_key: str
    inv_id: str
    experiment_id: str | None = None
    entity_type: str = "trial"
    row_grain: str | None = None
    fuel: str | None = None
    geometry: str | None = None
    methodology: str | None = None
    measurements: list[ExperimentalMeasurement]
    source_resource_id: str
    row_ref: str
    mapping_status: str | None = None
    interpretation_verified: bool = False
    raw_observations: dict[str, Any] = Field(default_factory=dict)


class ResearchFilters(Contract):
    inv_ids: list[str] = Field(default_factory=list, max_length=50)
    categories: list[str] = Field(default_factory=list, max_length=8)
    material: str | None = Field(default=None, max_length=200)
    fuel: str | None = Field(default=None, max_length=200)
    gravity: str | None = Field(default=None, max_length=100)
    project_type: str | None = Field(default=None, max_length=100)
    instrumentation: str | None = Field(default=None, max_length=200)
    security_application: str | None = Field(default=None, max_length=200)
    o2_pct: float | None = Field(default=None, ge=0, le=100)
    pressure_kpa: float | None = Field(default=None, gt=0, le=100000)
    flow_cm_s: float | None = Field(default=None, ge=0, le=100000)
    gravity_g: float | None = Field(default=None, ge=0, le=100)


class ResearchSearchRequest(Contract):
    query: str = Field(min_length=1, max_length=2000)
    filters: ResearchFilters = Field(default_factory=ResearchFilters)
    offset: int = Field(default=0, ge=0, le=100000)
    limit: int = Field(default=20, ge=1, le=100)


class ResearchSearchResult(Contract):
    inv_id: str
    title: str
    acronym: str | None = None
    description: str | None = None
    categories: list[dict[str, Any]]
    relevance: dict[str, Any]
    applicability: str = "not_established"
    related_findings: list[ScientificFinding]
    references: list[Citation]


class InvestigationDetail(Contract):
    inv_id: str
    title: str
    acronym: str | None = None
    project_type: str | None = None
    entity_type: str = "investigation"
    description: str | None = None
    sections: dict[str, list[dict[str, Any]]]
    categories: list[dict[str, Any]]
    facets: dict[str, list[dict[str, Any]]]
    findings: list[ScientificFinding]
    references: list[Citation]
    publications: list[dict[str, Any]]
    trial_count: int
    trial_conditions: list[dict[str, Any]] = Field(default_factory=list)
    missing_fields: list[str]
    warnings: list[str]
    gaps: list[dict[str, Any]] = Field(default_factory=list)


class ComparisonRequest(Contract):
    investigation_ids: list[str] = Field(default_factory=list, max_length=8)
    trial_keys: list[str] = Field(default_factory=list, max_length=20)


class ComparisonResult(Contract):
    entity_type: str
    ids: list[str]
    variables: list[dict[str, Any]]
    similarities: list[dict[str, Any]]
    differences: list[dict[str, Any]]
    relations: list[dict[str, Any]]
    compatibility: dict[str, Any]
    conclusions: list[dict[str, Any]]
    references: list[Citation]
    warnings: list[str]


class ScenarioRequest(Contract):
    query: str = Field(default="", max_length=2000)
    environment: Literal["space_station", "spacecraft", "lunar_base", "mars_base", "pressurized_vehicle"] | None = None
    material: str | None = Field(default=None, max_length=200)
    fuel: str | None = Field(default=None, max_length=200)
    gravity_g: float | None = Field(default=None, ge=0, le=100)
    pressure_kpa: float | None = Field(default=None, gt=0, le=100000)
    o2_pct: float | None = Field(default=None, ge=0, le=100)
    flow_cm_s: float | None = Field(default=None, ge=0, le=100000)
    phenomenon: str | None = Field(default=None, max_length=200)
    filters: ResearchFilters = Field(default_factory=ResearchFilters)
    limit: int = Field(default=10, ge=1, le=50)


class ScenarioAnalysis(Contract):
    criteria: dict[str, Any]
    oxygen_partial_pressure_kpa: float | None = None
    investigations: list[ResearchSearchResult]
    trials: list[dict[str, Any]]
    trial_total: int
    gaps: list[dict[str, Any]]
    implications: list[dict[str, Any]]
    recommendations: list[dict[str, Any]]
    references: list[Citation]
    warnings: list[str]


class InvestigationAnalysisRequest(Contract):
    investigation_id: str = Field(min_length=1, max_length=100)
    question: str = Field(default="Resultados principales y limitaciones", max_length=2000)


class Message(Contract):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=4000)


class AssistantRequest(Contract):
    question: str = Field(min_length=1, max_length=2000)
    investigation_ids: list[str] = Field(default_factory=list, max_length=8)
    finding_ids: list[str] = Field(default_factory=list, max_length=30)
    trial_keys: list[str] = Field(default_factory=list, max_length=20)
    filters: ResearchFilters = Field(default_factory=ResearchFilters)
    scenario: ScenarioRequest | None = None
    history: list[Message] = Field(default_factory=list, max_length=12)


class AIAnswer(Contract):
    interpretation: str
    statements: list[dict[str, Any]]
    evidence: list[ScientificFinding]
    finding_ids: list[str]
    references: list[Citation]
    limitations: list[str]
    warnings: list[str]
    evidence_status: EvidenceStatus
    context: dict[str, Any]
    structured: dict[str, Any] = Field(default_factory=dict)
    generation_mode: str = "extractive_grounded"


class SearchResponse(Contract):
    results: list[ResearchSearchResult]
    criteria: dict[str, Any]
    total: int
    offset: int
    limit: int
    mode: str
    warnings: list[str]


class Page(Contract):
    items: list[dict[str, Any]]
    total: int
    offset: int
    limit: int


T = TypeVar("T")


class Envelope(BaseModel, Generic[T]):
    data: T
    meta: dict[str, Any]
