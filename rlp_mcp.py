#!/usr/bin/env python3
"""rlp_mcp.py — MCP-Server (stdio) für den RLP-Open-Data-Katalog (geobasis-rlp.de).

Bietet den Katalog und das Laden der Dateien als MCP-Werkzeuge: Produkte,
AGS- und Gemarkungssuche, Kachel-URLs für Punkt/Rechteck/AGS-Gebiet, ALKIS je
Gemarkung, LAS-Header ohne Voll download — und download lädt die Dateien in
einen lokalen Ordner.

Nur Python-Standardbibliothek (≥ 3.9), kein venv. Nutzt rlp_dl.py und
lod2_gebiet.py aus diesem Ordner; Details zum Katalog in SKILL.md.

Protokoll: JSON-RPC 2.0, eine Nachricht pro Zeile über stdin/stdout
(MCP-stdio-Transport). Meldungen und Protokoll gehen nach stderr, stdout
führt ausschließlich JSON-RPC.

Einrichten (Beispiele):
  OpenCode  ~/.config/opencode/opencode.json:
    {"mcp": {"rlp-opendata": {"type": "local",
      "command": ["python3", "/pfad/zu/rlp_mcp.py"]}}}
  Claude Desktop claude_desktop_config.json:
    {"mcpServers": {"rlp-opendata": {"command": "python3",
      "args": ["/pfad/zu/rlp_mcp.py"]}}}

Von Hand testen:
  printf '%s\n' \\
   '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"test","version":"1"}}}' \\
   '{"jsonrpc":"2.0","method":"notifications/initialized"}' \\
   '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' | python3 rlp_mcp.py
"""
from __future__ import annotations

import json
import os
import re
import struct
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import rlp_dl           # noqa: E402  (eigene Module aus diesem Ordner)
import lod2_gebiet      # noqa: E402

NAME, VERSION = "rlp-opendata", "1.0.0"
PROT_EIGEN = "2025-06-18"
PROT_BKANNT = {"2024-11-05", "2025-03-26", "2025-06-18"}
LIZENZ = ("Datenlizenz Deutschland Namensnennung 2.0 (dl-de/by-2-0); "
          "Quellenvermerk Pflicht: © GeoBasis-DE / LVermGeo RLP (Jahr), dl-de/by-2-0")


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def fmt_groesse(b: float) -> str:
    for ein in ("B", "KB", "MB", "GB", "TB"):
        if b < 1024 or ein == "TB":
            return f"{int(b)} B" if ein == "B" else f"{b:.1f} {ein}"
        b /= 1024
    return f"{b:.1f} TB"


def produkt(key: str) -> dict:
    if key not in rlp_dl.PRODUCTS:
        raise ValueError(f"unbekanntes Produkt {key!r}. Bekannt: {', '.join(rlp_dl.PRODUCTS)}")
    return rlp_dl.PRODUCTS[key]


# --- Werkzeuge -------------------------------------------------------------------

def t_produkte(a: dict) -> str:
    zeilen = [f"{'key':<18}{'Raster':<11}{'Format':<7}URL aus Kachelnr.?   Titel", "-" * 100]
    for k, p in rlp_dl.PRODUCTS.items():
        raster = f"{p['km']} km" if p["km"] else p["art"]
        det = "ja" if p["direct"] else ("Index" if p["km"] else "-")
        zeilen.append(f"{k:<18}{raster:<11}{p['ext']:<7}{det:<18}{p['title']}")
    zeilen.append("")
    zeilen.append("Lizenz: " + LIZENZ)
    zeilen.append("Koordinaten: EPSG:25832, Höhen DHHN2016. Kachelnr. = Südwest-Ecke in km (Ost/Nord).")
    return "\n".join(zeilen)


def t_ags_suchen(a: dict) -> str:
    q = a["suchbegriff"].lower()
    treffer = []
    if os.path.exists(rlp_dl.KREISE_JSON):
        import json as _json
        with open(rlp_dl.KREISE_JSON, encoding="utf-8") as f:
            treffer = [(x["ags"], x["typ"], x["name"]) for x in _json.load(f)
                       if x["ags"].startswith("07") and q in x["name"].lower()]
    if not treffer:
        return (f"Kein Kreis mit {a['suchbegriff']!r} unter den 36 Kreisen/kreisfreien Städten.\n"
                "Gemeinden und Verbandsgemeinden stehen nicht in dieser Liste, ihr AGS ist aber "
                "trotzdem gültig: alle gültigen Codes eines Produkts listet "
                f'curl -s "{rlp_dl.ROOT}/<ordner>/current/meta4/" | grep -oP \'(?<=href=")[^"]+\\.meta4\'')
    zeilen = ["AGS ist hierarchisch: 07=ganze RLP, 5 Stellen=Kreis, 7=Verbandsgemeinde, 8=Gemeinde.",
              "Gemarkungen (für ALKIS/LoD2) mit gemarkung_suchen finden."]
    zeilen += [f"  {ags:<10}{typ:<22}{name}" for ags, typ, name in sorted(treffer)]
    return "\n".join(zeilen)


