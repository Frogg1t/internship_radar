"""Persistent seen-job store with URL canonicalization and SHA-256 deduplication."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from job_radar.models import RawJob

_TRACKING_PARAM_PREFIXES = ("utm_", "fbclid", "gclid", "mc_cid", "mc_eid", "ref", "source")


def canonicalize_url(url: str) -> str:
    """Normalize a job URL by stripping tracking query params and trailing slashes."""
    parsed = urlparse(url.strip())
    scheme = (parsed.scheme or "https").lower()
    netloc = parsed.netloc.lower()
    path = parsed.path.rstrip("/") or "/"

    kept_params = [
        (k, v)
        for k, v in parse_qsl(parsed.query, keep_blank_values=False)
        if not any(k.lower().startswith(prefix) for prefix in _TRACKING_PARAM_PREFIXES)
    ]
    kept_params.sort()
    query = urlencode(kept_params)
    return urlunparse((scheme, netloc, path, "", query, ""))


def compute_fingerprint(job: RawJob) -> str:
    """Create a stable SHA-256 identifier for a job posting."""
    identity = job.external_id.strip() if job.external_id else canonicalize_url(job.url)
    payload = f"{job.company_id.lower()}::{identity}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:24]


class SeenJobsStore:
    """JSON-backed deduplication store designed for clean Git commits."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._data: dict = {"version": 1, "last_run": None, "jobs": {}}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        loaded = json.loads(self.path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict) and isinstance(loaded.get("jobs"), dict):
            self._data = loaded

    def is_seen(self, fingerprint: str) -> bool:
        """Return True if a job fingerprint was recorded in a prior run."""
        return fingerprint in self._data["jobs"]

    def mark_seen(self, fingerprint: str, job: RawJob, notified: bool) -> None:
        """Record a job fingerprint with lightweight metadata."""
        now_iso = datetime.now(timezone.utc).isoformat()
        existing = self._data["jobs"].get(fingerprint)
        if existing:
            existing["last_seen"] = now_iso
            existing["notified"] = existing.get("notified", False) or notified
            return

        self._data["jobs"][fingerprint] = {
            "company_id": job.company_id,
            "title": job.title[:160],
            "url": canonicalize_url(job.url),
            "first_seen": now_iso,
            "last_seen": now_iso,
            "notified": notified,
        }

    def save(self) -> None:
        """Persist state deterministically with sorted keys."""
        self._data["last_run"] = datetime.now(timezone.utc).isoformat()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        serialized = json.dumps(self._data, indent=2, sort_keys=True, ensure_ascii=False)
        self.path.write_text(f"{serialized}\n", encoding="utf-8")

    @property
    def count(self) -> int:
        return len(self._data["jobs"])
