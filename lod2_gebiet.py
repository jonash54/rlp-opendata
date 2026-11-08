#!/usr/bin/env python3
"""lod2_gebiet.py — LoD2-Gebäude (CityGML) aus RLP auf ein Gebiet zuschneiden.

Lädt die 2-km-Kacheln von geobasis-rlp.de/data/geb3dlo, nimmt jedes Gebäude,
dessen Grundflächen-Mittelpunkt im Gebiet liegt (Gebäude werden nie
zerschnitten, jedes kommt genau einmal vor) und schreibt eine CityGML-Datei.

Gebiete: Gemarkung (amtliche Grenze aus dem WFS verwaltungsgrenzen_rp),
Gemeinde (AGS), UTM-Rechteck oder 1-km-Kachelnummern.

Nur Python-Standardbibliothek.
"""
from __future__ import annotations

import argparse
import collections
import csv
import os
import re
import shutil
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from xml.sax.saxutils import escape

LOD2 = "https://geobasis-rlp.de/data/geb3dlo/current/gml/LoD2_32_{e}_{n}_2_RP.gml"
WFS = "https://geo5.service24.rlp.de/wfs/verwaltungsgrenzen_rp.fcgi"
CODELISTEN = "https://repository.gdi-de.org/schemas/adv/citygml/Codelisten/"
CACHE = os.path.expanduser("~/.cache/rlp-opendata")
UA = {"User-Agent": "lod2_gebiet.py (geodata tooling)"}


def die(msg: str) -> None:
    print(f"Fehler: {msg}", file=sys.stderr)
    sys.exit(1)


def log(msg: str) -> None:
    print(msg, file=sys.stderr)


def fetch(url: str, timeout: int = 300) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return r.read()


def cached(url: str, name: str, max_age_h: int) -> bytes:
    os.makedirs(CACHE, exist_ok=True)
    p = os.path.join(CACHE, name)
    if os.path.exists(p) and time.time() - os.path.getmtime(p) < max_age_h * 3600:
        return open(p, "rb").read()
    data = fetch(url)
    open(p, "wb").write(data)
    return data


# --- Gebiete -------------------------------------------------------------------
# Ein Gebiet ist eine Liste von Polygonen, jedes eine Liste von Ringen
# [(x, y), ...] in EPSG:25832. Innen ist, was nach der Gerade-ungerade-Regel
# in irgendeinem Polygon liegt (Löcher werden so automatisch ausgespart).

def wfs(typ: str, flt: str | None = None, props: str | None = None) -> str:
    q = dict(SERVICE="WFS", VERSION="2.0.0", REQUEST="GetFeature",
             TYPENAMES=f"vermkv:{typ}", SRSNAME="EPSG:25832")
    if flt:
        q["FILTER"] = flt
    if props:
        q["PROPERTYNAME"] = props
    return fetch(WFS + "?" + urllib.parse.urlencode(q)).decode("utf-8")


def gleich_filter(feld: str, wert: str) -> str:
    return (f"<Filter><PropertyIsEqualTo><PropertyName>{feld}</PropertyName>"
            f"<Literal>{escape(wert)}</Literal></PropertyIsEqualTo></Filter>")


def polygone_aus_gml(xml: str) -> list:
    polys = []
    for p in re.findall(r"<gml:Polygon.*?</gml:Polygon>", xml, re.S):
        ringe = []
        for pl in re.findall(r"<gml:posList[^>]*>([^<]*)", p):
            v = list(map(float, pl.split()))
            ringe.append(list(zip(v[0::2], v[1::2])))
        polys.append(ringe)
    return polys


def feld(xml: str, name: str) -> str:
    m = re.search(rf"<vermkv:{name}>([^<]*)", xml)
    return m[1] if m else ""


def normal(t: str) -> str:
    t = t.lower()
    for a, b in (("ä", "a"), ("ö", "o"), ("ü", "u"), ("ß", "ss")):
        t = t.replace(a, b)
    return t


