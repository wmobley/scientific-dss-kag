from enum import StrEnum
from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Mode(StrEnum):
    lexical = "lexical"
    hybrid = "hybrid"
    ontology = "ontology"
    kag = "kag"


class RetrievalRequest(StrictModel):
    query: str = Field(min_length=1, max_length=2000)
    mode: Mode = Mode.hybrid
    k: int = Field(default=3, ge=1, le=20)
    context: list[str] = Field(default_factory=list, max_length=15)

    @field_validator("query")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("query must contain non-whitespace text")
        return value.strip()

    @field_validator("context")
    @classmethod
    def known_context(cls, values):
        from .retrieval import CONCEPTS
        if any(v not in CONCEPTS for v in values):
            raise ValueError("context must contain known ontology class names")
        return sorted(set(values))


class Evidence(StrictModel):
    id: str
    source_id: str
    source_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    passage: str = Field(min_length=1)
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    concepts: list[str]
    review_status: str = Field(pattern=r"^(candidate|reviewed)$")
    origin: str


class Pathway(StrictModel):
    objective: str = Field(default="", max_length=2000)
    information_needs: list[str] = Field(default_factory=list, max_length=20)
    alternatives: list[str] = Field(default_factory=list, max_length=20)
    uncertainties: list[str] = Field(default_factory=list, max_length=20)
    evidence_ids: list[str] = Field(default_factory=list, max_length=50)

    @field_validator("information_needs", "alternatives", "uncertainties", "evidence_ids")
    @classmethod
    def bounded_items(cls, items):
        if any(len(item) > 2000 or not item.strip() for item in items):
            raise ValueError("items must be nonblank and at most 2000 characters")
        return items


class EvaluationRequest(StrictModel):
    k: int = Field(default=3, ge=1, le=20)
