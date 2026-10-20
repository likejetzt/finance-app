import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from linkedin_relay.config import get_settings  # noqa: E402
from linkedin_relay.db import Database  # noqa: E402


@pytest.fixture
def settings(tmp_path, monkeypatch):
    for key in ("APP_PASSWORD", "AUTO_APPROVE", "RSS_URLS", "INBOX_DIR"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("MY_LINK", "https://example.com/peno")
    monkeypatch.setenv("POST_SLOTS", "Di 08:30, Do 08:30")
    monkeypatch.setenv("LINKEDIN_ORG_ID", "12345")
    monkeypatch.setenv("LINKEDIN_CLIENT_ID", "cid")
    monkeypatch.setenv("LINKEDIN_CLIENT_SECRET", "secret")
    return get_settings()


@pytest.fixture
def db(settings):
    return Database(settings.db_path)
