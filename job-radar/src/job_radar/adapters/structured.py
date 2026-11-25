"""Parsers for structured job feeds: Schema.org JSON-LD, Personio XML, Greenhouse, Lever, Workday."""

from __future__ import annotations

import json
import re
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree as ET

from bs4 import BeautifulSoup
import httpx

from job_radar.models import CompanyConfig, RawJob


def _iter_json_ld_objects(payload: object) -> list[dict]:
    """Flatten JSON-LD objects including arrays and @graph containers."""
    items: list[dict] = []
    if isinstance(payload, list):
        for elem in payload:
            items.extend(_iter_json_ld_objects(elem))
    elif isinstance(payload, dict):
        if "@graph" in payload and isinstance(payload["@graph"], list):
            items.extend(_iter_json_ld_objects(payload["@graph"]))
        items.append(payload)
    return items


def _is_job_posting_type(raw_type: object) -> bool:
    if isinstance(raw_type, str):
        return raw_type.endswith("JobPosting")
    if isinstance(raw_type, list):
        return any(isinstance(t, str) and t.endswith("JobPosting") for t in raw_type)
    return False


def _extract_location(job_loc: object) -> str:
    if isinstance(job_loc, list) and job_loc:
        return _extract_location(job_loc[0])
    if isinstance(job_loc, dict):
        addr = job_loc.get("address")
        if isinstance(addr, dict):
            parts = [
                str(addr.get("addressLocality", "")).strip(),
                str(addr.get("addressRegion", "")).strip(),
                str(addr.get("addressCountry", "")).strip(),
            ]
            return ", ".join(p for p in parts if p)
        return str(job_loc.get("name", "")).strip()
    if isinstance(job_loc, str):
        return job_loc.strip()
    return ""


def _strip_html(text: str) -> str:
    if "<" not in text:
        return " ".join(text.split())
    return " ".join(BeautifulSoup(text, "lxml").get_text(" ").split())


def extract_json_ld_jobs(html: str, base_url: str, company: CompanyConfig) -> list[RawJob]:
    """Extract Schema.org JobPosting entries embedded in HTML <script type='application/ld+json'>."""
    soup = BeautifulSoup(html, "lxml")
    jobs: list[RawJob] = []

    for script in soup.find_all("script", attrs={"type": re.compile(r"application/ld\+json", re.I)}):
        raw_text = script.string or script.get_text()
        if not raw_text or not raw_text.strip():
            continue
        try:
            parsed = json.loads(raw_text)
        except json.JSONDecodeError:
            continue

        for obj in _iter_json_ld_objects(parsed):
            if not _is_job_posting_type(obj.get("@type")):
                continue
            title = str(obj.get("title") or obj.get("name") or "").strip()
            if not title:
                continue
            raw_url = str(obj.get("url") or obj.get("sameAs") or base_url).strip()
            resolved_url = urljoin(base_url, raw_url)
            identifier = obj.get("identifier")
            ext_id = None
            if isinstance(identifier, dict):
                ext_id = str(identifier.get("value") or "").strip() or None
            elif isinstance(identifier, (str, int)):
                ext_id = str(identifier).strip() or None

            description = _strip_html(str(obj.get("description") or ""))[:400]
            location = _extract_location(obj.get("jobLocation"))
            jobs.append(
                RawJob(
                    company_id=company.id,
                    company_name=company.name,
                    title=title,
                    url=resolved_url,
                    location=location,
                    snippet=description,
                    source_type="json_ld",
                    tier=company.tier,
                    external_id=ext_id,
                )
            )
    return jobs


def parse_personio_xml(xml_text: str, base_url: str, company: CompanyConfig) -> list[RawJob]:
    """Parse Personio public XML job feed (<workzag-jobs><position>...)."""
    root = ET.fromstring(xml_text)
    jobs: list[RawJob] = []
    parsed_base = urlparse(base_url)
    portal_root = f"{parsed_base.scheme}://{parsed_base.netloc}"

    for pos in root.findall(".//position"):
        title = (pos.findtext("name") or "").strip()
        pos_id = (pos.findtext("id") or "").strip()
        if not title:
            continue
        office = (pos.findtext("office") or "").strip()
        employment = (pos.findtext("employmentType") or "").strip()
        dept = (pos.findtext("department") or "").strip()
        job_url = f"{portal_root}/job/{pos_id}" if pos_id else base_url
        snippet = " | ".join(part for part in (dept, employment, office) if part)
        jobs.append(
            RawJob(
                company_id=company.id,
                company_name=company.name,
                title=title,
                url=job_url,
                location=office,
                snippet=snippet,
                source_type="personio_xml",
                tier=company.tier,
                external_id=pos_id or None,
            )
        )
    return jobs