def gemarkungsliste() -> list[dict]:
    """Alle Gemarkungen von RLP ohne Geometrie (~1 MB, 7 Tage gecacht)."""
    q = dict(SERVICE="WFS", VERSION="2.0.0", REQUEST="GetFeature",
             TYPENAMES="vermkv:gemarkungen_rlp", PROPERTYNAME="gmkgnr,gemarkung,gemeinde,gmdesch")
    xml = cached(WFS + "?" + urllib.parse.urlencode(q), "gemarkungen_rlp.xml", 24 * 7).decode("utf-8")
    return [dict(nr=feld(m, "gmkgnr"), name=feld(m, "gemarkung"), gemeinde=feld(m, "gemeinde"),
                 ags="07" + feld(m, "gmdesch"))
            for m in re.findall(r"<wfs:member>.*?</wfs:member>", xml, re.S)]


def finde_gemarkungen(text: str) -> list[dict]:
    n = normal(text.strip())
    alle = gemarkungsliste()
    exakt = [g for g in alle if n in (g["nr"], normal(g["name"]))]
    return exakt or [g for g in alle if n in normal(g["name"]) or n in normal(g["gemeinde"])]


def gebiet_gemarkung(text: str) -> tuple[list, str]:
    treffer = finde_gemarkungen(text)
    if len(treffer) != 1:
        zeige(treffer)
        die(f"{len(treffer)} Gemarkungen passen zu {text!r}, bitte die Nummer angeben")
    g = treffer[0]
    xml = wfs("gemarkungen_rlp", gleich_filter("gmkgnr", g["nr"]))
    log(f"# Gemarkung {g['name']} ({g['nr']}), Gemeinde {g['gemeinde']} (AGS {g['ags']})")
    return polygone_aus_gml(xml), f"Gemarkung_{g['name']}_{g['nr']}"


def gebiet_gemeinde(ags: str) -> tuple[list, str]:
    if not re.fullmatch(r"07\d{6}", ags):
        die("Gemeinde-AGS hat 8 Stellen und beginnt mit 07, z. B. 07331003")
    # Der Dienst führt den AGS 10-stellig, gmdesch ist der AGS ohne die 07.
    xml = wfs("gemeinde_rlp", gleich_filter("gmdesch", ags[2:]))
    if "<wfs:member>" not in xml:
        die(f"keine Gemeinde mit AGS {ags}")
    name = feld(xml, "gemeinde")
    log(f"# Gemeinde {name} (AGS {ags})")
    return polygone_aus_gml(xml), f"Gemeinde_{name}_{ags}"


def rechteck(e0: float, n0: float, e1: float, n1: float) -> list:
    return [[[(e0, n0), (e1, n0), (e1, n1), (e0, n1)]]]


def lies_kachel(t: str) -> tuple[int, int]:
    """'436/5510', '436_5510', '4365510' oder '324365510' → (436, 5510) in km."""
    m = re.fullmatch(r"(?:32)?(\d{3})[/_,]?(\d{4})", t.strip())
    if not m:
        die(f"Kachelnummer {t!r} nicht verstanden (erwartet z. B. 436/5510)")
    return int(m[1]), int(m[2])


def innen(polys: list, x: float, y: float) -> bool:
    for ringe in polys:
        c = False
        for r in ringe:
            for (x1, y1), (x2, y2) in zip(r, r[1:] + r[:1]):
                if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
                    c = not c
        if c:
            return True
    return False


# Gebäude auf einer Kachelgrenze stehen manchmal in der Nachbardatei, obwohl
# ihr Mittelpunkt (knapp, ~1 m) in dieser Kachel liegt. Darum auch die
# Nachbarkacheln laden, die bis RAND Meter an das Gebiet heranreichen.
RAND = 200


