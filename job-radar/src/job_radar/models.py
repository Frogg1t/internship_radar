"""Pydantic data models for companies, jobs, scoring, and run summaries."""

from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field


Tier = Literal["A", "B", "skip"]


class CompanyConfig(BaseModel):
    """Configuration for a single target organization."""

    id: str
    name: str
    tier: Tier = "B"
    enabled: bool = True
    adapter: str = "auto"
    career_url: str
    ats_slug: str | None = None
    aliases: list[str] = Field(default_factory=list)
    notes: str | None = None


class ScoringConfig(BaseModel):
    """Keyword lists and score thresholds for bilingual job relevance."""

    min_notify_score: int = 3
    high_priority_score: int = 6
    max_bootstrap_alerts: int = 10
    role_keywords: list[str] = Field(default_factory=list)
    domain_keywords: list[str] = Field(default_factory=list)
    location_keywords: list[str] = Field(default_factory=list)
    exclude_keywords: list[str] = Field(default_factory=list)


class BoardsConfig(BaseModel):
    """External job board URLs monitored alongside company career portals."""

    jku_jobboerse_urls: list[str] = Field(default_factory=list)
    karriere_at_queries: list[str] = Field(default_factory=list)


class ProfileConfig(BaseModel):
    """Top-level profile YAML schema."""

    scoring: ScoringConfig
    boards: BoardsConfig = Field(default_factory=BoardsConfig)


class RawJob(BaseModel):
    """Normalized job listing produced by any adapter before scoring."""

    company_id: str
    company_name: str
    title: str
    url: str
    location: str = ""
    snippet: str = ""
    source_type: str = "html"
    tier: Tier = "B"
    external_id: str | None = None


class ScoredJob(BaseModel):
    """Job listing enriched with deduplication fingerprint and relevance score."""

    fingerprint: str
    job: RawJob
    score: int
    role_matches: list[str] = Field(default_factory=list)
    domain_matches: list[str] = Field(default_factory=list)
    location_matches: list[str] = Field(default_factory=list)
    excluded_reason: str | None = None

    @property
    def is_excluded(self) -> bool:
        return self.excluded_reason is not None


class AdapterOutcome(BaseModel):
    """Result of fetching a single source (company or board)."""

    source_id: str
    source_name: str
    url: str
    ok: bool
    detected_kind: str = "none"
    jobs: list[RawJob] = Field(default_factory=list)
    error: str | None = None


class RunSummary(BaseModel):
    """Aggregated statistics for a radar execution."""

    sources_checked: int = 0
    sources_failed: int = 0
    total_fetched: int = 0
    new_listings: int = 0
    matched_listings: int = 0
    notified_listings: int = 0
