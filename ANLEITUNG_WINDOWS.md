# Anleitung für Windows

Diese Anleitung führt dich einmalig durch die Einrichtung. Danach läuft die App auf deinem PC,
holt neue Beiträge aus dem geteilten Ordner, erstellt die deutsche Fassung und postet die
freigegebenen Beiträge zu den eingestellten Zeiten.

Zeitbedarf: etwa 45 Minuten, ohne die Wartezeit auf LinkedIn.

## Was du vorher brauchst

- **Claude-API-Schlüssel:** Auf https://console.anthropic.com registrieren, unter "Billing" ein
  Guthaben aufladen (z. B. 20 EUR) und unter "API Keys" einen Schlüssel erstellen. Er beginnt mit
  `sk-ant-`. Den Schlüssel wie ein Passwort behandeln.
- **Google Drive für Desktop** (oder Dropbox/OneDrive) für den geteilten Ordner mit Nicolas.

## Schritt 1: App herunterladen

1. Bei GitHub angemeldet diesen Link öffnen, die ZIP-Datei wird heruntergeladen:
   https://github.com/likejetzt/finance-app/archive/refs/heads/claude/linkedin-profile-monitor-translate-crj73i.zip
2. Die ZIP-Datei mit Rechtsklick > "Alle extrahieren" entpacken, z. B. nach `C:\LinkedIn-Relay`.
   Nicht in den Google-Drive-Ordner legen.

## Schritt 2: Installieren

1. Im entpackten Ordner **`installieren.bat`** doppelklicken.
2. Falls Windows "Der Computer wurde durch Windows geschützt" anzeigt: auf "Weitere Informationen"
   und dann "Trotzdem ausführen" klicken.
3. Falls Python fehlt, wird es installiert. Dann das Fenster schließen und `installieren.bat`
   noch einmal doppelklicken.
4. Am Ende öffnet sich der Editor mit der Einstellungsdatei `.env`.

## Schritt 3: Einstellungen ausfüllen

In der Datei `.env` hinter dem Gleichheitszeichen eintragen, dann speichern (Strg + S):

| Zeile | Was eintragen |
|---|---|
| `ANTHROPIC_API_KEY=` | dein Claude-Schlüssel |
| `MY_LINK=` | der Link, der unter jedem Beitrag stehen soll |
| `INBOX_DIR=` | Pfad zum geteilten Ordner (siehe Schritt 5) |
| `POST_SLOTS=` | deine Sendezeiten, voreingestellt Mo bis Fr um 08:30 und 12:30 |
| `APP_PASSWORD=` | optional ein Passwort für die Oberfläche |

Die LinkedIn-Zeilen bleiben vorerst leer (siehe Schritt 7).

Die Datei später wieder öffnen: Rechtsklick auf `.env` > "Öffnen mit" > "Editor".
Nach jeder Änderung die App neu starten.

## Schritt 4: Starten

**`starten.bat`** doppelklicken. Es öffnet sich ein schwarzes Fenster und danach der Browser mit
der App (Adresse `http://localhost:5000`). Das schwarze Fenster offen lassen, minimieren ist in
Ordnung. Schließt du es, ist die App aus.

Teste die App zuerst über **"Beitrag importieren"** mit einem Beitrag von Nicolas: Text einfügen,
Grafik hochladen. Nach ein bis drei Minuten ist die deutsche Fassung fertig.

## Schritt 5: Geteilten Ordner einrichten

1. Google Drive für Desktop installieren und anmelden. Im Explorer erscheint ein Laufwerk
   "Google Drive" (meist `G:`).
2. Nicolas oder sein Team teilt einen Ordner mit dir. Füge ihn in Google Drive über
   Rechtsklick > "Verknüpfung zu Ablage hinzufügen" zu "Meine Ablage" hinzu.
3. Im Explorer den Ordner suchen, Rechtsklick > "Als Pfad kopieren" und den Pfad in der `.env`
   hinter `INBOX_DIR=` einfügen.

