"""Configuration loaders for profile.yaml and companies.json."""

from __future__ import annotations

import json
import os
from pathlib import Path

import yaml

from job_radar.models import CompanyConfig, ProfileConfig


def default_root() -> Path:
    """Return the job-radar project root directory."""
    return Path(__file__).resolve().parents[2]


def load_dotenv_if_present(path: Path | None = None) -> None:
    """Load KEY=VALUE pairs from an optional .env file without overriding existing env vars."""
    target = path or (default_root() / ".env")
    if not target.is_file():
        return
    for raw_line in target.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"'")
        if key and key not in os.environ:
            os.environ[key] = value


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
