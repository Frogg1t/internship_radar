"""Unit tests for structured ATS feeds, HTML fallback, and mocked async fetches."""

import asyncio
import json

import httpx

from job_radar.adapters.html_links import extract_html_job_links, fetch_company_jobs
from job_radar.adapters.structured import extract_json_ld_jobs, parse_personio_xml
from job_radar.models import CompanyConfig


def _sample_company(adapter: str = "auto", url: str = "https://example.com/careers") -> CompanyConfig:
    return CompanyConfig(
        id="demo-co",
        name="Demo AI GmbH",
        tier="A",
        enabled=True,
        adapter=adapter,
        career_url=url,
    )


def test_extract_json_ld_job_posting() -> None:
    html = """
    <html><head>
    <script type="application/ld+json">
    {
      "@context": "https://schema.org/",
      "@type": "JobPosting",
      "title": "Machine Learning Intern",
      "url": "/jobs/ml-intern",
      "description": "<p>Build <b>PyTorch</b> models.</p>",
      "jobLocation": {"@type": "Place", "address": {"addressLocality": "Linz", "addressCountry": "AT"}}
    }
    </script>
    </head><body></body></html>
    """
    jobs = extract_json_ld_jobs(html, "https://example.com/careers", _sample_company())
    assert len(jobs) == 1
    assert jobs[0].title == "Machine Learning Intern"
    assert jobs[0].url == "https://example.com/jobs/ml-intern"
    assert jobs[0].location == "Linz, AT"
    assert "PyTorch" in jobs[0].snippet


def test_parse_personio_xml_feed() -> None:
    xml_data = """<?xml version="1.0" encoding="UTF-8"?>
    <workzag-jobs>
      <position>
        <id>98765</id>
        <name>Working Student Data Science (m/w/d)</name>
        <office>Linz</office>
        <department>AI Lab</department>
        <employmentType>Part-time</employmentType>
      </position>
    </workzag-jobs>
    """
    jobs = parse_personio_xml(xml_data, "https://demo.jobs.personio.de/xml", _sample_company())
    assert len(jobs) == 1
    assert jobs[0].url == "https://demo.jobs.personio.de/job/98765"
    assert jobs[0].location == "Linz"
    assert jobs[0].external_id == "98765"


def test_extract_html_job_links_filters_nav_noise() -> None:
    html = """
    <html><body>
      <nav><a href="/karriere">Karriere</a><a href="/impressum">Impressum</a></nav>
      <div class="job-list">
        <a href="/jobs/python-werkstudent">Python Werkstudent (m/w/d) - Linz</a>
        <a href="/jobs/python-werkstudent">Mehr erfahren</a>
      </div>
    </body></html>
    """
    jobs = extract_html_job_links(html, "https://example.com/karriere", _sample_company())
    assert len(jobs) == 1
    assert jobs[0].title == "Python Werkstudent (m/w/d) - Linz"
    assert jobs[0].url == "https://example.com/jobs/python-werkstudent"


def test_fetch_company_jobs_auto_follows_personio_hint() -> None:
    personio_xml = """<workzag-jobs><position><id>11</id><name>Junior AI Engineer</name><office>Linz</office></position></workzag-jobs>"""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "demo.at":
            return httpx.Response(
                200,
                text='<iframe src="https://demo.jobs.personio.de"></iframe>',
            )
        if request.url.host == "demo.jobs.personio.de":
            return httpx.Response(200, text=personio_xml)
        return httpx.Response(404)

    async def _run():
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            return await fetch_company_jobs(client, _sample_company(url="https://demo.at/karriere"))

    outcome = asyncio.run(_run())
    assert outcome.ok
    assert outcome.detected_kind == "personio_xml"
    assert len(outcome.jobs) == 1
    assert outcome.jobs[0].title == "Junior AI Engineer"
