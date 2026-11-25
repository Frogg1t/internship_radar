"""Telegram Bot API and console dry-run notifiers."""

from __future__ import annotations

import html
import os

import httpx

from job_radar.models import RunSummary, ScoredJob

_MAX_TELEGRAM_CHARS = 3800


def format_job_html(item: ScoredJob, high_priority_score: int = 6) -> str:
    """Format a single scored job as a safe Telegram HTML snippet."""
    job = item.job
    badge = "🔥" if item.score >= high_priority_score else "📌"
    tier_tag = f"Tier {job.tier}" if job.tier in ("A", "B") else "Board"

    tags: list[str] = [tier_tag]
    if item.role_matches:
        tags.append("/".join(item.role_matches[:2]))
    if item.domain_matches:
        tags.append("/".join(item.domain_matches[:3]))
    if item.location_matches:
        tags.append(item.location_matches[0])
    elif job.location:
        tags.append(job.location[:40])

    safe_company = html.escape(job.company_name)
    safe_title = html.escape(job.title)
    safe_url = html.escape(job.url, quote=True)
    safe_tags = html.escape(" · ".join(tags))

    return (
        f"{badge} <b>{safe_company}</b> (score {item.score})\n"
        f"<a href=\"{safe_url}\">{safe_title}</a>\n"
        f"<i>{safe_tags}</i>"
    )


def chunk_messages(entries: list[str], header: str) -> list[str]:
    """Pack formatted job blocks into Telegram-safe messages under 3800 chars."""
    if not entries:
        return []

    messages: list[str] = []
    current = header
    for entry in entries:
        candidate = f"{current}\n\n{entry}"
        if len(candidate) > _MAX_TELEGRAM_CHARS and current != header:
            messages.append(current)
            current = f"{header} (cont.)\n\n{entry}"
        else:
            current = candidate
    if current:
        messages.append(current)
    return messages


async def send_telegram_messages(
    messages: list[str],
    bot_token: str | None = None,
    chat_id: str | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> int:
    """Send HTML-formatted messages via Telegram Bot API. Returns count sent."""
    token = (bot_token or os.environ.get("TELEGRAM_BOT_TOKEN", "")).strip()
    target_chat = (chat_id or os.environ.get("TELEGRAM_CHAT_ID", "")).strip()
    if not token or not target_chat:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set to send notifications."
        )

    endpoint = f"https://api.telegram.org/bot{token}/sendMessage"
    sent = 0
    async with httpx.AsyncClient(timeout=20.0, transport=transport) as client:
        for text in messages:
            resp = await client.post(
                endpoint,
                json={
                    "chat_id": target_chat,
                    "text": text,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
            )
            resp.raise_for_status()
            sent += 1
    return sent


def print_dry_run(matches: list[ScoredJob], summary: RunSummary) -> None:
    """Render matched opportunities and run stats cleanly to stdout."""
    print(
        f"\n=== JKU Job Radar Dry Run ===\n"
        f"Sources checked: {summary.sources_checked} (failed: {summary.sources_failed})\n"
        f"Total fetched:   {summary.total_fetched}\n"
        f"New listings:    {summary.new_listings}\n"
        f"Matched alerts:  {len(matches)}\n"
    )
    for idx, item in enumerate(matches, start=1):
        tags = item.role_matches[:2] + item.domain_matches[:3] + item.location_matches[:1]
        print(
            f"{idx:2d}. [{item.score:2d}] {item.job.company_name} — {item.job.title}\n"
            f"    Tags: {', '.join(tags) or 'general'} | Source: {item.job.source_type}\n"
            f"    URL:  {item.job.url}"
        )
