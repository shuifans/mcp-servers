from typing import Literal
from pydantic import BaseModel, Field


SourceType = Literal["local_file", "ata", "yunzhidao", "public"]


class Location(BaseModel):
    page: int | None = None
    slide: int | None = None
    sheet: str | None = None
    cell_range: str | None = None
    section: str | None = None


class SearchResult(BaseModel):
    chunk_id: str
    document_id: str
    title: str
    content: str
    source_type: SourceType
    path: str | None = None
    url: str | None = None
    location: Location = Field(default_factory=Location)
    score: float = 0.0


class ChatRequest(BaseModel):
    question: str
    sources: list[SourceType] = Field(default_factory=lambda: ["local_file", "ata", "yunzhidao", "public"])


class ResearchMeta(BaseModel):
    queries: list[dict] = Field(default_factory=list)  # 所有执行的查询
    source_hits: dict[str, int] = Field(default_factory=dict)  # 各来源命中数
    retry_performed: bool = False
    gaps: list[str] = Field(default_factory=list)
    elapsed_ms: int = 0


class ChatResponse(BaseModel):
    answer: str
    citations: list[SearchResult]
    research: ResearchMeta | None = None


class LocalSourceRequest(BaseModel):
    path: str
    action: Literal["add", "remove"] = "add"
