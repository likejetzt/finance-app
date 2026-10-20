# LinkedIn Relay

Bereitet Beiträge von Nicolas Boucher auf Deutsch auf und plant sie auf der LinkedIn-Seite von
Peno Finance Insights ein. Für die Übernahme liegt eine Genehmigung des Autors vor.

Ablauf:

1. **Abruf (täglich):** Die App liest neue Beiträge aus dem Eingangsordner, aus JSON-Exporten und
   optional aus RSS-Feeds. Beiträge lassen sich auch in der Weboberfläche manuell importieren.
2. **Deutsche Fassung:** Claude übersetzt den Text, passt ihn an den DACH-Kontext an (deutsche
   Excel-Funktionen, Zahlenformate, US-Begriffe) und schreibt ihn im Stil aus `config/stil.md`.
   Quellenhinweis und Link hängt die App automatisch an.
3. **Grafiken:** Jede Grafik wird auf Deutsch nachgebaut (HTML, gerendert mit Chromium als PNG).
   Name und Handle des Originals werden entfernt, unten steht der Quellenhinweis.
4. **Prüfung:** Die App legt den Beitrag als Entwurf an und schlägt den nächsten freien Sendeplatz
   vor. In der Oberfläche siehst du Original und deutsche Fassung nebeneinander, dazu Prüfhinweise
   der KI. Du kannst den Text bearbeiten, Korrekturwünsche geben und den Beitrag freigeben.
5. **Veröffentlichung:** Freigegebene Beiträge postet der Worker zum geplanten Zeitpunkt über die
   offizielle LinkedIn-API auf der Seite.

## Warum kein automatisches Auslesen des LinkedIn-Profils

LinkedIn bietet keine Schnittstelle, um Beiträge fremder Profile zu lesen. Automatisches Auslesen
(Scraping) verstößt gegen die LinkedIn-Nutzervereinbarung und gefährdet das eigene Konto. Die
Genehmigung von Nicolas Boucher ändert daran nichts, weil es um die Regeln von LinkedIn geht.

Praktikable Wege:

- **Gemeinsamer Ordner (empfohlen):** Nicolas oder sein Team legt Beiträge in einem geteilten
  Google-Drive-, Dropbox- oder OneDrive-Ordner ab. Diesen Ordner als `INBOX_DIR` eintragen.
- **Manueller Import:** Text kopieren und Grafik in der Oberfläche hochladen. Etwa eine Minute pro Beitrag.
- **RSS:** Falls es einen Newsletter-Feed gibt, unter `RSS_URLS` eintragen.

### Format des Eingangsordners

```
inbox/
  2026-10-20-excel-formeln/
    post.txt          # Originaltext
    bild1.png         # eine oder mehrere Grafiken
    meta.json         # optional: {"url": "https://www.linkedin.com/posts/...", "id": "eindeutige-id"}
  export.json         # optional: [{"id": "...", "url": "...", "text": "...", "images": ["https://..." oder "datei.png"]}]
```

Verarbeitete Einträge werden nach `inbox/_importiert/` verschoben.

## Einrichtung

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/playwright install --with-deps chromium
cp .env.example .env      # ausfüllen
.venv/bin/python -m linkedin_relay start
```

Danach die Oberfläche unter http://localhost:5000 öffnen.

### Claude

`ANTHROPIC_API_KEY` in der `.env` eintragen (https://console.anthropic.com). Kostenrahmen:
grob einige Cent für den Text und etwa 10 bis 30 Cent pro Grafik, abhängig von Größe und
Textmenge. Das ist eine Schätzung; die tatsächlichen Kosten zeigt die Anthropic-Konsole.

### LinkedIn

1. Unter https://www.linkedin.com/developers eine App anlegen und mit der LinkedIn-Seite verknüpfen.
2. Das Produkt **Community Management API** beantragen. Ohne diese Freigabe darf die App nicht auf
   Unternehmens- oder Showcase-Seiten posten. LinkedIn prüft den Antrag; das kann einige Tage bis
   Wochen dauern und setzt eine verifizierte Seite voraus.
3. In der App die Redirect-URL `http://localhost:5000/linkedin/callback` eintragen
   (bei Betrieb auf einem Server die öffentliche Adresse).
4. Client-ID, Client-Secret und die Organisations-ID der Seite in die `.env` eintragen.
5. In der Oberfläche auf **LinkedIn verbinden** klicken. Du musst Administratorin der Seite sein.

Das Zugriffstoken gilt 60 Tage. Wenn LinkedIn ein Refresh-Token ausgibt, verlängert die App
automatisch; sonst zeigt die Übersicht an, wann neu verbunden werden muss.

**Bis die API-Freigabe vorliegt:** Entwürfe in der App erstellen, Grafik herunterladen und Text
kopieren, dann in der LinkedIn-Seitenverwaltung über "Beitrag planen" manuell einplanen.

## Betrieb

| Befehl | Zweck |
|---|---|
| `python -m linkedin_relay start` | Oberfläche und Worker (Abruf alle `FETCH_INTERVAL_MINUTES`, Veröffentlichung minütlich) |
| `python -m linkedin_relay worker` | nur Worker, z. B. als systemd-Dienst |
| `python -m linkedin_relay abrufen` | einmal abrufen und übersetzen (für Cron) |
| `python -m linkedin_relay veroeffentlichen` | fällige Beiträge posten (für Cron) |

Die App muss dauerhaft laufen, damit geplante Beiträge pünktlich erscheinen, z. B. auf einem kleinen
Server (Hetzner, IONOS) oder einem Rechner, der eingeschaltet bleibt. Wird sie im Internet
erreichbar gemacht, unbedingt `APP_PASSWORD` setzen und HTTPS verwenden.

Daten (Datenbank, Bilder) liegen in `data/`. Diesen Ordner sichern.

## Tests

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest
```

## Grenzen der ersten Version

- PDF-Karussells (Dokument-Beiträge) werden noch nicht unterstützt, nur Bildbeiträge.
- Der Nachbau der Grafiken ist sehr gut bei Text-Infografiken und Cheat Sheets. Fotos, Logos und
  komplexe Illustrationen werden nicht nachgebaut; die App weist darauf hin.
- Der Ende-zu-Ende-Lauf gegen die echte Claude- und LinkedIn-API ist mit eigenen Zugangsdaten zu
  testen; die Tests prüfen die Logik mit simulierten Antworten.
