"""Glue: import -> German draft -> schedule -> publish."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .ai import Adapter
from .config import Settings
from .db import Database
from .linkedin import LinkedInClient, LinkedInError
from .render import render_html
from .sources import RawPost, read_inbox, read_rss

log = logging.getLogger(__name__)


class Pipeline:
    def __init__(self, settings: Settings, db: Database, adapter: Adapter | None = None,
                 linkedin: LinkedInClient | None = None, renderer=render_html):
        self.s = settings
        self.db = db
        self._adapter = adapter
        self.linkedin = linkedin or LinkedInClient(settings, db)
        self.render = renderer

    @property
    def adapter(self) -> Adapter:
        if self._adapter is None:
            self._adapter = Adapter(self.s)
        return self._adapter

    @property
    def media_dir(self) -> Path:
        return self.s.data_dir / "media"

    # --- import ----------------------------------------------------------

    def store(self, posts: list[RawPost]) -> list[int]:
        ids = []
        for p in posts:
            post_id = self.db.add_post(p.source, p.ref, p.url, p.text, p.images)
            if post_id:
                ids.append(post_id)
        return ids

    def fetch(self) -> list[int]:
        posts = read_inbox(self.s.inbox_dir, self.media_dir)
        for url in self.s.rss_urls:
            try:
                posts += [p for p in read_rss(url, self.media_dir) if not self.db.has_ref(p.ref)]
            except Exception as exc:  # one broken feed must not stop the rest
                log.warning("RSS-Feed %s nicht lesbar: %s", url, exc)
        ids = self.store(posts)
        log.info("%d neue Beiträge importiert", len(ids))
        return ids

    # --- drafting --------------------------------------------------------

    def compose(self, de_text: str) -> str:
        parts = [de_text.strip()]
        footer = []
        if self.s.attribution_line:
            footer.append(self.s.attribution_line)
        if self.s.my_link:
            footer.append(self.s.link_line.format(link=self.s.my_link))
        if footer:
            parts.append("\n".join(footer))
        return "\n\n".join(parts)

    def next_free_slot(self, now: datetime | None = None) -> str | None:
        if not self.s.post_slots:
            return None
        tz = self.s.timezone
        now_local = (now or datetime.now(timezone.utc)).astimezone(tz)
        earliest = now_local + timedelta(hours=1)
        taken = self.db.taken_slots()
        for day in range(0, 120):
            date = (now_local + timedelta(days=day)).date()
            for weekday, hour, minute in self.s.post_slots:
                if date.weekday() != weekday:
                    continue
                slot = datetime(date.year, date.month, date.day, hour, minute, tzinfo=tz)
                iso = slot.astimezone(timezone.utc).isoformat(timespec="seconds")
                if slot >= earliest and iso not in taken:
                    return iso
        return None

    def translate_image(self, post: dict, index: int, feedback: str = "") -> tuple[str, str, list[str]]:
        result = self.adapter.translate_graphic(post["original_images"][index], feedback=feedback)
        out_dir = self.media_dir / post["source_ref"]
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / f"de_{index}.html").write_text(result.html, encoding="utf-8")
        png = self.render(result.html, result.width, result.height, out_dir / f"de_{index}.png")
        return str(png), result.alt_text, result.hints

    def process(self, post_id: int) -> None:
        post = self.db.get(post_id)
        try:
            text = self.adapter.adapt_text(post["original_text"], len(post["original_images"]))
            hints = [f"Text: {h}" for h in text.hints]
            images, alts = [], []
            for i in range(len(post["original_images"])):
                png, alt, img_hints = self.translate_image(post, i)
                images.append(png)
                alts.append(alt)
                hints += [f"Grafik {i + 1}: {h}" for h in img_hints]
        except Exception as exc:
            log.exception("Beitrag %s konnte nicht verarbeitet werden", post_id)
            self.db.update(post_id, status="fehler", error=str(exc))
            return
        slot = self.next_free_slot()
        self.db.update(
            post_id,
            de_text=self.compose(text.text),
            de_images=images,
            alt_texts=alts,
            hints=hints,
            scheduled_at=slot,
            error=None,
            status="geplant" if (self.s.auto_approve and slot) else "entwurf",
        )

    def regenerate_text(self, post_id: int, feedback: str = "") -> None:
        post = self.db.get(post_id)
        text = self.adapter.adapt_text(post["original_text"], len(post["original_images"]), feedback=feedback)
        hints = [h for h in post["hints"] if not h.startswith("Text:")] + [f"Text: {h}" for h in text.hints]
        self.db.update(post_id, de_text=self.compose(text.text), hints=hints)

    def regenerate_image(self, post_id: int, index: int, feedback: str = "") -> None:
        post = self.db.get(post_id)
        png, alt, img_hints = self.translate_image(post, index, feedback)
        images = list(post["de_images"])
        alts = list(post["alt_texts"])
        while len(images) <= index:
            images.append("")
            alts.append("")
        images[index], alts[index] = png, alt
        prefix = f"Grafik {index + 1}:"
        hints = [h for h in post["hints"] if not h.startswith(prefix)] + [f"{prefix} {h}" for h in img_hints]
        self.db.update(post_id, de_images=images, alt_texts=alts, hints=hints)

    def process_new(self) -> None:
        for post in self.db.list("neu"):
            self.process(post["id"])

    # --- publishing ------------------------------------------------------

    def publish(self, post_id: int) -> None:
        post = self.db.get(post_id)
        try:
            urn = self.linkedin.create_post(
                post["de_text"], [Path(p) for p in post["de_images"] if p], post["alt_texts"]
            )
        except (LinkedInError, OSError) as exc:
            log.error("Beitrag %s nicht veröffentlicht: %s", post_id, exc)
            self.db.update(post_id, status="fehler", error=str(exc))
            return
        self.db.update(post_id, status="veroeffentlicht", posted_urn=urn, error=None)
        log.info("Beitrag %s veröffentlicht: %s", post_id, urn)

    def publish_due(self, now: datetime | None = None) -> int:
        now_iso = (now or datetime.now(timezone.utc)).isoformat(timespec="seconds")
        due = self.db.due(now_iso)
        for post in due:
            self.publish(post["id"])
        return len(due)

    def daily(self) -> None:
        self.fetch()
        self.process_new()
