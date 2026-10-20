"""Review UI: check drafts, edit, approve, schedule, publish."""

from __future__ import annotations

import hashlib
import threading
from datetime import datetime, timezone
from pathlib import Path

from flask import (Flask, Response, abort, flash, g, redirect, render_template, request,
                   send_from_directory, session, url_for)
from werkzeug.utils import secure_filename

from .config import Settings, get_settings
from .db import STATUSES, Database
from .linkedin import MAX_COMMENTARY, LinkedInClient, LinkedInError
from .pipeline import Pipeline
from .sources import IMAGE_EXT, RawPost

WEEKDAY_NAMES = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]

STATUS_LABELS = {
    "neu": "In Bearbeitung",
    "entwurf": "Entwurf",
    "geplant": "Geplant",
    "veroeffentlicht": "Veröffentlicht",
    "abgelehnt": "Abgelehnt",
    "fehler": "Fehler",
}


def run_in_background(settings: Settings, fn_name: str, *args) -> None:
    """Long Claude calls run outside the request; each thread gets its own DB connection."""
    def target():
        pipeline = Pipeline(settings, Database(settings.db_path))
        getattr(pipeline, fn_name)(*args)
    threading.Thread(target=target, daemon=True).start()


def create_app(settings: Settings | None = None) -> Flask:
    settings = settings or get_settings()
    app = Flask(__name__)
    app.secret_key = settings.secret_key
    app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024

    def db() -> Database:
        if "db" not in g:
            g.db = Database(settings.db_path)
        return g.db

    def pipeline() -> Pipeline:
        return Pipeline(settings, db())

    @app.teardown_appcontext
    def close_db(_exc):
        conn = g.pop("db", None)
        if conn is not None:
            conn.conn.close()

    @app.before_request
    def require_password():
        if not settings.app_password or request.endpoint == "linkedin_callback":
            return None
        auth = request.authorization
        if auth and auth.password == settings.app_password:
            return None
        return Response("Anmeldung erforderlich", 401, {"WWW-Authenticate": 'Basic realm="LinkedIn Relay"'})

    @app.template_filter("local")
    def local_time(iso: str | None) -> str:
        if not iso:
            return ""
        local = datetime.fromisoformat(iso).astimezone(settings.timezone)
        return f"{WEEKDAY_NAMES[local.weekday()]} {local:%d.%m.%Y %H:%M}"

    @app.template_filter("input_dt")
    def input_dt(iso: str | None) -> str:
        if not iso:
            return ""
        return datetime.fromisoformat(iso).astimezone(settings.timezone).strftime("%Y-%m-%dT%H:%M")

    @app.template_filter("media")
    def media_url(path: str) -> str:
        rel = Path(path).resolve().relative_to((settings.data_dir / "media").resolve())
        return url_for("media", filename=rel.as_posix())

    @app.context_processor
    def inject():
        return {"labels": STATUS_LABELS, "settings": settings, "max_chars": MAX_COMMENTARY}

    @app.route("/")
    def index():
        status = request.args.get("status")
        posts = db().list(status if status in STATUSES else None)
        counts = {s: len(db().list(s)) for s in STATUSES}
        token = LinkedInClient(settings, db()).token_status()
        return render_template("index.html", posts=posts, counts=counts, status=status, token=token,
                               now=datetime.now(timezone.utc).timestamp())

    @app.route("/abrufen", methods=["POST"])
    def fetch():
        run_in_background(settings, "daily")
        flash("Abruf gestartet. Neue Beiträge erscheinen nach der Übersetzung als Entwurf.")
        return redirect(url_for("index"))

    @app.route("/import", methods=["GET", "POST"])
    def manual_import():
        if request.method == "GET":
            return render_template("import.html")
        text = request.form.get("text", "").strip()
        url = request.form.get("url", "").strip() or None
        files = [f for f in request.files.getlist("images")
                 if f.filename and Path(f.filename).suffix.lower() in IMAGE_EXT]
        if not text and not files:
            flash("Bitte Text oder mindestens eine Grafik angeben.")
            return redirect(url_for("manual_import"))
        ref = "manuell-" + hashlib.sha1(f"{url}|{text[:200]}|{datetime.now()}".encode()).hexdigest()[:12]
        target = settings.data_dir / "media" / ref
        target.mkdir(parents=True, exist_ok=True)
        images = []
        for i, f in enumerate(files):
            path = target / f"original_{i}{Path(secure_filename(f.filename)).suffix.lower()}"
            f.save(path)
            images.append(str(path))
        ids = pipeline().store([RawPost("manuell", ref, text, url, images)])
        if ids:
            run_in_background(settings, "process", ids[0])
            flash("Beitrag übernommen. Die deutsche Fassung wird erstellt, das dauert 1 bis 3 Minuten.")
            return redirect(url_for("post", post_id=ids[0]))
        flash("Dieser Beitrag wurde bereits importiert.")
        return redirect(url_for("index"))

    @app.route("/beitrag/<int:post_id>")
    def post(post_id: int):
        item = db().get(post_id) or abort(404)
        return render_template("post.html", p=item)

    @app.route("/beitrag/<int:post_id>/aktion", methods=["POST"])
    def action(post_id: int):
        item = db().get(post_id) or abort(404)
        act = request.form.get("aktion")
        fields = {}
        if "de_text" in request.form:
            fields["de_text"] = request.form["de_text"].replace("\r\n", "\n").strip()
            fields["alt_texts"] = [request.form.get(f"alt_{i}", "") for i in range(len(item["de_images"]))]
        when = request.form.get("scheduled_at")
        if when:
            local = datetime.fromisoformat(when).replace(tzinfo=settings.timezone)
            fields["scheduled_at"] = local.astimezone(timezone.utc).isoformat(timespec="seconds")
        text = fields.get("de_text", item["de_text"] or "")

        if act in ("planen", "jetzt") and len(text) > MAX_COMMENTARY:
            flash(f"Der Text hat {len(text)} Zeichen, LinkedIn erlaubt höchstens {MAX_COMMENTARY}.")
            act = "speichern"

        if act == "speichern":
            db().update(post_id, **fields)
            flash("Gespeichert.")
        elif act == "planen":
            if not fields.get("scheduled_at", item["scheduled_at"]):
                flash("Bitte einen Veröffentlichungszeitpunkt wählen.")
                db().update(post_id, **fields)
            else:
                db().update(post_id, status="geplant", error=None, **fields)
                flash("Freigegeben und eingeplant.")
        elif act == "zurueck":
            db().update(post_id, status="entwurf", **fields)
            flash("Planung aufgehoben, Beitrag ist wieder Entwurf.")
        elif act == "ablehnen":
            db().update(post_id, status="abgelehnt", scheduled_at=None)
            flash("Beitrag abgelehnt.")
        elif act == "jetzt":
            db().update(post_id, **fields)
            pipeline().publish(post_id)
            result = db().get(post_id)
            flash("Veröffentlicht." if result["status"] == "veroeffentlicht" else f"Fehler: {result['error']}")
        elif act == "neu_verarbeiten":
            db().update(post_id, status="neu", error=None)
            run_in_background(settings, "process", post_id)
            flash("Wird neu erstellt.")
        elif act == "text_neu":
            db().update(post_id, **fields)
            run_in_background(settings, "regenerate_text", post_id, request.form.get("feedback", ""))
            flash("Text wird neu erstellt. Seite in etwa einer Minute neu laden.")
        elif act and act.startswith("grafik_neu_"):
            db().update(post_id, **fields)
            index = int(act.rsplit("_", 1)[1])
            run_in_background(settings, "regenerate_image", post_id, index,
                              request.form.get(f"feedback_{index}", ""))
            flash(f"Grafik {index + 1} wird neu erstellt. Seite in 1 bis 2 Minuten neu laden.")
        return redirect(url_for("post", post_id=post_id))

    @app.route("/media/<path:filename>")
    def media(filename: str):
        return send_from_directory(settings.data_dir / "media", filename)

    @app.route("/linkedin/verbinden")
    def linkedin_connect():
        if not settings.linkedin_configured:
            flash("LinkedIn-Zugangsdaten fehlen in der .env (LINKEDIN_CLIENT_ID, _SECRET, _ORG_ID).")
            return redirect(url_for("index"))
        url, state = LinkedInClient(settings, db()).authorize_url()
        session["oauth_state"] = state
        return redirect(url)

    @app.route("/linkedin/callback")
    def linkedin_callback():
        if request.args.get("state") != session.pop("oauth_state", None):
            abort(400, "Ungültiger OAuth-Status")
        if "error" in request.args:
            flash(f"LinkedIn-Anmeldung abgebrochen: {request.args.get('error_description', request.args['error'])}")
            return redirect(url_for("index"))
        try:
            LinkedInClient(settings, db()).exchange_code(request.args["code"])
            flash("LinkedIn verbunden.")
        except LinkedInError as exc:
            flash(str(exc))
        return redirect(url_for("index"))

    return app
