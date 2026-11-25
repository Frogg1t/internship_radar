"""CLI entrypoint for running JKU Job Radar and probing career sources."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from job_radar.adapters.base import build_async_client
from job_radar.adapters.boards import fetch_board_url
from job_radar.adapters.html_links import fetch_company_jobs
from job_radar.config import default_root, load_companies, load_dotenv_if_present, load_profile
from job_radar.models import AdapterOutcome, CompanyConfig, RunSummary, ScoredJob
from job_radar.notifier import (
    chunk_messages,
    format_job_html,
    print_dry_run,
    send_telegram_messages,
)
from job_radar.scorer import score_job
from job_radar.store import SeenJobsStore


async def _gather_outcomes(
    companies: list[CompanyConfig],
    jku_urls: list[str],
    karriere_urls: list[str],
    include_boards: bool,
    concurrency: int = 8,
) -> list[AdapterOutcome]:
    semaphore = asyncio.Semaphore(concurrency)

    async with build_async_client() as client:
        async def _bounded_company(comp: CompanyConfig) -> AdapterOutcome:
            async with semaphore:
                return await fetch_company_jobs(client, comp)

        async def _bounded_board(board_id: str, board_name: str, url: str) -> AdapterOutcome:
            async with semaphore:
                return await fetch_board_url(client, board_id, board_name, url, companies)

        tasks = [_bounded_company(comp) for comp in companies if comp.enabled]
        if include_boards:
            for idx, url in enumerate(jku_urls, start=1):
                tasks.append(_bounded_board(f"jku-board-{idx}", "JKU Jobbörse", url))
            for idx, url in enumerate(karriere_urls, start=1):
                tasks.append(_bounded_board(f"karriere-at-{idx}", "karriere.at", url))

        return await asyncio.gather(*tasks)


async def run_radar(
    *,
    dry_run: bool = False,
    bootstrap: bool = False,
    tier_filter: str | None = None,
    company_id: str | None = None,
    root: Path | None = None,
) -> RunSummary:
    """Execute one full fetch -> deduplicate -> score -> notify cycle."""
    project_root = root or default_root()
    load_dotenv_if_present(project_root / ".env")
    profile = load_profile(project_root / "config" / "profile.yaml")
    all_companies = load_companies(project_root / "data" / "companies.json")

    selected = [
        c
        for c in all_companies
        if c.enabled
        and (tier_filter is None or c.tier == tier_filter)
        and (company_id is None or c.id == company_id)
    ]
    include_boards = company_id is None and tier_filter in (None, "A")

    outcomes = await _gather_outcomes(
        selected,
        profile.boards.jku_jobboerse_urls,
        profile.boards.karriere_at_queries,
        include_boards=include_boards,
    )

    store = SeenJobsStore(project_root / "data" / "seen_jobs.json")
    summary = RunSummary(sources_checked=len(outcomes))

    new_matches: list[ScoredJob] = []
    seen_this_run: set[str] = set()

    for outcome in outcomes:
        if not outcome.ok:
            summary.sources_failed += 1
            print(f"[WARN] {outcome.source_id} ({outcome.url}): {outcome.error}")
            continue

        summary.total_fetched += len(outcome.jobs)
        for raw_job in outcome.jobs:
            scored = score_job(raw_job, profile.scoring)
            if scored.fingerprint in seen_this_run or store.is_seen(scored.fingerprint):
                continue
            seen_this_run.add(scored.fingerprint)
            summary.new_listings += 1

            is_match = (not scored.is_excluded) and (scored.score >= profile.scoring.min_notify_score)
            if is_match:
                new_matches.append(scored)
            if not dry_run:
                store.mark_seen(scored.fingerprint, raw_job, notified=False)

    new_matches.sort(key=lambda item: item.score, reverse=True)
    summary.matched_listings = len(new_matches)

    to_notify = (
        new_matches[: profile.scoring.max_bootstrap_alerts] if bootstrap else new_matches
    )

    if dry_run:
        print_dry_run(to_notify, summary)
        return summary

    if to_notify:
        header = (
            "🎯 <b>JKU Job Radar — Initial Top Matches</b>"
            if bootstrap
            else f"🎯 <b>JKU Job Radar — {len(to_notify)} New Match(es)</b>"
        )
        entries = [
            format_job_html(item, high_priority_score=profile.scoring.high_priority_score)
            for item in to_notify
        ]
        messages = chunk_messages(entries, header=header)
        await send_telegram_messages(messages)
        for item in to_notify:
            store.mark_seen(item.fingerprint, item.job, notified=True)
        summary.notified_listings = len(to_notify)

    # Alert on elevated source failure rate so scraper breakage doesn't stay silent.
    if summary.sources_checked > 0 and (summary.sources_failed / summary.sources_checked) > 0.35:
        warn_msg = (
            f"⚠️ <b>JKU Job Radar Health Notice</b>\n"
            f"{summary.sources_failed}/{summary.sources_checked} career sources failed in this run."
        )
        try:
            await send_telegram_messages([warn_msg])
        except Exception as exc:
            print(f"[WARN] Failed to send health warning: {exc}")

    store.save()
    return summary


async def discover_sources(tier_filter: str | None = None, root: Path | None = None) -> None:
    """Probe enabled career URLs and print detected ATS types and job counts."""
    project_root = root or default_root()
    profile = load_profile(project_root / "config" / "profile.yaml")
    companies = [
        c
        for c in load_companies(project_root / "data" / "companies.json")
        if c.enabled and (tier_filter is None or c.tier == tier_filter)
    ]
    outcomes = await _gather_outcomes(
        companies,
        profile.boards.jku_jobboerse_urls,
        profile.boards.karriere_at_queries,
        include_boards=True,
    )
    for out in outcomes:
        status = "OK  " if out.ok else "FAIL"
        detail = f"kind={out.detected_kind:12s} jobs={len(out.jobs):3d}" if out.ok else out.error
        print(f"[{status}] {out.source_id:20s} | {detail} | {out.url}")


def cli() -> None:
    """Command-line interface for job-radar."""
    parser = argparse.ArgumentParser(prog="job-radar", description="JKU Career Fair Job Radar")
    sub = parser.add_subparsers(dest="command", required=True)

    run_cmd = sub.add_parser("run", help="Scan career portals and notify on new matches")
    run_cmd.add_argument("--dry-run", action="store_true", help="Print matches without Telegram or saving state")
    run_cmd.add_argument("--bootstrap", action="store_true", help="Seed seen_jobs and notify only top matches")
    run_cmd.add_argument("--tier", choices=["A", "B"], help="Scan only companies in a specific tier")
    run_cmd.add_argument("--company", help="Scan only a single company id")

    disc_cmd = sub.add_parser("discover", help="Probe career URLs and report detected ATS feeds")
    disc_cmd.add_argument("--tier", choices=["A", "B"], help="Probe only companies in a specific tier")

    args = parser.parse_args()
    if args.command == "run":
        summary = asyncio.run(
            run_radar(
                dry_run=args.dry_run,
                bootstrap=args.bootstrap,
                tier_filter=args.tier,
                company_id=args.company,
            )
        )
        print(f"Summary: {summary.model_dump()}")
    elif args.command == "discover":
        asyncio.run(discover_sources(tier_filter=args.tier))


if __name__ == "__main__":
    cli()