def t_gemarkung_suchen(a: dict) -> str:
    treffer = lod2_gebiet.finde_gemarkungen(a["text"])
    if not treffer:
        return f"keine Gemarkung zu {a['text']!r}"
    zeilen = [f"  {g['nr']}  {g['name']:<28} Gemeinde {g['gemeinde']} (AGS {g['ags']})"
              for g in treffer[:40]]
    if len(treffer) > 40:
        zeilen.append(f"  … und {len(treffer) - 40} weitere — Suchbegriff präzisieren")
    return "\n".join(zeilen)


def _kachel_urls(pkey: str, minx: float, miny: float, maxx: float, maxy: float,
                 pruefen: bool = False) -> str:
    p = produkt(pkey)
    if not p["km"]:
        raise ValueError(f"{pkey} hat kein Kachelraster ({p['art']}) — urls_gebiet nutzen"
                         + (" oder alkis_url" if p["art"] == "gemarkung" else ""))
    tiles = rlp_dl.tiles_in_bbox(minx, miny, maxx, maxy, p["km"])
    zeilen = [f"# {p['title']}",
              f"# UTM32-Bbox {minx:.0f},{miny:.0f},{maxx:.0f},{maxy:.0f} "
              f"-> {len(tiles)} Kachel(n) à {p['km']} km"]
    urls, total = [], 0
    if p["direct"]:
        base = f"{rlp_dl.ROOT}/{p['dir']}/current/{p['subdir']}/"
        for e, n in tiles:
            url = base + p["direct"].format(e=e, n=n)
            if pruefen:
                ok, size = rlp_dl.head_ok(url)
                if not ok:
                    zeilen.append(f"#   fehlt: {os.path.basename(url)}")
                    continue
                total += size
            urls.append(url)
        if not pruefen:
            zeilen.append("# Größen unbekannt — mit pruefen=true per HEAD-Request nachschlagen")
    else:
        zeilen.append(f"# Jahr im Dateinamen -> Landesindex wird geladen "
                      f"(gecacht in {rlp_dl.CACHE}, 24 h)")
        idx = rlp_dl.index_by_tile(pkey)
        for e, n in tiles:
            hit = idx.get((e, n))
            if not hit:
                zeilen.append(f"#   keine Kachel für {e}/{n} (außerhalb RLP oder Lücke)")
                continue
            name, size, url = hit
            total += size
            urls.append(url)
    zeilen.append(f"# {len(urls)} Dateien, Summe {fmt_groesse(total)}"
                  + (" (geprüft)" if pruefen and p["direct"] else ""))
    return "\n".join(zeilen + urls)


def t_urls_punkt(a: dict) -> str:
    x, y = (a["lon"], a["lat"]) if a.get("utm") else rlp_dl.lonlat_to_utm32(a["lon"], a["lat"])
    return _kachel_urls(a["produkt"], x, y, x, y, bool(a.get("pruefen")))


def t_urls_bbox(a: dict) -> str:
    if a.get("utm"):
        minx, miny, maxx, maxy = a["west"], a["sued"], a["ost"], a["nord"]
    else:
        minx, miny = rlp_dl.lonlat_to_utm32(a["west"], a["sued"])
        maxx, maxy = rlp_dl.lonlat_to_utm32(a["ost"], a["nord"])
    return _kachel_urls(a["produkt"], minx, miny, maxx, maxy, bool(a.get("pruefen")))


