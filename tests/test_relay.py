import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from PIL import Image

from linkedin_relay.ai import GraphicResult, TextResult
from linkedin_relay.config import parse_slots
from linkedin_relay.linkedin import LinkedInClient, escape_commentary
from linkedin_relay.pipeline import Pipeline
from linkedin_relay.sources import parse_rss, read_inbox


class FakeAdapter:
    def __init__(self):
        self.text_calls = []

    def adapt_text(self, original, image_count, feedback=""):
        self.text_calls.append((original, image_count, feedback))
        return TextResult("Deutscher Text mit XVERWEIS #Finance", ["US GAAP prüfen"])

    def translate_graphic(self, image_path, feedback=""):
        return GraphicResult("<html><body>Hallo</body></html>", "Grafik auf Deutsch", ["Logo entfernt"], 1080, 1350)


def fake_render(html, width, height, out_path):
    out_path.write_bytes(b"png")
    return out_path


class FakeResponse:
    def __init__(self, status, payload=None, headers=None):
        self.status_code = status
        self._payload = payload or {}
        self.headers = headers or {}
        self.text = json.dumps(self._payload)

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self):
        self.calls = []

    def post(self, url, json=None, data=None, headers=None, timeout=None):
        self.calls.append(("POST", url, json))
        if "initializeUpload" in url:
            n = sum(1 for c in self.calls if "initializeUpload" in c[1])
            return FakeResponse(200, {"value": {"uploadUrl": f"https://upload/{n}", "image": f"urn:li:image:{n}"}})
        if url.endswith("/posts"):
            return FakeResponse(201, headers={"x-restli-id": "urn:li:share:999"})
        return FakeResponse(404)

    def put(self, url, data=None, headers=None, timeout=None):
        self.calls.append(("PUT", url, None))
        return FakeResponse(201)


def recent() -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat(timespec="seconds")


def make_image(path: Path):
    Image.new("RGB", (800, 1000), "white").save(path)


def test_escape_commentary_keeps_hashtags_and_escapes_reserved():
    out = escape_commentary("Formel (A1*B1) mit @Team und #Excel_Tipps, Link https://x.de/a_b")
    assert "\\(A1\\*B1\\)" in out
    assert "\\@Team" in out
    assert "{hashtag|\\#|Excel_Tipps}" in out
    assert "https://x.de/a\\_b" in out


def test_parse_slots():
    assert parse_slots("Do 08:30, Di 7:05") == [(1, 7, 5), (3, 8, 30)]


def test_next_free_slot_skips_taken(settings, db):
    p = Pipeline(settings, db, adapter=FakeAdapter(), renderer=fake_render)
    monday = datetime(2026, 10, 19, 9, 0, tzinfo=timezone.utc)  # Montag
    first = p.next_free_slot(monday)
    assert first == "2026-10-20T06:30:00+00:00"  # Di 08:30 Berlin (Sommerzeit)
    post_id = db.add_post("manuell", "a", None, "x", [])
    db.update(post_id, scheduled_at=first, status="geplant")
    assert p.next_free_slot(monday) == "2026-10-22T06:30:00+00:00"


def test_compose_adds_attribution_and_link(settings, db):
    p = Pipeline(settings, db)
    text = p.compose("Hallo")
    assert text.startswith("Hallo\n\n")
    assert "freundlicher Genehmigung" in text
    assert text.endswith("Mehr dazu: https://example.com/peno")


def test_read_inbox_folder_and_json(settings, tmp_path):
    inbox = settings.inbox_dir
    folder = inbox / "beitrag1"
    folder.mkdir(parents=True)
    (folder / "post.txt").write_text("Original text", encoding="utf-8")
    (folder / "meta.json").write_text('{"url": "https://linkedin.com/x", "id": "p1"}')
    make_image(folder / "a.png")
    (inbox / "export.json").write_text(json.dumps([{"id": "p2", "text": "Second", "images": []}]))
    posts = read_inbox(inbox, settings.data_dir / "media")
    assert {p.ref for p in posts} == {"p1", "p2"}
    p1 = next(p for p in posts if p.ref == "p1")
    assert p1.url == "https://linkedin.com/x" and len(p1.images) == 1 and Path(p1.images[0]).exists()
    assert (inbox / "_importiert" / "beitrag1").exists()
    assert read_inbox(inbox, settings.data_dir / "media") == []


def test_parse_rss(tmp_path):
    rss = b"""<?xml version="1.0"?><rss><channel>
      <item><title>Titel</title><link>https://n.example/1</link><guid>g1</guid>
      <description>&lt;p&gt;Hallo&lt;br/&gt;Welt&lt;/p&gt;</description></item>
    </channel></rss>"""
    posts = parse_rss(rss, tmp_path)
    assert posts[0].text == "Titel\n\nHallo\nWelt"
    assert posts[0].url == "https://n.example/1"


