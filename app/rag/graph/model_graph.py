from typing import List, Literal, Optional, TypedDict
from pydantic import BaseModel, Field
import operator
from typing import Annotated

class PlannedSub(BaseModel):
    question: str = Field(description="a complete standalone sub-question (keep IDs/names verbatim)")
    strategy: Literal["lookup", "list_all", "summarize", "visual"]
    doc: Optional[str] = Field(None, description="exact filename ONLY if exactly one document clearly matches; else null")
    pages: List[int] = Field(default_factory=list, description="page numbers if the question names specific pages")

class QueryPlan(BaseModel):
    subs: List[PlannedSub]

class CacheState():
    answer: str = ""
    sources: List[str] = []
    cached: False

class RAGState(TypedDict):
    question: str
    subs: List[dict]
    results: Annotated[list, operator.add]   
    answer: str
    cache_results: List[CacheState]
    retries: int
    verdict: str
    fix: dict

class PlanCoverage(BaseModel):
    missing: str = Field("", description="a requirement of the original question that NO sub-question covers; '' if fully covered")

class Reflection(BaseModel):
    grounded: bool = Field(description="is every factual claim in the answer supported by the evidence?")
    useful: bool   = Field(description="does the answer fully address EVERY part of the user's question?")
    problem: str   = Field("", description="what is unsupported or missing, if anything")