def t_urls_gebiet(a: dict) -> str:
    pkey, ags = a["produkt"], a["ags"]
    p = produkt(pkey)
    cap = int(a.get("max_urls", 300))
    url = rlp_dl.meta4_url(pkey, ags)
    entries = rlp_dl.parse_metalink(rlp_dl.fetch(url))
    data = [e for e in entries if e[0].endswith("." + p["ext"])]
    urls = list(dict.fromkeys(u for _, _, u in data))
    veraltet = len(urls) < len(data)
    total = sum(s for _, s, _ in data)
    zeilen = [f"# {p['title']}",
              f"# AGS {ags}: {len(urls)} Datendateien, {fmt_groesse(total)}",
              f"# Metalink: {url}"]
    if veraltet:
        zeilen.append("# Achtung: der Metalink enthält veraltete Einträge (alte Prüfsummen) — "
                      "URL-Liste laden, aria2c mit diesem Metalink kann an der Prüfsumme scheitern")
    if len(urls) > cap:
        zeilen.append(f"# (nur die ersten {cap} von {len(urls)} URLs — max_urls erhöhen, "
                      "oder die ganze Liste mit download ags+produkt laden)")
        urls = urls[:cap]
    return "\n".join(zeilen + urls)


def t_alkis_url(a: dict) -> str:
    treffer = lod2_gebiet.finde_gemarkungen(a["gemarkung"])
    if len(treffer) != 1:
        liste = "\n".join(f"  {g['nr']}  {g['name']:<28} Gemeinde {g['gemeinde']} (AGS {g['ags']})"
                          for g in treffer[:40])
        return (f"{len(treffer)} Gemarkungen passen — bitte die Nummer angeben:\n{liste}"
                if treffer else f"keine Gemarkung zu {a['gemarkung']!r}")
    g = treffer[0]
    ordner = f"{rlp_dl.ROOT}/bda/current/xml/"
    listing = rlp_dl.cached(ordner).decode("utf-8", "replace")
    m = re.search(rf'href="(bda_\d+_{g["nr"][2:]}_[^"]+\.zip)"', listing)
    if not m:
        raise ValueError(f"keine bda-Datei für Gemarkung {g['name']} ({g['nr']})")
    url = ordner + m[1]
    ok, size = rlp_dl.head_ok(url)
    return (f"# ALKIS-Bestandsdaten (NAS-XML) Gemarkung {g['name']} ({g['nr']}), "
            f"Gemeinde {g['gemeinde']}" + (f", {fmt_groesse(size)}" if ok else "") + f"\n{url}")


def t_datei_info(a: dict) -> str:
    """LAS/LAZ-Public-Header per Range-Request (512 Byte statt Vollabruf)."""
    d = rlp_dl.fetch(a["url"], rng="bytes=0-511")
    if d[:4] != b"LASF":
        raise ValueError("keine LAS/LAZ-Datei (Signatur LASF fehlt) — datei_info geht nur für Punktwolken")
    ver = (d[24], d[25])
    maxx, minx, maxy, miny, maxz, minz = struct.unpack_from("<6d", d, 179)
    n = (struct.unpack_from("<Q", d, 247)[0] if ver >= (1, 4)
         else struct.unpack_from("<I", d, 107)[0])
    return (f"LAS-Version : {ver[0]}.{ver[1]}\n"
            f"BBox EPSG:25832: {minx:.0f}, {miny:.0f}, {maxx:.0f}, {maxy:.0f}\n"
            f"Höhe        : {minz:.1f} – {maxz:.1f} m\n"
            f"Punkte      : {n:,}".replace(",", "."))


