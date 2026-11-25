"""Unit tests for Telegram HTML formatting, message chunking, and mocked delivery."""

import asyncio
import json

import httpx

from job_radar.models import RawJob, ScoredJob
from job_radar.notifier import chunk_messages, format_job_html, send_telegram_messages


def _make_scored(idx: int) -> ScoredJob:
    return ScoredJob(
        fingerprint=f"fp-{idx}",
        score=7,
        role_matches=["internship"],
        domain_matches=["ai", "python"],
        location_matches=["linz"],
        job=RawJob(
            company_id="mindbreeze",
            company_name="Mindbreeze & Co <Test>",
            title=f"AI Intern #{idx} — NLP & LLMs",
            url=f"https://example.com/jobs/{idx}?a=1&b=2",
            tier="A",
        ),
    )


def test_format_escapes_html_and_chunks_safely() -> None:
    entries = [format_job_html(_make_scored(i)) for i in range(40)]
    assert "&amp;" in entries[0]
    assert "&lt;Test&gt;" in entries[0]
    chunks = chunk_messages(entries, header="<b>Header</b>")
    assert len(chunks) >= 2
    assert all(len(c) <= 3800 for c in chunks)


def test_send_telegram_messages_posts_expected_payload() -> None:
    captured: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(json.loads(request.content.decode("utf-8")))
        return httpx.Response(200, json={"ok": True})

    async def _run() -> int:
        return await send_telegram_messages(
            ["Hello <b>JKU</b>"],
            bot_token="123:ABC",
            chat_id="999",
            transport=httpx.MockTransport(handler),
        )

    count = asyncio.run(_run())
    assert count == 1
    assert captured[0]["chat_id"] == "999"
    assert captured[0]["parse_mode"] == "HTML"
