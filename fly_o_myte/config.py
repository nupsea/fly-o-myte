"""
Configuration management for Fly-O-Myte.

Two-layer config:
  1. ~/.fly-o-myte/config.yaml  — family profile, preferences, API keys
  2. Environment variables / .env file — override any setting

Use get_settings() and load_family_profile() everywhere.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# ─── Default paths ────────────────────────────────────────────────────────────

APP_DIR = Path(os.environ.get("FLY_O_MYTE_HOME", "~/.fly-o-myte")).expanduser()
DEFAULT_CONFIG_PATH = APP_DIR / "config.yaml"
DEFAULT_DB_PATH = APP_DIR / "fly-o-myte.db"
DEFAULT_ANALYTICS_DIR = APP_DIR / "analytics"
DEFAULT_LOG_PATH = APP_DIR / "fly-o-myte.log"


# ─── Family profile dataclasses ───────────────────────────────────────────────


@dataclass
class Child:
    name: str
    dob: date  # age is computed at travel date, not at search time


@dataclass
class DepartureWindow:
    earliest_hour: int = 8  # earliest acceptable departure (families prefer 8am+)
    latest_hour: int = 18  # latest acceptable departure


@dataclass
class FamilyProfile:
    adults: int = 2
    children: list[Child] = field(default_factory=list)
    origin_airport: str = "BNE"
    state: str = "QLD"
    school_type: Literal["state", "independent", "catholic"] = "state"
    bags_per_person: int = 1
    max_stops: int = 1
    preferred_departure_window: DepartureWindow = field(default_factory=DepartureWindow)
    default_trip_length: int = 7
    blocked_airlines: list[str] = field(default_factory=list)
    budget_threshold_aud: float | None = None

    @property
    def total_pax(self) -> int:
        return self.adults + len(self.children)

    def child_ages_at(self, travel_date: date) -> list[int]:
        """Return each child's age in full years at the given travel date."""
        ages = []
        for child in self.children:
            age = (
                travel_date.year
                - child.dob.year
                - (
                    (travel_date.month, travel_date.day)
                    < (child.dob.month, child.dob.day)
                )
            )
            ages.append(age)
        return ages

    def lap_infant_count_at(self, travel_date: date) -> int:
        """Number of children who will be lap infants (age < 2) at travel date."""
        return sum(1 for age in self.child_ages_at(travel_date) if age < 2)

    def seated_child_count_at(self, travel_date: date) -> int:
        """Number of children who need a seat (age 2-11) at travel date."""
        return sum(1 for age in self.child_ages_at(travel_date) if 2 <= age < 12)


# ─── Settings (env vars + .env file) ─────────────────────────────────────────


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Flight data
    serpapi_api_key: str = ""  # primary: Google Flights via SerpAPI
    tequila_api_key: str = ""  # legacy: Kiwi.com Tequila (sign-up broken as of 2026)
    amadeus_client_id: str = ""
    amadeus_client_secret: str = ""
    amadeus_hostname: str = "test"

    # LLM
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"

    # Observability
    logfire_token: str = ""

    # Notifications
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_pass: str = ""
    default_alert_email: str = ""

    # SerpAPI response cache TTL in hours (set to 0 to disable, 24 for light testing)
    serpapi_cache_ttl_hours: int = 6

    # Storage (override only if needed)
    fly_o_myte_db_path: str = str(DEFAULT_DB_PATH)
    fly_o_myte_analytics_dir: str = str(DEFAULT_ANALYTICS_DIR)
    fly_o_myte_config_path: str = str(DEFAULT_CONFIG_PATH)
    fly_o_myte_log_path: str = str(DEFAULT_LOG_PATH)

    @field_validator(
        "serpapi_api_key", "tequila_api_key", "anthropic_api_key", "openai_api_key", mode="before"
    )
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        return v.strip() if v else ""

    @property
    def db_path(self) -> Path:
        return Path(self.fly_o_myte_db_path).expanduser()

    @property
    def analytics_dir(self) -> Path:
        return Path(self.fly_o_myte_analytics_dir).expanduser()

    @property
    def config_path(self) -> Path:
        return Path(self.fly_o_myte_config_path).expanduser()

    @property
    def log_path(self) -> Path:
        return Path(self.fly_o_myte_log_path).expanduser()

    def llm_provider(self) -> Literal["openai", "claude", "ollama", "none"]:
        if self.openai_api_key:
            return "openai"
        if self.anthropic_api_key:
            return "claude"
        if self.ollama_base_url:
            return "ollama"
        return "none"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings singleton — call once at app startup."""
    return Settings()


def load_family_profile(config_path: Path | None = None) -> FamilyProfile:
    """
    Load family profile from ~/.fly-o-myte/config.yaml.
    Returns defaults if the file does not exist (first run, before `fom setup`).
    """
    path = config_path or get_settings().config_path

    if not path.exists():
        return FamilyProfile()

    with path.open() as f:
        raw = yaml.safe_load(f)

    if not raw or "family" not in raw:
        return FamilyProfile()

    fam = raw["family"]
    children = [
        Child(name=c["name"], dob=date.fromisoformat(c["dob"]))
        for c in fam.get("children", [])
    ]
    window_raw = fam.get("preferred_departure_window", {})
    window = DepartureWindow(
        earliest_hour=window_raw.get("earliest_hour", 8),
        latest_hour=window_raw.get("latest_hour", 18),
    )

    return FamilyProfile(
        adults=fam.get("adults", 2),
        children=children,
        origin_airport=fam.get("origin_airport", "BNE"),
        state=fam.get("state", "QLD"),
        school_type=fam.get("school_type", "state"),
        bags_per_person=fam.get("bags_per_person", 1),
        max_stops=fam.get("max_stops", 1),
        preferred_departure_window=window,
        default_trip_length=fam.get("default_trip_length", 7),
        blocked_airlines=fam.get("blocked_airlines", []),
        budget_threshold_aud=fam.get("budget_threshold_aud"),
    )
