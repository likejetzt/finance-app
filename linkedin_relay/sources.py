"""Where original posts come from.

There is no official LinkedIn API to read another member's posts, and
automated scraping breaks the LinkedIn User Agreement. The sources here
therefore work with material that is handed over legitimately:

* Inbox folder: one sub-folder per post (text file + images), e.g. a
  shared Google Drive / Dropbox / OneDrive folder synced to this machine.
* JSON export: a ``*.json`` file in the inbox with a list of posts.
* RSS feeds: e.g. a newsletter feed of the original author.
* Manual import through the web UI (see web.py).
"""

from __future__ import annotations

import hashlib
import html
import json
import re
import shutil
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

import requests

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
TEXT_NAMES = ("post.txt", "post.md", "text.txt", "text.md")


@dataclass
class RawPost:
    source: str
    ref: str
    text: str
    url: str | None = None
    images: list[str] = field(default_factory=list)  # local paths


def _ref(*parts: str) -> str:
    return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:16]


def download_image(url: str, target_dir: Path, index: int) -> str:
    target_dir.mkdir(parents=True, exist_ok=True)
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    ext = Path(urlparse(url).path).suffix.lower()
    if ext not in IMAGE_EXT:
        ctype = resp.headers.get("content-type", "")
        ext = ".png" if "png" in ctype else ".webp" if "webp" in ctype else ".jpg"
    path = target_dir / f"original_{index}{ext}"
    path.write_bytes(resp.content)
    return str(path)


def copy_images(paths: list[Path], target_dir: Path) -> list[str]:
    target_dir.mkdir(parents=True, exist_ok=True)
    result = []
    for i, src in enumerate(paths):
        dst = target_dir / f"original_{i}{src.suffix.lower()}"
        shutil.copy2(src, dst)
        result.append(str(dst))
    return result


def read_inbox(inbox: Path, media_dir: Path) -> list[RawPost]:
    """Collect posts from the inbox and move processed entries to _importiert/."""
    if not inbox.exists():
        inbox.mkdir(parents=True, exist_ok=True)
        return []
    done_dir = inbox / "_importiert"
    posts: list[RawPost] = []

    for entry in sorted(inbox.iterdir()):
        if entry.name.startswith((".", "_")):
            continue
        if entry.is_dir():
            post = _read_post_folder(entry, media_dir)
            if post:
                posts.append(post)
        elif entry.suffix.lower() == ".json":
            posts.extend(_read_json_export(entry, media_dir))
        else:
            continue
        done_dir.mkdir(exist_ok=True)
        target = done_dir / entry.name
        if target.exists():
            target = done_dir / f"{entry.stem}_{_ref(str(entry))}{entry.suffix}"
        shutil.move(str(entry), str(target))
    return posts


def _read_post_folder(folder: Path, media_dir: Path) -> RawPost | None:
    text_file = next((folder / n for n in TEXT_NAMES if (folder / n).exists()), None)
    if text_file is None:
        text_file = next(iter(sorted(folder.glob("*.txt")) + sorted(folder.glob("*.md"))), None)
    text = text_file.read_text(encoding="utf-8-sig", errors="replace").strip() if text_file else ""
    meta = {}
    if (folder / "meta.json").exists():
        meta = json.loads((folder / "meta.json").read_text(encoding="utf-8-sig"))
    images = sorted(p for p in folder.iterdir() if p.suffix.lower() in IMAGE_EXT)
    if not text and not images:
        return None
    ref = meta.get("id") or _ref("inbox", folder.name, text[:200])
    return RawPost(
        source="ordner",
        ref=ref,
        text=text,
        url=meta.get("url"),
        images=copy_images(images, media_dir / ref),
    )


def _read_json_export(path: Path, media_dir: Path) -> list[RawPost]:
    """Accepts [{"id"?, "url"?, "text", "images": [url or path, ...]}, ...]."""
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if isinstance(data, dict):
        data = data.get("posts", [])
    posts = []
    for entry in data:
        text = (entry.get("text") or "").strip()
        ref = str(entry.get("id") or _ref("json", entry.get("url") or "", text[:200]))
        images = []
        for i, img in enumerate(entry.get("images") or []):
            if str(img).startswith(("http://", "https://")):
                images.append(download_image(img, media_dir / ref, i))
            else:
                images.extend(copy_images([path.parent / img], media_dir / ref))
        posts.append(RawPost("json", ref, text, entry.get("url"), images))
    return posts


_TAG_RE = re.compile(r"<[^>]+>")
_MEDIA_NS = "{http://search.yahoo.com/mrss/}"


def strip_html(raw: str) -> str:
    raw = re.sub(r"<br\s*/?>|</p>", "\n", raw, flags=re.I)
    return html.unescape(_TAG_RE.sub("", raw)).strip()


def read_rss(feed_url: str, media_dir: Path, limit: int = 10) -> list[RawPost]:
    resp = requests.get(feed_url, timeout=30)
    resp.raise_for_status()
    return parse_rss(resp.content, media_dir, limit)


def parse_rss(content: bytes, media_dir: Path, limit: int = 10) -> list[RawPost]:
    root = ET.fromstring(content)
    posts = []
    for item in root.iter("item"):
        link = (item.findtext("link") or "").strip()
        guid = (item.findtext("guid") or link).strip()
        title = (item.findtext("title") or "").strip()
        body = strip_html(item.findtext("description") or "")
        ref = _ref("rss", guid)
        image_urls = [e.get("url") for e in item.findall("enclosure") if (e.get("type") or "").startswith("image")]
        image_urls += [e.get("url") for e in item.findall(f"{_MEDIA_NS}content") if e.get("url")]
        images = []
        for i, url in enumerate(dict.fromkeys(image_urls)):
            try:
                images.append(download_image(url, media_dir / ref, i))
            except requests.RequestException:
                pass
        text = f"{title}\n\n{body}".strip()
        posts.append(RawPost("rss", ref, text, link or None, images))
        if len(posts) >= limit:
            break
    return posts
