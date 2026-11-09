# rlp-opendata — Skill für die offenen Geobasisdaten Rheinland-Pfalz

Wissen und Werkzeuge rund um https://geobasis-rlp.de/data/: welche Produkte es
gibt, wie die Kacheln heißen, wie man sie für ein Gebiet findet und lädt,
ALKIS je Gemarkung, LoD2 auf ein Gebiet zuschneiden, AdV-Schlüssellisten.

## Inhalt

- `SKILL.md` — die eigentliche Anleitung (Markdown). Das ist der Teil, den ein
  KI-Modell lesen muss.
- `rlp_dl.py`, `lod2_gebiet.py` — Python-Skripte, nur Standardbibliothek
  (Python 3.9 oder neuer), laufen unter Linux, macOS und Windows.
- `rlp_mcp.py` — MCP-Server (stdio): Katalogsuche und Datei-Downloads als
  Werkzeuge für Claude Desktop, OpenCode & Co., ohne dass das Modell Shell
  commands ausführen darf.
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

## MCP-Server (`rlp_mcp.py`)

Wer das Modell nicht Shell-Befehle ausführen lassen will, hängt die Skripte als
MCP-Server an — wieder nur Standardbibliothek, kein venv. Der Server spricht
JSON-RPC über stdin/stdout und bietet den Katalog als zehn Werkzeuge an:
`produkte`, `ags_suchen`, `gemarkung_suchen`, `urls_punkt`, `urls_bbox`,
`urls_gebiet`, `alkis_url`, `datei_info`, `download` und `lod2_zuschneiden`.

**OpenCode** — am bequemsten per CLI (schreibt `~/.config/opencode/opencode.json`):

```sh
opencode mcp add rlp-opendata --global -- python3 /pfad/zu/rlp-opendata/rlp_mcp.py
```

Von Hand (V2-Format, global oder als `opencode.json` im Projekt):

```json
{"$schema": "https://opencode.ai/config.json",
 "mcp": {"servers": {"rlp-opendata": {"type": "local",
   "command": ["python3", "/pfad/zu/rlp-opendata/rlp_mcp.py"]}}}}
```

**Claude Desktop** (`claude_desktop_config.json`):

```json
{"mcpServers": {"rlp-opendata": {"command": "python3",
  "args": ["/pfad/zu/rlp-opendata/rlp_mcp.py"]}}}
```

`download` lädt in einen Ordner, prüft vorher die Gesamtgröße gegen `max_gb`
und lässt vorhandene Dateien in Ruhe. Für sehr große Läufe (> 2000 Dateien)
weist er auf `aria2c` mit dem Metalink hin — das ist parallel und prüft SHA-256.
Von Hand prüfen:

```bash
printf '%s\n' \
 '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"t","version":"1"}}}' \
 '{"jsonrpc":"2.0","method":"notifications/initialized"}' \
 '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' | python3 rlp_mcp.py
```

## Lizenz der Daten

Die geladenen Daten stehen unter dl-de/by-2-0. Quellenvermerk:
© GeoBasis-DE / LVermGeo RLP (Jahr), dl-de/by-2-0