def kacheln_fuer(polys: list) -> list[tuple[int, int]]:
    xs = [x for p in polys for r in p for x, _ in r]
    ys = [y for p in polys for r in p for _, y in r]
    e0, e1 = int((min(xs) - RAND) // 2000) * 2, int((max(xs) + RAND) // 2000) * 2
    n0, n1 = int((min(ys) - RAND) // 2000) * 2, int((max(ys) + RAND) // 2000) * 2
    return [(e, n) for e in range(e0, e1 + 1, 2) for n in range(n0, n1 + 1, 2)]


# --- LoD2 lesen und schreiben ----------------------------------------------------

MITGLIED = re.compile(r"  <core:cityObjectMember>.*?</core:cityObjectMember>\n", re.S)
POSLIST = re.compile(r"<gml:posList[^>]*>([^<]*)<")
GRUND = re.compile(r"<bldg:GroundSurface.*?</bldg:GroundSurface>", re.S)
# bldg:function und bldg:roofType eines Building/BuildingPart, samt Einrückung
ATTR = re.compile(r"([ \t]*)(<bldg:function>([^<]*)</bldg:function>\n)?"
                  r"([ \t]*<bldg:roofType>([^<]*)</bldg:roofType>\n)?")


def lade_kacheln(kacheln: list, ordner: str) -> list[str]:
    pfade = []
    for i, (e, n) in enumerate(kacheln, 1):
        url = LOD2.format(e=e, n=n)
        p = os.path.join(ordner, os.path.basename(url))
        if not os.path.exists(p):
            log(f"# lade {i}/{len(kacheln)} {os.path.basename(url)}")
            try:
                data = fetch(url)
            except urllib.error.HTTPError as err:
                if err.code == 404:
                    log(f"#   gibt es nicht (außerhalb RLP), übersprungen")
                    continue
                raise
            open(p, "wb").write(data)
        pfade.append(p)
    return pfade


def mittelpunkt(block: str) -> tuple[float, float]:
    teil = "".join(GRUND.findall(block)) or block
    v = [float(x) for p in POSLIST.findall(teil) for x in p.split()]
    return sum(v[0::3]) / len(v[0::3]), sum(v[1::3]) / len(v[1::3])


def codeliste(datei: str) -> dict[str, str]:
    xml = cached(CODELISTEN + datei, datei, 24 * 30).decode("utf-8")
    out = {}
    for d in re.findall(r"<gml:Definition.*?</gml:Definition>", xml, re.S):
        namen = [n.strip() for n in re.findall(r"<gml:name[^>]*>([^<]*)", d)]
        if len(namen) > 1:
            out[namen[0]] = namen[1]
    return out


def mit_klartext(block: str, funktion: dict, dach: dict, fehlt: collections.Counter) -> str:
    """Bedeutung von Gebäudefunktion und Dachform als generische Attribute
    direkt vor bldg:function/bldg:roofType einfügen (dort erlaubt das Schema sie)."""
    def gen(ein, name, wert):
        return (f'{ein}<gen:stringAttribute name="{name}">\n'
                f"{ein}  <gen:value>{escape(wert)}</gen:value>\n{ein}</gen:stringAttribute>\n")

    def ersetze(m):
        if not (m[2] or m[4]):
            return m[0]
        neu = ""
        if m[2]:
            if m[3] in funktion: neu += gen(m[1], "Gebaeudefunktion_Bezeichnung", funktion[m[3]])
            else: fehlt["Funktion " + m[3]] += 1
        if m[4]:
            if m[5] in dach: neu += gen(m[1], "Dachform_Bezeichnung", dach[m[5]])
            else: fehlt["Dachform " + m[5]] += 1
        return neu + m[1] + (m[2] or "") + (m[4] or "")
    return ATTR.sub(ersetze, block)


def schreibe(pfad: str, name: str, kopf: str, bloecke: list[str]) -> None:
    v = [float(x) for b in bloecke for p in POSLIST.findall(b) for x in p.split()]
    kopf = re.sub(r"<gml:name>[^<]*", f"<gml:name>{escape(name)}", kopf, count=1)
    if v:
        kopf = re.sub(
            r"(<gml:lowerCorner[^>]*>)[^<]*(</gml:lowerCorner>\s*<gml:upperCorner[^>]*>)[^<]*(</gml:upperCorner>)",
            lambda m: (f"{m[1]}{min(v[0::3]):.3f} {min(v[1::3]):.3f} {min(v[2::3]):.3f}{m[2]}"
                       f"{max(v[0::3]):.3f} {max(v[1::3]):.3f} {max(v[2::3]):.3f}{m[3]}"),
            kopf, count=1)
    with open(pfad, "w", encoding="utf-8") as f:
        f.write(kopf)
        f.writelines(bloecke)
        f.write("</core:CityModel>\n")


def statistik(bloecke: list[str]) -> None:
    funk = collections.Counter(); adr = collections.Counter()
    for b in bloecke:
        m = re.search(r"<bldg:function>([^<]*)", b)
        f = m[1] if m else "(keine)"
        funk[f] += 1
        adr[f] += "<xal:ThoroughfareNumber>" in b
    gesamt = sum(funk.values()); mit = sum(adr.values())
    log(f"# {gesamt} Gebäude, {mit} mit Straße/Hausnummer ({100 * mit / max(gesamt, 1):.0f} %)")
    for f, n in funk.most_common(5):
        log(f"#   {f}: {n} (davon {adr[f]} mit Adresse)")


def cmd_schneiden(args, polys_je_ausgabe: dict[str, list]) -> None:
    """polys_je_ausgabe: Dateiname (ohne .gml) → Gebiet. Bei mehreren Ausgaben
    landet jedes Gebäude in der ersten, die es enthält."""
    alle = [r for polys in polys_je_ausgabe.values() for r in polys]
    kacheln = kacheln_fuer(alle)
    log(f"# {len(kacheln)} LoD2-Kacheln (2 km) überdecken das Gebiet, je 20–80 MB")
    ordner = args.cache or tempfile.mkdtemp(prefix="lod2_")
    os.makedirs(ordner, exist_ok=True)
    os.makedirs(args.ausgabe, exist_ok=True)
    try:
        pfade = lade_kacheln(kacheln, ordner)
        if not pfade:
            die("keine LoD2-Kachel gefunden — liegt das Gebiet in RLP?")
        if args.klartext:
            funktion = codeliste("BuildingFunctionTypeAdV.xml")
            dach = codeliste("RoofTypeTypeAdV.xml")
            fehlt = collections.Counter()
        ergebnis = {k: [] for k in polys_je_ausgabe}
        ids, kopf = set(), None
        for p in pfade:
            text = open(p, encoding="utf-8").read()
            if kopf is None:
                kopf = text[: text.index("  <core:cityObjectMember>")]
            for m in MITGLIED.finditer(text):
                b = m.group()
                x, y = mittelpunkt(b)
                ziel = next((k for k, polys in polys_je_ausgabe.items() if innen(polys, x, y)), None)
                if ziel is None:
                    continue
                gid = re.search(r'gml:id="([^"]+)"', b)[1]
                if gid in ids:
                    continue
                ids.add(gid)
                ergebnis[ziel].append(mit_klartext(b, funktion, dach, fehlt) if args.klartext else b)
        dateien = []
        for name, bloecke in ergebnis.items():
            pfad = os.path.join(args.ausgabe, name + ".gml")
            schreibe(pfad, name, kopf, bloecke)
            dateien.append(pfad)
            log(f"# {pfad}")
            statistik(bloecke)
        if len(ergebnis) > 1 and args.zusammen:
            name = args.zusammen
            pfad = os.path.join(args.ausgabe, name + ".gml")
            schreibe(pfad, name, kopf, [b for bl in ergebnis.values() for b in bl])
            dateien.append(pfad)
            log(f"# {pfad} (alle zusammen)")
        if args.klartext and fehlt:
            log(f"# ohne Klartext (Schlüssel nicht in der AdV-Liste): {dict(fehlt)}")
        if args.zip:
            for pfad in dateien:
                with zipfile.ZipFile(pfad[:-4] + ".zip", "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
                    z.write(pfad, os.path.basename(pfad))
                os.remove(pfad)
                print(pfad[:-4] + ".zip")
        else:
            print("\n".join(dateien))
    finally:
        if not args.cache:
            shutil.rmtree(ordner, ignore_errors=True)


# --- Befehle ---------------------------------------------------------------------

def zeige(gemarkungen: list[dict]) -> None:
    for g in gemarkungen[:40]:
        log(f"  {g['nr']}  {g['name']:<28} Gemeinde {g['gemeinde']} ({g['ags']})")
    if len(gemarkungen) > 40:
        log(f"  … und {len(gemarkungen) - 40} weitere")


def cmd_suche(args) -> None:
    t = finde_gemarkungen(args.text)
    zeige(t)
    if not t:
        die(f"keine Gemarkung zu {args.text!r}")


def cmd_gemarkung(args) -> None:
    polys, name = gebiet_gemarkung(args.gemarkung)
    cmd_schneiden(args, {"LoD2_" + name: polys})


def cmd_gemeinde(args) -> None:
    polys, name = gebiet_gemeinde(args.ags)
    cmd_schneiden(args, {"LoD2_" + name: polys})


def cmd_bbox(args) -> None:
    e0, n0, e1, n1 = args.e0, args.n0, args.e1, args.n1
    cmd_schneiden(args, {f"LoD2_{int(e0)}_{int(n0)}_{int(e1)}_{int(n1)}": rechteck(e0, n0, e1, n1)})


def cmd_kacheln(args) -> None:
    ks = list(dict.fromkeys(lies_kachel(t) for t in args.kacheln))
    gebiete = {f"LoD2_32_{e}_{n}_1_RP": rechteck(e * 1000, n * 1000, e * 1000 + 1000, n * 1000 + 1000)
               for e, n in ks}
    if not args.einzeln:
        gebiete = {f"LoD2_{len(ks)}_Kacheln": [r for p in gebiete.values() for r in p]}
    cmd_schneiden(args, gebiete)


def cmd_schluessel(args) -> None:
    os.makedirs(args.ausgabe, exist_ok=True)
    for datei, name in (("BuildingFunctionTypeAdV.xml", "Gebaeudefunktion_Schluessel_AdV.csv"),
                        ("RoofTypeTypeAdV.xml", "Dachform_Schluessel_AdV.csv")):
        pfad = os.path.join(args.ausgabe, name)
        with open(pfad, "w", encoding="utf-8-sig", newline="") as f:   # BOM: Excel erkennt UTF-8
            w = csv.writer(f, delimiter=";")
            w.writerow(["Schluessel", "Bedeutung"])
            w.writerows(codeliste(datei).items())
        print(pfad)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def schneid_optionen(s):
        s.add_argument("-o", "--ausgabe", default=".", help="Zielordner (Standard: .)")
        s.add_argument("--klartext", action="store_true",
                       help="Bedeutung von Gebäudefunktion und Dachform als Attribute ergänzen")
        s.add_argument("--zip", action="store_true", help="jede Ausgabe als .zip (GML packt ~10:1)")
        s.add_argument("--cache", help="Kacheln hier ablegen und wiederverwenden "
                                       "(Standard: temporär, wird danach gelöscht)")

    s = sub.add_parser("suche", help="Gemarkung nach Name, Gemeinde oder Nummer suchen")
    s.add_argument("text"); s.set_defaults(fn=cmd_suche)

    s = sub.add_parser("gemarkung", help="alle Gebäude einer Gemarkung (Name oder 6-stellige Nummer)")
    s.add_argument("gemarkung"); schneid_optionen(s); s.set_defaults(fn=cmd_gemarkung)

    s = sub.add_parser("gemeinde", help="alle Gebäude einer Gemeinde (8-stelliger AGS)")
    s.add_argument("ags"); schneid_optionen(s); s.set_defaults(fn=cmd_gemeinde)

    s = sub.add_parser("bbox", help="alle Gebäude in einem UTM-Rechteck (EPSG:25832, Meter)")
    for k in ("e0", "n0", "e1", "n1"):
        s.add_argument(k, type=float)
    schneid_optionen(s); s.set_defaults(fn=cmd_bbox)

    s = sub.add_parser("kacheln", help="Gebäude je 1-km-Kachel, z. B. 436/5511 4365510 435_5510")
    s.add_argument("kacheln", nargs="+")
    s.add_argument("--einzeln", action="store_true", help="eine Datei je Kachel statt einer gemeinsamen")
    s.add_argument("--zusammen", metavar="NAME", help="mit --einzeln: zusätzlich alle in einer Datei NAME.gml")
    schneid_optionen(s); s.set_defaults(fn=cmd_kacheln)

    s = sub.add_parser("schluessel", help="AdV-Schlüssellisten (Gebäudefunktion, Dachform) als CSV")
    s.add_argument("-o", "--ausgabe", default="."); s.set_defaults(fn=cmd_schluessel)

    args = ap.parse_args()
    args.zusammen = getattr(args, "zusammen", None)
    args.fn(args)


if __name__ == "__main__":
    main()