So muss der Ordner aufgebaut sein: **ein Unterordner pro Beitrag**, darin der Text als
`post.txt` und die Grafik(en) als PNG oder JPG. Optional eine Datei `meta.json` mit dem Link
zum Originalbeitrag: `{"url": "https://www.linkedin.com/posts/..."}`.

```
Geteilter Ordner/
   2026-10-21 Excel-Formeln/
      post.txt
      grafik.png
```

Die App prüft den Ordner jede Stunde. Übernommene Beiträge verschiebt sie in den Unterordner
`_importiert`. So sieht auch Nicolas' Team, was schon verarbeitet ist.

Nachricht an Nicolas' Team (Vorschlag, auf Englisch):

> Hi, as agreed with Nicolas, I'm preparing German versions of his posts for my LinkedIn page.
> To make this easy for you: could you drop each new post into the shared folder as its own
> subfolder, with the post text as post.txt and the graphic(s) as PNG or JPG? A link to the
> original post in a meta.json file is a nice-to-have. Every German post credits Nicolas as
> the original author. Thanks a lot!

## Schritt 6: PC wach halten und Autostart

- **Energieoptionen:** Windows-Einstellungen > System > Netzbetrieb und Energiesparen >
  "Bei Netzbetrieb Standbymodus nach" auf **Nie** stellen. Der Bildschirm darf ausgehen.
- **Autostart:** `autostart_einrichten.bat` doppelklicken. Dann startet die App bei jedem
  Hochfahren von selbst (minimiert, ohne Browser).

War der PC zu einer Sendezeit aus, postet die App den Beitrag nicht verspätet und nicht alles auf
einmal. Sie verschiebt ihn auf den nächsten freien Sendeplatz und vermerkt das beim Beitrag.

## Schritt 7: LinkedIn verbinden

Für automatisches Posten auf deiner Seite braucht es eine Freigabe von LinkedIn:

1. https://www.linkedin.com/developers/apps > "Create app". Als Seite deine LinkedIn-Seite wählen.
2. Die Seite bestätigt die Verknüpfung (Seitenadmin bekommt eine Anfrage).
3. Im Reiter "Products" die **Community Management API** beantragen. LinkedIn prüft das;
   das kann Tage bis Wochen dauern.
4. Im Reiter "Auth" unter "Authorized redirect URLs" eintragen: `http://localhost:5000/linkedin/callback`
5. Client ID und Client Secret aus "Auth" sowie die Seiten-ID in die `.env` eintragen. Die
   Seiten-ID ist die Zahl in der Adresse, wenn du deine Seite als Admin öffnest:
   `linkedin.com/company/12345678/admin`.
6. App neu starten, in der Übersicht auf **"LinkedIn verbinden"** klicken und bestätigen.

**Bis die Freigabe da ist:** Beiträge in der App prüfen, dann Grafik herunterladen und Text
kopieren und auf LinkedIn auf deiner Seite über das Uhr-Symbol neben "Posten" einplanen.

## Täglicher Ablauf

1. App im Browser öffnen: `http://localhost:5000` (Lesezeichen anlegen).
2. Reiter **"Entwurf"**: Beiträge durchsehen, Prüfhinweise lesen, Text bei Bedarf anpassen.
3. **"Freigeben und einplanen"** klicken. Den vorgeschlagenen Termin kannst du ändern.
4. Den Rest erledigt die App.

## Wenn etwas nicht klappt

- **Fenster schließt sich sofort oder zeigt einen Fehler:** Foto vom Fenster an Claude schicken.
- **Beitrag hat Status "Fehler":** Die Meldung steht oben im Beitrag. "Komplett neu erstellen"
  versucht es erneut.
- **Grafik sieht falsch aus:** Unter der Grafik einen Korrekturwunsch eintragen, z. B. "Schrift
  größer, Tabelle wie im Original zweispaltig", und "Grafik neu erstellen" klicken.