def parse_greenhouse_json(data: dict, company: CompanyConfig) -> list[RawJob]:
    """Parse Greenhouse Job Board API JSON."""
    jobs: list[RawJob] = []
    for item in data.get("jobs", []):
        title = str(item.get("title") or "").strip()
        url = str(item.get("absolute_url") or "").strip()
        if not title or not url:
            continue
        loc = item.get("location") or {}
        location = str(loc.get("name") or "").strip() if isinstance(loc, dict) else ""
        jobs.append(
            RawJob(
                company_id=company.id,
                company_name=company.name,
                title=title,
                url=url,
                location=location,
                source_type="greenhouse",
                tier=company.tier,
                external_id=str(item.get("id") or "") or None,
            )
        )
    return jobs


def parse_lever_json(data: list, company: CompanyConfig) -> list[RawJob]:
    """Parse Lever public postings JSON."""
    jobs: list[RawJob] = []
    for item in data:
        title = str(item.get("text") or "").strip()
        url = str(item.get("hostedUrl") or "").strip()
        if not title or not url:
            continue
        cats = item.get("categories") or {}
        location = str(cats.get("location") or "").strip() if isinstance(cats, dict) else ""
        commitment = str(cats.get("commitment") or "").strip() if isinstance(cats, dict) else ""
        jobs.append(
            RawJob(
                company_id=company.id,
                company_name=company.name,
                title=title,
                url=url,
                location=location,
                snippet=commitment,
                source_type="lever",
                tier=company.tier,
                external_id=str(item.get("id") or "") or None,
            )
        )
    return jobs


def parse_smartrecruiters_json(data: dict, company: CompanyConfig) -> list[RawJob]:
    """Parse SmartRecruiters public postings API JSON."""
    jobs: list[RawJob] = []
    slug = company.ats_slug or ""
    for item in data.get("content", []):
        title = str(item.get("name") or "").strip()
        post_id = str(item.get("id") or "").strip()
        if not title or not post_id:
            continue
        loc = item.get("location") or {}
        city = str(loc.get("city") or "").strip()
        country = str(loc.get("country") or "").strip()
        location = ", ".join(p for p in (city, country) if p)
        ref = str(item.get("ref") or "")
        url = (
            f"https://jobs.smartrecruiters.com/{slug}/{post_id}"
            if slug
            else (ref or company.career_url)
        )
        jobs.append(
            RawJob(
                company_id=company.id,
                company_name=company.name,
                title=title,
                url=url,
                location=location,
                source_type="smartrecruiters",
                tier=company.tier,
                external_id=post_id,
            )
        )
    return jobs


async def fetch_workday_jobs(
    client: httpx.AsyncClient,
    workday_url: str,
    company: CompanyConfig,
    limit: int = 40,
) -> list[RawJob]:
    """Query a Workday CXS endpoint derived from a myworkdayjobs.com career URL."""
    parsed = urlparse(workday_url)
    host = parsed.netloc
    tenant = host.split(".")[0]
    path_parts = [p for p in parsed.path.split("/") if p and not re.match(r"^[a-z]{2}-[A-Z]{2}$", p)]
    site = path_parts[0] if path_parts else tenant
    api_url = f"https://{host}/wday/cxs/{tenant}/{site}/jobs"

    resp = await client.post(
        api_url,
        json={"appliedFacets": {}, "limit": limit, "offset": 0, "searchText": ""},
        headers={"Accept": "application/json", "Content-Type": "application/json"},
    )
    resp.raise_for_status()
    payload = resp.json()

    jobs: list[RawJob] = []
    for item in payload.get("jobPostings", []):
        title = str(item.get("title") or "").strip()
        ext_path = str(item.get("externalPath") or "").strip()
        if not title or not ext_path:
            continue
        location = str(item.get("locationsText") or "").strip()
        jobs.append(
            RawJob(
                company_id=company.id,
                company_name=company.name,
                title=title,
                url=urljoin(f"https://{host}/{site}/", ext_path.lstrip("/")),
                location=location,
                source_type="workday",
                tier=company.tier,
                external_id=ext_path,
            )
        )
    return jobs


def detect_ats_hints(html: str, page_url: str) -> tuple[str | None, str | None]:
    """Detect embedded ATS provider links in a career landing page."""
    personio_match = re.search(r"https?://([a-z0-9-]+)\.jobs\.personio\.(?:de|com)", html, re.I)
    if personio_match:
        return "personio_xml", f"{personio_match.group(0)}/xml"

    greenhouse_match = re.search(
        r"https?://boards(?:-api)?\.greenhouse\.io/(?:v1/boards/)?([a-z0-9_-]+)", html, re.I
    )
    if greenhouse_match:
        slug = greenhouse_match.group(1)
        return "greenhouse", f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"

    lever_match = re.search(r"https?://jobs\.lever\.co/([a-z0-9_-]+)", html, re.I)
    if lever_match:
        slug = lever_match.group(1)
        return "lever", f"https://api.lever.co/v0/postings/{slug}?mode=json"

    workday_match = re.search(r"https?://[a-z0-9-]+\.wd\d+\.myworkdayjobs\.com/[^\s\"'<>]+", html, re.I)
    if workday_match:
        return "workday", workday_match.group(0)

    if "myworkdayjobs.com" in page_url:
        return "workday", page_url

    return None, None
