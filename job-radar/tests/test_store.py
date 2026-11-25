"""Unit tests for URL canonicalization and SeenJobsStore deduplication."""

from pathlib import Path

from job_radar.models import RawJob
from job_radar.store import SeenJobsStore, canonicalize_url, compute_fingerprint


def test_canonicalize_url_strips_tracking_and_trailing_slash() -> None:
    u1 = "HTTPS://Example.com/jobs/ai-intern/?utm_source=linkedin&id=42&fbclid=xyz"
    u2 = "https://example.com/jobs/ai-intern?id=42"
    assert canonicalize_url(u1) == canonicalize_url(u2)


def test_store_deduplicates_across_reload(tmp_path: Path) -> None:
    db_path = tmp_path / "seen_jobs.json"
    job = RawJob(
        company_id="keba",
        company_name="KEBA Group AG",
        title="Junior Python Developer",
        url="https://jobs.keba.com/job/123?utm_campaign=fair",
        tier="A",
    )
    fp = compute_fingerprint(job)

    store1 = SeenJobsStore(db_path)
    assert not store1.is_seen(fp)
    store1.mark_seen(fp, job, notified=True)
    store1.save()

    store2 = SeenJobsStore(db_path)
    assert store2.is_seen(fp)
    assert store2.count == 1
