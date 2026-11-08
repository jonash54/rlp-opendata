# rlp-opendata — Skill für die offenen Geobasisdaten Rheinland-Pfalz

Wissen und Werkzeuge rund um https://geobasis-rlp.de/data/: welche Produkte es
gibt, wie die Kacheln heißen, wie man sie für ein Gebiet findet und lädt,
ALKIS je Gemarkung, LoD2 auf ein Gebiet zuschneiden, AdV-Schlüssellisten.

## Inhalt

- `SKILL.md` — die eigentliche Anleitung (Markdown). Das ist der Teil, den ein
  KI-Modell lesen muss.
- `rlp_dl.py`, `lod2_gebiet.py` — Python-Skripte, nur Standardbibliothek
  (Python 3.9 oder neuer), laufen unter Linux, macOS und Windows.
- `kreise_rlp.json` — Kreisnamen und Schlüssel für `rlp_dl.py ags`.
- `dop_gitter.py`, `dop_klassen.py` — optional, brauchen GDAL und numpy.

## Einrichten

**Claude Code:** den Ordner nach `~/.claude/skills/rlp-opendata/` entpacken.
Claude erkennt den Skill dann von selbst.

**Andere Modelle (Qwen, Ollama, LM Studio, Open WebUI …):** Diese kennen keine
Skills. Den Inhalt von `SKILL.md` als Systemprompt oder Wissensdokument
hinterlegen und dazuschreiben, wo die Skripte liegen, z. B.:

> Die Skripte aus SKILL.md liegen in C:\Tools\rlp-opendata\. Statt $S diesen
> Pfad verwenden.

Wenn das Modell keine Befehle ausführen kann, liefert es die Befehle, und man
startet sie selbst:

```bash
python3 rlp_dl.py produkte
python3 rlp_dl.py alkis Alzey
python3 lod2_gebiet.py gemarkung Alzey --klartext --zip -o ausgabe
```

(Unter Windows `py` statt `python3`.)

Der Abschnitt „Nur auf dem jh54-Server“ in `SKILL.md` gilt nur für einen
bestimmten Server und kann woanders ignoriert werden.

## Lizenz der Daten

Die geladenen Daten stehen unter dl-de/by-2-0. Quellenvermerk:
© GeoBasis-DE / LVermGeo RLP (Jahr), dl-de/by-2-0
