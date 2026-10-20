"""Settings, read from environment variables (optionally from a .env file)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent

WEEKDAYS = {"mo": 0, "di": 1, "mi": 2, "do": 3, "fr": 4, "sa": 5, "so": 6}


def load_dotenv(path: Path) -> None:
    """Minimal .env loader: KEY=VALUE lines, existing env vars win."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key.strip(), value)


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "ja", "yes", "on"}


def parse_slots(raw: str) -> list[tuple[int, int, int]]:
    """'Di 08:30, Do 08:30' -> [(1, 8, 30), (3, 8, 30)]"""
    slots = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        day, time = part.split()
        hour, minute = time.split(":")
        slots.append((WEEKDAYS[day.lower()[:2]], int(hour), int(minute)))
    return sorted(slots)


@dataclass
class Settings:
    data_dir: Path
    db_path: Path
    inbox_dir: Path
    style_guide_path: Path
    timezone: ZoneInfo
    my_link: str
    link_line: str
    attribution_line: str
    source_author: str
    post_slots: list[tuple[int, int, int]]
    auto_approve: bool
    fetch_time: str
    rss_urls: list[str]
    claude_model: str
    brand_primary: str
    brand_accent: str
    brand_font: str
    linkedin_client_id: str
    linkedin_client_secret: str
    linkedin_redirect_uri: str
    linkedin_scope: str
    linkedin_org_id: str
    linkedin_version: str
    app_password: str
    secret_key: str
    extra: dict = field(default_factory=dict)

    @property
    def org_urn(self) -> str:
        return f"urn:li:organization:{self.linkedin_org_id}"

    @property
    def linkedin_configured(self) -> bool:
        return bool(self.linkedin_client_id and self.linkedin_client_secret and self.linkedin_org_id)


def get_settings() -> Settings:
    load_dotenv(ROOT / ".env")
    env = os.environ.get
    data_dir = Path(env("DATA_DIR", str(ROOT / "data")))
    return Settings(
        data_dir=data_dir,
        db_path=data_dir / "relay.db",
        inbox_dir=Path(env("INBOX_DIR", str(data_dir / "inbox"))),
        style_guide_path=Path(env("STYLE_GUIDE", str(ROOT / "config" / "stil.md"))),
        timezone=ZoneInfo(env("TIMEZONE", "Europe/Berlin")),
        my_link=env("MY_LINK", ""),
        link_line=env("LINK_LINE", "Mehr dazu: {link}"),
        attribution_line=env(
            "ATTRIBUTION_LINE",
            "Original von Nicolas Boucher, deutsche Fassung mit freundlicher Genehmigung.",
        ),
        source_author=env("SOURCE_AUTHOR", "Nicolas Boucher"),
        post_slots=parse_slots(env("POST_SLOTS", "Di 08:30, Do 08:30")),
        auto_approve=_bool("AUTO_APPROVE", False),
        fetch_time=env("FETCH_TIME", "06:00"),
        rss_urls=[u.strip() for u in env("RSS_URLS", "").split(",") if u.strip()],
        claude_model=env("CLAUDE_MODEL", "claude-opus-5-5"),
        brand_primary=env("BRAND_PRIMARY", "#0B2545"),
        brand_accent=env("BRAND_ACCENT", "#13A89E"),
        brand_font=env("BRAND_FONT", "'Inter', 'Helvetica Neue', Arial, sans-serif"),
        linkedin_client_id=env("LINKEDIN_CLIENT_ID", ""),
        linkedin_client_secret=env("LINKEDIN_CLIENT_SECRET", ""),
        linkedin_redirect_uri=env("LINKEDIN_REDIRECT_URI", "http://localhost:5000/linkedin/callback"),
        linkedin_scope=env("LINKEDIN_SCOPE", "w_organization_social"),
        linkedin_org_id=env("LINKEDIN_ORG_ID", ""),
        linkedin_version=env("LINKEDIN_VERSION", "202609"),
        app_password=env("APP_PASSWORD", ""),
        secret_key=env("SECRET_KEY", "bitte-in-env-setzen"),
    )
