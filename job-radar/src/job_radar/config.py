"""Configuration loaders for profile.yaml and companies.json."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from job_radar.models import CompanyConfig, ProfileConfig


def default_root() -> Path:
    """Return the job-radar project root directory."""
    return Path(__file__).resolve().parents[2]


def load_profile(path: Path | None = None) -> ProfileConfig:
    """Load and validate the YAML scoring & boards configuration."""
    target = path or (default_root() / "config" / "profile.yaml")
    data = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    return ProfileConfig.model_validate(data)


def load_companies(path: Path | None = None) -> list[CompanyConfig]:
    """Load and validate the JKU company registry JSON."""
    target = path or (default_root() / "data" / "companies.json")
    raw = json.loads(target.read_text(encoding="utf-8"))
    return [CompanyConfig.model_validate(item) for item in raw]
