"""Bilingual (EN/DE) relevance scoring tailored to AI/Software internships & junior roles."""

from __future__ import annotations

import re

from job_radar.models import RawJob, ScoredJob, ScoringConfig
from job_radar.store import compute_fingerprint


def _compile_keyword_pattern(keyword: str) -> re.Pattern[str]:
    """Build a boundary-aware case-insensitive regex so short tokens (e.g. 'ai') don't false-match."""
    escaped = re.escape(keyword.strip().lower())
    return re.compile(rf"(?<![a-z0-9äöüß]){escaped}(?![a-z0-9äöüß])", re.IGNORECASE)


def _find_matches(text: str, keywords: list[str]) -> list[str]:
    matched: list[str] = []
    for kw in keywords:
        if _compile_keyword_pattern(kw).search(text):
            matched.append(kw)
    return matched


def score_job(job: RawJob, config: ScoringConfig) -> ScoredJob:
    """Score a normalized RawJob against role, domain, location, and exclusion rules."""
    fingerprint = compute_fingerprint(job)
    title_text = job.title.lower()
    full_text = f"{job.title} {job.location} {job.snippet}".lower()

    excluded = _find_matches(title_text, config.exclude_keywords)
    if excluded:
        return ScoredJob(
            fingerprint=fingerprint,
            job=job,
            score=-10,
            excluded_reason=f"excluded keyword in title: {', '.join(excluded)}",
        )

    role_matches = _find_matches(full_text, config.role_keywords)
    domain_matches = _find_matches(full_text, config.domain_keywords)
    location_matches = _find_matches(full_text, config.location_keywords)

    score = 0
    if role_matches:
        score += 3
    # Cap domain contribution so verbose descriptions don't overpower missing role/domain fit.
    score += min(len(domain_matches) * 2, 6)
    if location_matches:
        score += 1
    if job.tier == "A":
        score += 1

    # Require at least one domain OR role signal so generic non-tech roles in Linz don't trigger.
    if not domain_matches and not role_matches:
        score = 0

    return ScoredJob(
        fingerprint=fingerprint,
        job=job,
        score=score,
        role_matches=role_matches,
        domain_matches=domain_matches,
        location_matches=location_matches,
    )