def t_download(a: dict) -> str:
    urls = [u.strip() for u in a.get("urls", []) if u.strip()]
    ags, pkey = a.get("ags"), a.get("produkt")
    if not urls and ags and pkey:                      # Gebiet direkt laden
        p = produkt(pkey)
        entries = rlp_dl.parse_metalink(rlp_dl.fetch(rlp_dl.meta4_url(pkey, ags)))
        urls = list(dict.fromkeys(u for name, _, u in entries
                                  if name.endswith("." + p["ext"])))
    if not urls:
        raise ValueError("keine URLs — entweder urls angeben oder ags+produkt")
    if len(urls) > 2000:
        raise ValueError(f"{len(urls)} URLs — für so große Läufe lieber aria2c mit dem "
                         "Metalink aus urls_gebiet (parallel, prüft SHA-256).")
    ziel = os.path.expanduser(a["ziel_ordner"])
    max_gb = float(a.get("max_gb", 20))
    par = max(1, min(int(a.get("parallel", 4)), 8))
    os.makedirs(ziel, exist_ok=True)

    with ThreadPoolExecutor(par) as ex:
        groessen = list(ex.map(lambda u: rlp_dl.head_ok(u)[1], urls))
    total = sum(groessen)
    if total > max_gb * 1024**3:
        raise ValueError(f"{len(urls)} Dateien, {fmt_groesse(total)} — über der Grenze max_gb="
                         f"{max_gb:g}. Gebiet verkleinern oder max_gb erhöhen.")

    def lade(u: str) -> tuple[str, int, str]:
        name = os.path.basename(urllib.parse.urlsplit(u).path) or "download"
        p = os.path.join(ziel, name)
        if os.path.exists(p) and os.path.getsize(p) > 0:
            return p, os.path.getsize(p), "übersprungen (lag schon da)"
        tmp = p + ".part"
        req = urllib.request.Request(u, headers=rlp_dl.UA)
        try:
            with urllib.request.urlopen(req, timeout=1800) as r, open(tmp, "wb") as f:
                while True:
                    b = r.read(1 << 20)
                    if not b:
                        break
                    f.write(b)
            os.replace(tmp, p)
            return p, os.path.getsize(p), "geladen"
        except Exception as e:  # noqa: BLE001
            try:
                os.remove(tmp)
            except OSError:
                pass
            raise RuntimeError(f"{name}: {type(e).__name__}: {e}") from e

    zeilen, fehler = [], []
    with ThreadPoolExecutor(par) as ex:
        for (p, size, status), u in zip(ex.map(lade, urls), urls):
            (zeilen if status != "fehler" else fehler).append(
                f"  {p}  {fmt_groesse(size)}  {status}")
    n_gel = sum(1 for z in zeilen if "geladen" in z)
    n_ueb = sum(1 for z in zeilen if "übersprungen" in z)
    bericht = [f"# {n_gel} geladen, {n_ueb} übersprungen, {len(fehler)} Fehler — "
               f"{fmt_groesse(total)} nach {ziel}", *zeilen]
    if fehler:
        bericht.append("# Fehler:")
        bericht += fehler
        bericht.append(f"# Lizenz: {LIZENZ}")
    elif not fehler:
        bericht.append(f"# Lizenz: {LIZENZ}")
    return "\n".join(bericht)


def t_lod2_zuschneiden(a: dict) -> str:
    """Dünner Wrapper um lod2_gebiet.py (Nähe, Gründe und Randgebäude dort)."""
    art = a["gebiet_art"]
    if art not in ("gemarkung", "gemeinde", "bbox"):
        raise ValueError("gebiet_art: gemarkung | gemeinde | bbox")
    cmd = [sys.executable, os.path.join(HERE, "lod2_gebiet.py"), art]
    if art == "bbox":
        for k in ("e0", "n0", "e1", "n1"):
            if k not in a:
                raise ValueError(f"bbox braucht {k}")
            cmd.append(str(a[k]))
    else:
        if "gebiet" not in a:
            raise ValueError("gebiet fehlt (Gemarkungsname/-nummer oder 8-stelliger AGS)")
        cmd.append(str(a["gebiet"]))
    if a.get("klartext"):
        cmd.append("--klartext")
    if a.get("zip"):
        cmd.append("--zip")
    cmd += ["-o", os.path.expanduser(a.get("ziel_ordner", "."))]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=7200)
    out = (r.stdout or "").strip()
    protokoll = (r.stderr or "").strip()
    if r.returncode != 0:
        raise RuntimeError((protokoll or out or f"lod2_gebiet.py exit {r.returncode}")[-4000:])
    return (out + "\n" if out else "") + protokoll + f"\n# Lizenz: {LIZENZ}"


# --- Werkzeug-Registry -------------------------------------------------------------

def schema(**props) -> dict:
    """JSON-Schema; pfl=True (bei num/strf) markiert Pflichtfelder."""
    return dict(type="object",
                properties={k: {kk: vv for kk, vv in v.items() if kk != "pflicht"}
                            for k, v in props.items()},
                required=[k for k, v in props.items() if v.get("pflicht")],
                additionalProperties=False)


def num(besch: str, pfl=True) -> dict:
    d = dict(type="number", description=besch)
    if pfl:
        d["pflicht"] = True
    return d


def strf(besch: str, pfl=True, **extra) -> dict:
    d = dict(type="string", description=besch)
    if pfl:
        d["pflicht"] = True
    d.update(extra)
    return d


PRODUKT_DESC = "Produkt-Schlüssel, siehe produkte (z. B. dgm1, las, dop20rgbi, geb3dlo, bda)"
P_SCHEMA = dict(type="string", description=PRODUKT_DESC)

