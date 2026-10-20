"""Claude calls: German post text in the user's style, German version of graphics."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from pathlib import Path

import anthropic
from PIL import Image

from .config import Settings

MEDIA_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
               ".webp": "image/webp", ".gif": "image/gif"}

TEXT_SCHEMA = {
    "type": "object",
    "properties": {
        "text": {"type": "string"},
        "hinweise": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["text", "hinweise"],
    "additionalProperties": False,
}

GRAPHIC_SCHEMA = {
    "type": "object",
    "properties": {
        "html": {"type": "string"},
        "alt_text": {"type": "string"},
        "hinweise": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["html", "alt_text", "hinweise"],
    "additionalProperties": False,
}

CONTEXT_RULES = """\
Kontextanpassung für Leser in Deutschland, Österreich und der Schweiz:
- Excel-Funktionen in der deutschen Excel-Version angeben (z. B. XLOOKUP -> XVERWEIS,
  SUMIFS -> SUMMEWENNS, IF -> WENN), Argumente mit Semikolon trennen, Dezimalkomma verwenden.
- Englische Fachbegriffe, die im deutschen Finance-Alltag üblich sind (Forecast, Cashflow,
  Dashboard, Power Query), beibehalten. Produkt- und Toolnamen nie übersetzen.
- US-spezifische Regeln oder Begriffe (US GAAP, IRS, 401(k), Sales Tax, Fiscal Year) nur dann
  durch ein deutsches Pendant (HGB, IFRS, Finanzamt, Umsatzsteuer, Geschäftsjahr) ersetzen,
  wenn die Aussage dadurch fachlich korrekt bleibt. Sonst den Begriff stehen lassen oder kurz
  einordnen und einen Hinweis ausgeben.
- Reine Beispielbeträge dürfen in EUR umgestellt werden. Tatsächliche Zahlen, Studienwerte oder
  Fakten aus dem Original niemals umrechnen oder verändern.
