"""LinkedIn REST API: OAuth, image upload and posts on an organization page.

Posting as a company or showcase page needs the scope ``w_organization_social``,
which LinkedIn grants through the "Community Management API" product of a
developer app (application with review). The authenticated member must be an
admin of the page.
"""

from __future__ import annotations

import re
import secrets
import time
from pathlib import Path
from urllib.parse import urlencode

import requests

from .config import Settings
from .db import Database

AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
API = "https://api.linkedin.com/rest"
TOKEN_KEY = "linkedin_token"
MAX_COMMENTARY = 3000

# Reserved characters of LinkedIn's "little text" format used in `commentary`.
_RESERVED = re.compile(r"([\\|{}@\[\]()<>#*_~])")
_HASHTAG = re.compile(r"(?<![\w#])#(\w+)", re.UNICODE)


class LinkedInError(RuntimeError):
    pass


def escape_commentary(text: str) -> str:
    """Escape reserved characters; keep #hashtags as real hashtags."""
    tags: list[str] = []

    def stash(match: re.Match) -> str:
        tags.append(match.group(1))
        return f"\x00{len(tags) - 1}\x00"

    text = _HASHTAG.sub(stash, text)
    text = _RESERVED.sub(r"\\\1", text)
    return re.sub(r"\x00(\d+)\x00", lambda m: "{hashtag|\\#|" + tags[int(m.group(1))] + "}", text)


class LinkedInClient:
    def __init__(self, settings: Settings, db: Database, session: requests.Session | None = None):
        self.s = settings
        self.db = db
        self.http = session or requests.Session()

    # --- OAuth -----------------------------------------------------------

    def authorize_url(self) -> tuple[str, str]:
        state = secrets.token_urlsafe(16)
        query = urlencode({
            "response_type": "code",
            "client_id": self.s.linkedin_client_id,
            "redirect_uri": self.s.linkedin_redirect_uri,
            "state": state,
            "scope": self.s.linkedin_scope,
        })
        return f"{AUTH_URL}?{query}", state

    def exchange_code(self, code: str) -> None:
        self._store_token(self._token_request({
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.s.linkedin_redirect_uri,
        }))

    def _token_request(self, data: dict) -> dict:
        data |= {"client_id": self.s.linkedin_client_id, "client_secret": self.s.linkedin_client_secret}
        resp = self.http.post(TOKEN_URL, data=data, timeout=30)
        if resp.status_code != 200:
            raise LinkedInError(f"Token-Anfrage fehlgeschlagen: {resp.status_code} {resp.text}")
        return resp.json()

    def _store_token(self, payload: dict) -> None:
        now = int(time.time())
        token = {
            "access_token": payload["access_token"],
            "expires_at": now + int(payload.get("expires_in", 0)),
        }
        old = self.db.get_kv(TOKEN_KEY) or {}
        if payload.get("refresh_token"):
            token["refresh_token"] = payload["refresh_token"]
            token["refresh_expires_at"] = now + int(payload.get("refresh_token_expires_in", 0))
        elif old.get("refresh_token"):
            token["refresh_token"] = old["refresh_token"]
            token["refresh_expires_at"] = old.get("refresh_expires_at", 0)
        self.db.set_kv(TOKEN_KEY, token)

    def token_status(self) -> dict | None:
        return self.db.get_kv(TOKEN_KEY)

    def access_token(self) -> str:
        token = self.db.get_kv(TOKEN_KEY)
        if not token:
            raise LinkedInError("LinkedIn ist nicht verbunden. Bitte in der App unter 'LinkedIn verbinden' anmelden.")
        if token["expires_at"] - time.time() < 3600:
            if token.get("refresh_token") and token.get("refresh_expires_at", 0) > time.time():
                self._store_token(self._token_request({
                    "grant_type": "refresh_token",
                    "refresh_token": token["refresh_token"],
                }))
                token = self.db.get_kv(TOKEN_KEY)
            elif token["expires_at"] <= time.time():
                raise LinkedInError("LinkedIn-Token ist abgelaufen. Bitte neu verbinden.")
        return token["access_token"]

    # --- API -------------------------------------------------------------

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.access_token()}",
            "LinkedIn-Version": self.s.linkedin_version,
            "X-Restli-Protocol-Version": "2.0.0",
        }

    def upload_image(self, path: Path) -> str:
        resp = self.http.post(
            f"{API}/images?action=initializeUpload",
            json={"initializeUploadRequest": {"owner": self.s.org_urn}},
            headers=self._headers(),
            timeout=30,
        )
        if resp.status_code != 200:
            raise LinkedInError(f"Bild-Upload konnte nicht gestartet werden: {resp.status_code} {resp.text}")
        value = resp.json()["value"]
        put = self.http.put(
            value["uploadUrl"],
            data=path.read_bytes(),
            headers={"Authorization": f"Bearer {self.access_token()}"},
            timeout=120,
        )
        if put.status_code not in (200, 201):
            raise LinkedInError(f"Bild-Upload fehlgeschlagen: {put.status_code} {put.text}")
        return value["image"]

    def create_post(self, text: str, images: list[Path], alt_texts: list[str]) -> str:
        commentary = escape_commentary(text)
        if len(text) > MAX_COMMENTARY:
            raise LinkedInError(f"Text ist {len(text)} Zeichen lang, LinkedIn erlaubt {MAX_COMMENTARY}.")
        body = {
            "author": self.s.org_urn,
            "commentary": commentary,
            "visibility": "PUBLIC",
            "distribution": {
                "feedDistribution": "MAIN_FEED",
                "targetEntities": [],
                "thirdPartyDistributionChannels": [],
            },
            "lifecycleState": "PUBLISHED",
            "isReshareDisabledByAuthor": False,
        }
        urns = [self.upload_image(p) for p in images]
        alts = [(alt_texts[i] if i < len(alt_texts) else "")[:300] for i in range(len(urns))]
        if len(urns) == 1:
            body["content"] = {"media": {"id": urns[0], "altText": alts[0]}}
        elif len(urns) > 1:
            body["content"] = {"multiImage": {"images": [
                {"id": u, "altText": a} for u, a in zip(urns, alts)
            ]}}
        resp = self.http.post(f"{API}/posts", json=body, headers=self._headers(), timeout=60)
        if resp.status_code != 201:
            raise LinkedInError(f"Beitrag konnte nicht erstellt werden: {resp.status_code} {resp.text}")
        return resp.headers.get("x-restli-id", "")