TOOLS = [
    dict(name="produkte",
         description="Katalog aller offenen Geobasisdaten RLPs auf geobasis-rlp.de: "
                     "Produkt-Schlüssel, Kachelraster, Format. Immer zuerst aufrufen.",
         inputSchema=schema(), fn=t_produkte),
    dict(name="ags_suchen",
         description="Amtlichen Gemeindeschlüssel (AGS) eines Kreises oder einer kreisfreien "
                     "Stadt RLPs suchen (für urls_gebiet).",
         inputSchema=schema(suchbegriff=strf("Kreisname, z. B. Altenkirchen")), fn=t_ags_suchen),
    dict(name="gemarkung_suchen",
         description="Gemarkungen (Katasterbezirke) RLPs nach Name, Gemeinde oder Nummer "
                     "suchen — für alkis_url und lod2_zuschneiden.",
         inputSchema=schema(text=strf("Name, Gemeinde oder 6-stellige Gemarkungsnummer")),
         fn=t_gemarkung_suchen),
    dict(name="urls_punkt",
         description="Download-URLs der Kacheln an einem Punkt (Lon/Lat WGS84 oder UTM32).",
         inputSchema=schema(lon=num("Längengrad (oder Ost, wenn utm=true)"),
                            lat=num("Breitengrad (oder Nord, wenn utm=true)"),
                            produkt=P_SCHEMA,
                            utm=dict(type="boolean", description="Eingabe ist EPSG:25832 statt Lon/Lat",
                                     default=False),
                            pruefen=dict(type="boolean",
                                         description="Existenz+Größe je Kachel per HEAD prüfen",
                                         default=False)),
         fn=t_urls_punkt),
    dict(name="urls_bbox",
         description="Download-URLs aller Kacheln, die ein Rechteck berührt.",
         inputSchema=schema(west=num("West (Lon bzw. min Ost, wenn utm=true)"),
                            sued=num("Süd"), ost=num("Ost"), nord=num("Nord"),
                            produkt=P_SCHEMA,
                            utm=dict(type="boolean", description="Eingabe ist EPSG:25832 (Meter)",
                                     default=False),
                            pruefen=dict(type="boolean", default=False)),
         fn=t_urls_bbox),
    dict(name="urls_gebiet",
         description="Alle Dateien eines AGS-Gebiets über den Metalink des Servers "
                     "(AGS: 07=RLP, 5=Kreis, 7=Verbandsgemeinde, 8=Gemeinde). Liefert Zahl, "
                     "Gesamtgröße und URLs — Größe erst prüfen, dann laden.",
         inputSchema=schema(ags=strf("Amtlicher Gemeindeschlüssel, z. B. 07132"),
                            produkt=P_SCHEMA,
                            max_urls=dict(type="integer", default=300,
                                          description="Höchstzahl URLs im Text")),
         fn=t_urls_gebiet),
    dict(name="alkis_url",
         description="URL des ALKIS-Bestandsdatenauszugs (NAS-XML, ZIP) einer Gemarkung.",
         inputSchema=schema(gemarkung=strf("Gemarkungsname oder 6-stellige Nummer, z. B. Alzey")),
         fn=t_alkis_url),
    dict(name="datei_info",
         description="LAS/LAZ-Header einer Punktwolke per Range-Request lesen (512 Byte): "
                     "BBox, Höhen, Punktzahl — ohne die Datei zu laden.",
         inputSchema=schema(url=strf("URL der .laz/.las-Datei")), fn=t_datei_info),
    dict(name="download",
         description="Dateien von geobasis-rlp.de in einen lokalen Ordner laden. Entweder "
                     "urls (aus urls_punkt/-bbox/-gebiet/alkis_url) oder ags+produkt direkt. "
                     "Prüft Gesamtgröße gegen max_gb, lädt parallel, setzt vorhandene Dateien "
                     "übersprungen fort. Für >2000 Dateien aria2c mit dem Metalink verwenden.",
         inputSchema=schema(urls=dict(type="array", items=dict(type="string"),
                                      description="URLs zum Laden"),
                            ags=strf("stattdessen: AGS-Gebiet direkt laden", pfl=False),
                            produkt=dict(type="string", description=PRODUKT_DESC),
                            ziel_ordner=strf("Zielordner, wird angelegt"),
                            max_gb=dict(type="number", default=20,
                                        description="Abbruch, wenn die Dateien zusammen größer sind"),
                            parallel=dict(type="integer", default=4,
                                          description="gleichzeitige Downloads (1–8)")),
         fn=t_download),
    dict(name="lod2_zuschneiden",
         description="LoD2-3D-Gebäude (CityGML) auf Gemarkung, Gemeinde (AGS) oder UTM-Rechteck "
                     "zuschneiden; lädt die nötigen 2-km-Kacheln selbst und löscht sie danach. "
                     "Gebäude werden nie zerschnitten, Nachbarkacheln werden mitgeladen.",
         inputSchema=schema(gebiet_art=strf("gemarkung | gemeinde | bbox"),
                            gebiet=strf("Gemarkungsname/-nummer oder 8-stelliger AGS", pfl=False),
                            e0=num("min Ost in m (nur bbox)", pfl=False),
                            n0=num("min Nord (nur bbox)", pfl=False),
                            e1=num("max Ost (nur bbox)", pfl=False),
                            n1=num("max Nord (nur bbox)", pfl=False),
                            klartext=dict(type="boolean", default=False,
                                          description="Gebäudefunktion/Dachform als Klartext-Attribute"),
                            zip=dict(type="boolean", default=False, description="Ausgaben als .zip"),
                            ziel_ordner=strf("Zielordner", pfl=False)),
         fn=t_lod2_zuschneiden),
]
TOOLS_BY = {t["name"]: t for t in TOOLS}


