"""Unit tests for bilingual DE/EN relevance scoring."""

from job_radar.config import load_profile
from job_radar.models import RawJob
from job_radar.scorer import score_job


def test_internship_ai_linz_scores_high() -> None:
    profile = load_profile()
    job = RawJob(
        company_id="mindbreeze",
        company_name="Mindbreeze GmbH",
        title="Werkstudent / Internship Artificial Intelligence & Python (m/w/d)",
        url="https://www.mindbreeze.com/jobs/ai-intern",
        location="Linz",
        snippet="Work on LLM pipelines and RAG systems.",
        tier="A",
    )
    scored = score_job(job, profile.scoring)
    assert not scored.is_excluded
    assert scored.score >= profile.scoring.high_priority_score
    assert "ai" in scored.domain_matches or "artificial intelligence" in scored.domain_matches
    assert "python" in scored.domain_matches
    assert "linz" in scored.location_matches


def test_senior_and_lehrling_roles_are_excluded() -> None:
    profile = load_profile()
    senior = RawJob(
        company_id="fabasoft",
        company_name="Fabasoft",
        title="Senior AI Solutions Architect (m/w/d)",
        url="https://www.fabasoft.com/jobs/1",
        tier="A",
    )
    lehrling = RawJob(
        company_id="engel",
        company_name="ENGEL",
        title="Lehrling Mechatronik (m/w/d)",
        url="https://jobs.engelglobal.com/1",
        tier="A",
    )
    assert score_job(senior, profile.scoring).is_excluded
    assert score_job(lehrling, profile.scoring).is_excluded


def test_short_ai_token_does_not_false_match_maintenance() -> None:
    profile = load_profile()
    job = RawJob(
        company_id="alpla",
        company_name="ALPLA",
        title="Facility Maintenance Technician",
        url="https://career.alpla.com/jobs/maint-1",
        location="Linz",
        tier="B",
    )
    scored = score_job(job, profile.scoring)
    assert scored.domain_matches == []
    assert scored.score == 0