def test_process_and_publish(settings, db):
    img = settings.data_dir / "orig.png"
    img.parent.mkdir(parents=True, exist_ok=True)
    make_image(img)
    session = FakeSession()
    li = LinkedInClient(settings, db, session=session)
    db.set_kv("linkedin_token", {"access_token": "tok", "expires_at": int(time.time()) + 86400 * 30})
    p = Pipeline(settings, db, adapter=FakeAdapter(), linkedin=li, renderer=fake_render)

    post_id = db.add_post("manuell", "ref1", None, "English original", [str(img)])
    p.process(post_id)
    post = db.get(post_id)
    assert post["status"] == "entwurf"
    assert post["de_text"].startswith("Deutscher Text")
    assert post["hints"] == ["Text: US GAAP prüfen", "Grafik 1: Logo entfernt"]
    assert post["alt_texts"] == ["Grafik auf Deutsch"]
    assert Path(post["de_images"][0]).exists()
    assert post["scheduled_at"]

    db.update(post_id, status="geplant", scheduled_at=recent())
    assert p.publish_due() == 1
    post = db.get(post_id)
    assert post["status"] == "veroeffentlicht" and post["posted_urn"] == "urn:li:share:999"
    body = next(c[2] for c in session.calls if c[1].endswith("/posts"))
    assert body["author"] == "urn:li:organization:12345"
    assert body["content"] == {"media": {"id": "urn:li:image:1", "altText": "Grafik auf Deutsch"}}
    assert "{hashtag|\\#|Finance}" in body["commentary"]


def test_publish_without_token_marks_error(settings, db):
    p = Pipeline(settings, db, adapter=FakeAdapter(), renderer=fake_render)
    post_id = db.add_post("manuell", "ref2", None, "x", [])
    db.update(post_id, de_text="Text", status="geplant", scheduled_at=recent())
    p.publish_due()
    post = db.get(post_id)
    assert post["status"] == "fehler" and "nicht verbunden" in post["error"]


def test_process_failure_sets_error(settings, db):
    class Broken(FakeAdapter):
        def adapt_text(self, *a, **k):
            raise RuntimeError("API down")

    p = Pipeline(settings, db, adapter=Broken(), renderer=fake_render)
    post_id = db.add_post("manuell", "ref3", None, "x", [])
    p.process(post_id)
    assert db.get(post_id)["status"] == "fehler"


def test_web_flow(settings, db):
    from linkedin_relay.web import create_app

    app = create_app(settings)
    client = app.test_client()
    post_id = db.add_post("manuell", "ref4", None, "Original", [])
    db.update(post_id, de_text="Deutsch", status="entwurf")
    assert client.get("/").status_code == 200
    assert "Deutsch".encode() in client.get(f"/beitrag/{post_id}").data
    resp = client.post(f"/beitrag/{post_id}/aktion",
                       data={"aktion": "planen", "de_text": "Neu", "scheduled_at": "2026-11-03T08:30"})
    assert resp.status_code == 302
    post = db.get(post_id)
    assert post["status"] == "geplant" and post["de_text"] == "Neu"
    assert post["scheduled_at"] == "2026-11-03T07:30:00+00:00"  # Winterzeit


def test_web_password(settings, monkeypatch):
    from linkedin_relay.config import get_settings
    from linkedin_relay.web import create_app

    monkeypatch.setenv("APP_PASSWORD", "geheim")
    client = create_app(get_settings()).test_client()
    assert client.get("/").status_code == 401
    import base64
    auth = base64.b64encode(b"elena:geheim").decode()
    assert client.get("/", headers={"Authorization": f"Basic {auth}"}).status_code == 200


def test_missed_slot_is_rescheduled_not_posted(settings, db):
    session = FakeSession()
    li = LinkedInClient(settings, db, session=session)
    db.set_kv("linkedin_token", {"access_token": "tok", "expires_at": int(time.time()) + 86400})
    p = Pipeline(settings, db, adapter=FakeAdapter(), linkedin=li, renderer=fake_render)
    now = datetime(2026, 10, 20, 10, 0, tzinfo=timezone.utc)  # Di 12:00 Berlin
    old = db.add_post("manuell", "old", None, "x", [])
    db.update(old, de_text="Alt", status="geplant", scheduled_at="2026-10-19T06:30:00+00:00")
    fresh = db.add_post("manuell", "fresh", None, "y", [])
    db.update(fresh, de_text="Neu", status="geplant", scheduled_at="2026-10-20T09:45:00+00:00")

    assert p.publish_due(now) == 1
    assert db.get(fresh)["status"] == "veroeffentlicht"
    moved = db.get(old)
    assert moved["status"] == "geplant"
    assert moved["scheduled_at"] == "2026-10-22T06:30:00+00:00"
    assert "verpasst" in moved["hints"][-1]
    assert sum(1 for c in session.calls if c[1].endswith("/posts")) == 1


def test_empty_env_value_uses_default(settings, monkeypatch):
    from linkedin_relay.config import get_settings

    monkeypatch.setenv("INBOX_DIR", "")
    assert get_settings().inbox_dir == settings.data_dir / "inbox"