# --- JSON-RPC über stdio -------------------------------------------------------------

def send(msg: dict) -> None:
    sys.stdout.buffer.write(json.dumps(msg, ensure_ascii=False).encode("utf-8") + b"\n")
    sys.stdout.buffer.flush()


def antwort(id_, ergebnis: dict) -> None:
    send(dict(jsonrpc="2.0", id=id_, result=ergebnis))


def fehler(id_, code: int, msg: str) -> None:
    send(dict(jsonrpc="2.0", id=id_, error=dict(code=code, message=msg)))


def handle(req: dict) -> None:
    meth = req.get("method")
    id_ = req.get("id")
    params = req.get("params") or {}
    if meth is None:                                   # Antwort des Clients o. Ä.
        return
    if id_ is None:                                    # Notification
        if meth not in ("notifications/initialized", "notifications/cancelled",
                        "notifications/progress", "notifications/message"):
            log(f"unbekannte Notification {meth!r}")
        return
    if meth == "initialize":
        pv = params.get("protocolVersion")
        antwort(id_, dict(
            protocolVersion=pv if pv in PROT_BKANNT else PROT_EIGEN,
            capabilities=dict(tools=dict(listChanged=False)),
            serverInfo=dict(name=NAME, version=VERSION),
            instructions="Offene Geobasisdaten Rheinland-Pfalz (geobasis-rlp.de). "
                         "Mit produkte beginnen, URLs mit urls_* lösen, mit download laden. "
                         + LIZENZ))
        return
    if meth == "ping":
        antwort(id_, {})
        return
    if meth == "resources/list" or meth == "prompts/list":
        antwort(id_, {meth.split("/")[0]: []})
        return
    if meth == "tools/list":
        antwort(id_, dict(tools=[{k: t[k] for k in ("name", "description", "inputSchema")}
                                 for t in TOOLS]))
        return
    if meth == "tools/call":
        t = TOOLS_BY.get(params.get("name", ""))
        if not t:
            fehler(id_, -32602, f"unbekanntes Werkzeug {params.get('name')!r}")
            return
        try:
            text = t["fn"](params.get("arguments") or {})
            antwort(id_, dict(content=[dict(type="text", text=text)], isError=False))
        except SystemExit as e:                        # rlp_dl.py meldet über die Konsole
            antwort(id_, dict(content=[dict(type="text", text=f"Fehler: {e}")], isError=True))
        except Exception as e:  # noqa: BLE001
            antwort(id_, dict(content=[dict(type="text",
                                            text=f"{type(e).__name__}: {e}")], isError=True))
        return
    fehler(id_, -32601, f"Methode nicht bekannt: {meth}")


def main() -> None:
    log(f"{NAME} {VERSION}: MCP-Server am Start (stdio), {len(TOOLS)} Werkzeuge")
    for zeile in sys.stdin.buffer:
        zeile = zeile.strip()
        if not zeile:
            continue
        try:
            req = json.loads(zeile.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as e:
            log(f"Zeile nicht lesbar ({e}): {zeile[:120]!r}")
            continue
        try:
            handle(req)
        except Exception as e:  # noqa: BLE001  — der Server darf nie sterben
            log(f"interner Fehler bei {req.get('method')}: {type(e).__name__}: {e}")
            if req.get("id") is not None:
                fehler(req["id"], -32603, str(e))


if __name__ == "__main__":
    main()
