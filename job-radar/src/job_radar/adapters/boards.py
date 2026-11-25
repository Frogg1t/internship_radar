"""Adapters for JKU Jobbörse and karriere.at regional job boards."""

from __future__ import annotations

import httpx

from job_radar.adapters.base import fetch_text
from job_radar.adapters.html_links import extract_html_job_links
from job_radar.adapters.structured import extract_json_ld_jobs
from job_radar.models import AdapterOutcome, CompanyConfig, RawJob


def _match_target_company(text: str, companies: list[CompanyConfig]) -> CompanyConfig | None:
    lowered = text.lower()
    for comp in companies:
        for alias in [comp.name, *comp.aliases]:
            alias_clean = alias.strip().lower()
            if len(alias_clean) >= 3 and alias_clean in lowered:
                return comp
    return None


async def fetch_board_url(
    client: httpx.AsyncClient,
    board_id: str,
    board_name: str,
    url: str,
    target_companies: list[CompanyConfig],
) -> AdapterOutcome:
    """Fetch listings from a central Austrian/JKU job board and attribute known companies."""
    synthetic = CompanyConfig(
        id=board_id,
        name=board_name,
        tier="B",
        enabled=True,
        adapter=board_id,
        career_url=url,
    )
    try:
        resp = await fetch_text(client, url)
        final_url = str(resp.url)
        html = resp.text

        jobs = extract_json_ld_jobs(html, final_url, synthetic)
        kind = "json_ld"
        if not jobs:
            jobs = extract_html_job_links(html, final_url, synthetic)
            kind = "html_links" if jobs else "html_empty"

        enriched: list[RawJob] = []
        for job in jobs:
            haystack = f"{job.title} {job.snippet}"
            matched = _match_target_company(haystack, target_companies)
            if matched:
                enriched.append(
                    job.model_copy(
                        update={
                            "company_id": matched.id,
                            "company_name": f"{matched.name} (via {board_name})",
                            "tier": matched.tier,
                            "source_type": board_id,
                        }
                    )
                )
            else:
                enriched.append(job.model_copy(update={"source_type": board_id}))

        return AdapterOutcome(
            source_id=board_id,
            source_name=board_name,
            url=final_url,
            ok=True,
            detected_kind=kind,
            jobs=enriched,
        )
    except Exception as exc:
        return AdapterOutcome(
            source_id=board_id,
            source_name=board_name,
            url=url,
            ok=False,
            detected_kind="error",
            error=f"{type(exc).__name__}: {exc}",
        )