- Datums- und Zahlenformate deutsch (20.10.2026, 1.250,50 EUR).
- Nichts hinzuerfinden: keine neuen Fakten, Kennzahlen, Erfahrungen oder Zitate.
"""


class ClaudeRefused(RuntimeError):
    pass


@dataclass
class TextResult:
    text: str
    hints: list[str]


@dataclass
class GraphicResult:
    html: str
    alt_text: str
    hints: list[str]
    width: int
    height: int


class Adapter:
    def __init__(self, settings: Settings, client: anthropic.Anthropic | None = None):
        self.settings = settings
        self.client = client or anthropic.Anthropic()

    def _style_guide(self) -> str:
        path = self.settings.style_guide_path
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def _call(self, system: str, content: list[dict], schema: dict, effort: str) -> dict:
        # fallbacks="default": if a safety classifier declines, the API retries
        # on Anthropic's recommended fallback model inside the same call.
        with self.client.beta.messages.stream(
            model=self.settings.claude_model,
            max_tokens=64000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
            system=system,
            messages=[{"role": "user", "content": content}],
        ) as stream:
            response = stream.get_final_message()
        if response.stop_reason == "refusal":
            raise ClaudeRefused(getattr(response.stop_details, "explanation", None) or "Anfrage abgelehnt")
        if response.stop_reason == "max_tokens":
            raise RuntimeError("Antwort wurde abgeschnitten (max_tokens erreicht)")
        text = next(b.text for b in response.content if b.type == "text")
        return json.loads(text)

    def adapt_text(self, original: str, image_count: int, feedback: str = "") -> TextResult:
        author = self.settings.source_author
        system = (
            f"Du bereitest LinkedIn-Beiträge von {author} für eine deutschsprachige "
            "LinkedIn-Unternehmensseite auf. Der Autor hat die Übernahme und Übersetzung genehmigt.\n\n"
            "Aufgabe: Übersetze den Beitrag ins Deutsche, passe ihn an den DACH-Kontext an und "
            "schreibe ihn im unten beschriebenen Stil. Inhalt und Kernaussagen bleiben erhalten; "
            "Aufbau und Formulierungen darfst du an den Stil anpassen.\n\n"
            f"{CONTEXT_RULES}\n"
            "Füge keinen Link und keine Quellenangabe ein, beides ergänzt das System.\n"
            "Maximal 2600 Zeichen. Höchstens drei deutschsprachige Hashtags am Ende.\n"
            "In 'hinweise' nennst du alles, was eine Person vor der Veröffentlichung prüfen "
            "sollte (unsichere Anpassungen, US-spezifische Inhalte, mögliche Missverständnisse). "
            "Leere Liste, wenn nichts zu prüfen ist.\n\n"
            "# Stilvorgaben\n\n" + self._style_guide()
        )
        note = f"\n\n(Zum Beitrag gehören {image_count} Grafik(en), die separat übersetzt werden.)" if image_count else ""
        if feedback:
            note += f"\n\nKorrekturwunsch zur vorherigen Fassung: {feedback}"
        data = self._call(
            system,
            [{"type": "text", "text": f"<original>\n{original}\n</original>{note}"}],
            TEXT_SCHEMA,
            effort="medium",
        )
        return TextResult(text=data["text"].strip(), hints=data["hinweise"])

    def translate_graphic(self, image_path: str, feedback: str = "") -> GraphicResult:
        path = Path(image_path)
        with Image.open(path) as img:
            w, h = img.size
        # Render at LinkedIn-friendly width, keep aspect ratio.
        width = 1080
        height = round(h * width / w)
        s = self.settings
        system = (
            f"Du erstellst deutsche Fassungen von Grafiken (Infografiken, Cheat Sheets, Schaubilder) "
            f"von {s.source_author}. Die Übernahme ist vom Autor genehmigt.\n\n"
            f"Gib ein vollständiges, eigenständiges HTML-Dokument zurück, das die Grafik auf exakt "
            f"{width} x {height} Pixel nachbaut (html, body: margin 0, feste Breite und Höhe, overflow hidden).\n"
            "- Layout, Reihenfolge, Hierarchie und Farblogik des Originals übernehmen.\n"
            "- Alle Texte ins Deutsche übersetzen. Deutsche Texte sind länger: Schriftgrößen so wählen, "
            "dass nichts überläuft oder abgeschnitten wird.\n"
            f"- Schriftart: font-family {s.brand_font}.\n"
            "- Keine externen Ressourcen (keine Bilder, Fonts oder Skripte von außen). Icons als "
            "einfaches Inline-SVG oder Unicode. Fotos und Logos nicht nachbauen, sondern weglassen "
            "und in 'hinweise' erwähnen.\n"
            f"- Namen, Handles und Logos des Originals entfernen. Unten eine kleine Fußzeile: "
            f"\"{s.attribution_line}\".\n"
            f"- Akzentfarbe für die Fußzeile: {s.brand_accent}.\n\n"
            f"{CONTEXT_RULES}\n"
            "'alt_text': kurze deutsche Bildbeschreibung für Screenreader (max. 300 Zeichen).\n"
            "'hinweise': was vor der Veröffentlichung geprüft werden sollte."
        )
        data_b64 = base64.standard_b64encode(path.read_bytes()).decode("utf-8")
        media_type = MEDIA_TYPES.get(path.suffix.lower(), "image/png")
        data = self._call(
            system,
            [
                {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": data_b64}},
                {"type": "text", "text": "Erstelle die deutsche Fassung dieser Grafik."
                 + (f"\n\nKorrekturwunsch zur vorherigen Fassung: {feedback}" if feedback else "")},
            ],
            GRAPHIC_SCHEMA,
            effort="high",
        )
        return GraphicResult(data["html"], data["alt_text"], data["hinweise"], width, height)
