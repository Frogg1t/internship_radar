"""HTML fallback career link extractor and unified company fetch dispatcher."""

from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
import httpx

from job_radar.adapters.base import fetch_text
from job_radar.adapters.structured import (
    detect_ats_hints,
    extract_json_ld_jobs,
    fetch_workday_jobs,
    parse_greenhouse_json,
    parse_lever_json,
    parse_personio_xml,
    parse_smartrecruiters_json,
)
from job_radar.models import AdapterOutcome, CompanyConfig, RawJob

_JOB_URL_PATTERN = re.compile(
    r"(/job/|/jobs/|/jobdetail|/stellenangebot|/stelle/|/vacancy|/position|/offene-stellen/[^/?#]+|"
    r"onlyfy\.jobs|prescreen\.io|jobs\.personio|myworkdayjobs|smartrecruiters|softgarden|rexx|"
    r"karriere\.at/jobs/|jobboerse\.jku\.at/job)",
    re.I,
)
_NOISE_TITLE_PATTERN = re.compile(
    r"^(mehr erfahren|details|weiterlesen|read more|learn more|apply now|jetzt bewerben|"
    r"datenschutz|impressum|cookies|kontakt|login|home|zurück|back|alle jobs|all jobs|"
    r"karriere|careers|jobs|initiativbewerbung)$",
    re.I,
)


def extract_html_job_links(html: str, base_url: str, company: CompanyConfig) -> list[RawJob]:
    """Heuristically extract likely job-posting links from an HTML career page."""
    soup = BeautifulSoup(html, "lxml")
    jobs: list[RawJob] = []
    seen_urls: set[str] = set()

    for anchor in soup.find_all("a", href=True):
        href = str(anchor["href"]).strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue

        resolved = urljoin(base_url, href)
        parsed = urlparse(resolved)
        if parsed.scheme not in ("http", "https"):
            continue
        if resolved.rstrip("/") == base_url.rstrip("/"):
            continue

        title = " ".join(anchor.get_text(" ").split())
        if len(title) < 6 or len(title) > 140 or _NOISE_TITLE_PATTERN.match(title):
            continue

        parent_text = " ".join(anchor.parent.get_text(" ").split()) if anchor.parent else ""
        is_job_url = bool(_JOB_URL_PATTERN.search(resolved))
        # Also allow links inside explicit job-list elements if URL path has depth >= 2.
        path_segments = [seg for seg in parsed.path.split("/") if seg]
        if not is_job_url:
            has_job_class = any(
                "job" in " ".join(el.get("class", [])).lower()
                or "stelle" in " ".join(el.get("class", [])).lower()
                for el in [anchor, anchor.parent]
                if el is not None and hasattr(el, "get")
            )
            if not (has_job_class and len(path_segments) >= 2):
                continue

        if resolved in seen_urls:
            continue
        seen_urls.add(resolved)

        snippet = parent_text[:280] if parent_text != title else ""
        jobs.append(
            RawJob(
                company_id=company.id,
                company_name=company.name,
                title=title,
                url=resolved,
                snippet=snippet,
                source_type="html_links",
                tier=company.tier,
            )
        )
    return jobs


async def _fetch_explicit_ats(
    client: httpx.AsyncClient,
    ats_kind: str,
    endpoint: str,
    company: CompanyConfig,
) -> list[RawJob]:
    if ats_kind == "personio_xml":
        resp = await fetch_text(client, endpoint)
        return parse_personio_xml(resp.text, endpoint, company)
    if ats_kind == "greenhouse":
        resp = await fetch_text(client, endpoint)
        return parse_greenhouse_json(resp.json(), company)
    if ats_kind == "lever":
        resp = await fetch_text(client, endpoint)
        return parse_lever_json(resp.json(), company)
    if ats_kind == "smartrecruiters":
        resp = await fetch_text(client, endpoint)
        return parse_smartrecruiters_json(resp.json(), company)
    if ats_kind == "workday":
        return await fetch_workday_jobs(client, endpoint, company)
    return []


async def fetch_company_jobs(client: httpx.AsyncClient, company: CompanyConfig) -> AdapterOutcome:
    """Fetch open postings for a company using structured ATS feeds first, then HTML fallback."""
    try:
        if company.adapter in ("personio_xml", "greenhouse", "lever", "smartrecruiters", "workday"):
            jobs = await _fetch_explicit_ats(client, company.adapter, company.career_url, company)
            return AdapterOutcome(
                source_id=company.id,
                source_name=company.name,
                url=company.career_url,
                ok=True,
                detected_kind=company.adapter,
                jobs=jobs,
            )

        resp = await fetch_text(client, company.career_url)
        final_url = str(resp.url)
        html = resp.text

        json_ld_jobs = extract_json_ld_jobs(html, final_url, company)
        if json_ld_jobs:
            return AdapterOutcome(
                source_id=company.id,
                source_name=company.name,
                url=final_url,
                ok=True,
                detected_kind="json_ld",
                jobs=json_ld_jobs,
            )

        ats_kind, ats_endpoint = detect_ats_hints(html, final_url)
        if ats_kind and ats_endpoint:
            try:
                ats_jobs = await _fetch_explicit_ats(client, ats_kind, ats_endpoint, company)
                if ats_jobs:
                    return AdapterOutcome(
                        source_id=company.id,
                        source_name=company.name,
                        url=ats_endpoint,
                        ok=True,
                        detected_kind=ats_kind,
                        jobs=ats_jobs,
                    )
            except Exception:
                # Fall back to HTML link extraction if the hinted ATS endpoint blocks/fails.
                pass

        html_jobs = extract_html_job_links(html, final_url, company)
        return AdapterOutcome(
            source_id=company.id,
            source_name=company.name,
            url=final_url,
            ok=True,
            detected_kind="html_links" if html_jobs else "html_empty",
            jobs=html_jobs,
        )
    except Exception as exc:
        return AdapterOutcome(
            source_id=company.id,
            source_name=company.name,
            url=company.career_url,
            ok=False,
            detected_kind="error",
            error=f"{type(exc).__name__}: {exc}",
        )
