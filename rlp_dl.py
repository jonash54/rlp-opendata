#!/usr/bin/env python3
"""rlp_dl.py — Auflöser für RLP-Open-Data-Downloads (geobasis-rlp.de).

Erzeugt Download-URL-Listen für alle offenen Produkte des LVermGeo RLP,
aus einem Punkt, einer Bounding-Box, einem Amtlichen Gemeindeschlüssel (AGS)
oder (ALKIS) einer Gemarkung.

Nur Python-Standardbibliothek. Reprojektion WGS84→UTM32 nutzt osgeo.osr falls
vorhanden, sonst eine eingebaute Transversal-Mercator-Formel.

Details zum Kachel- und Metalink-Schema: SKILL.md neben diesem Skript.
"""
from __future__ import annotations

import argparse
import math
import os
import re
import struct
import sys
import time
import urllib.error
import urllib.request

ROOT = "https://geobasis-rlp.de/data"
CACHE = os.path.expanduser("~/.cache/rlp-opendata")
UA = {"User-Agent": "rlp_dl.py (geodata tooling)"}

# --- Produktdefinitionen ------------------------------------------------------
# Alle Ordner unter https://geobasis-rlp.de/data/ (Stand 2026-10-29).
# meta4:  <dir>/current/meta4/<meta4_prefix>_<AGS>.meta4  (AGS 07 = ganz RLP)
# direct: Dateiname aus der Kachel-SW-Ecke (km) konstruierbar; None = Index nötig
# km:     Kachelkante; None = kein Kachelraster (Blattschnitt, Gemarkung, ganzes Land)
# art:    kachel | blatt (DTK-Blattschnitt) | gemarkung (eine Datei je Gemarkung)
#         | land (eine Datei für ganz RLP)
def _p(title, dir, subdir, ext, km, meta4_prefix, direct=None, art="kachel"):
    return dict(title=title, dir=dir, subdir=subdir, ext=ext, km=km,
                meta4_prefix=meta4_prefix, direct=direct, art=art)


PRODUCTS = {
    # Höhe und Punktwolken
    "las": _p("Laserpunkte LPG+LPO (Boden+Oberfläche), LAZ", "las", "las", "laz", 1,
              "las_las", "lpolpg_32_{e}_{n}_1_rp.laz"),
    "bdom20rgbi": _p("bDOM RGBI – bildbasiertes DOM, eingefärbte Punktwolke, LAZ",
                     "bdom20rgbi", "las", "laz", 2, "bdom20rgbi_las", "bdom20rgbi_32_{e}_{n}_2_rp.laz"),
    "dgm1": _p("DGM1 – Digitales Geländemodell 1 m, GeoTIFF", "dgm1", "tif", "tif", 1, "dgm1_tif"),
    "dom1": _p("DOM1 – Digitales Oberflächenmodell 1 m, GeoTIFF", "dom1", "tif", "tif", 1, "dom1_tif"),
    # Luftbilder
    "dop20rgb": _p("DOP20 RGB – Orthophoto 20 cm, JPEG2000", "dop20rgb", "jp2", "jp2", 2, "dop20rgb_jp2"),
    "dop20rgbi": _p("DOP20 RGBI – Orthophoto 20 cm, 4-Kanal, JPEG2000",
                    "dop20rgbi", "jp2", "jp2", 2, "dop20rgbi_jp2"),
    # Gebäude
    "geb3dlo": _p("LoD2 – 3D-Gebäudemodelle, CityGML", "geb3dlo", "gml", "gml", 2,
                  "geb3dlo_gml", "LoD2_32_{e}_{n}_2_RP.gml"),
    "hu": _p("Hausumringe (ALKIS-Gebäudegrundrisse), Shapefile, ganz RLP",
             "hu", "zip", "zip", None, "hu_zip", art="land"),
    "hk": _p("Hauskoordinaten (amtliche Adressen mit Koordinate), CSV, ganz RLP",
             "hk", "zip", "zip", None, "hk_zip", art="land"),
    # Liegenschaftskataster (ALKIS)
    "bda": _p("ALKIS-Bestandsdatenauszug (NAS-XML) je Gemarkung",
              "bda", "xml", "zip", None, "bda_xml", art="gemarkung"),
    "lika": _p("Liegenschaftskarte, GeoTIFF 1-Bit, ~6 cm", "lika", "tif", "tif", 1,
               "lika_tif", "lika_0451_{e}_{n}.tif"),
    "bodensch": _p("Bodenschätzung (Karte), GeoTIFF, ~6 cm", "bodensch", "tif", "tif", 1,
                   "bodensch_tif", "bodensch_0451_{e}_{n}.tif"),
    "ln": _p("Landnutzung (ALKIS tatsächliche Nutzung), GeoPackage, ganz RLP",
             "ln", "zip", "zip", None, "ln_zip", art="land"),
    "lb": _p("Landbedeckung, GeoPackage, ganz RLP", "lb", "zip", "zip", None, "lb_zip", art="land"),
    # Karten
    "dtk5": _p("DTK5 – Topographische Karte 1:5.000, GeoTIFF 25 cm", "dtk5", "tif", "tif", 2,
               "dtk5_tif", "DTK5_{e}{n}.tif"),
    "dtk25": _p("DTK25 – Topographische Karte 1:25.000, Blätter (ZIP mit Ebenen-TIFFs)",
                "dtk25", "tif", "zip", None, "dtk25_tif", art="blatt"),
    "dtk50": _p("DTK50 – Topographische Karte 1:50.000, Blätter", "dtk50", "tif", "zip", None,
                "dtk50_tif", art="blatt"),
    "dtk100": _p("DTK100 – Topographische Karte 1:100.000, Blätter", "dtk100", "tif", "zip", None,
                 "dtk100_tif", art="blatt"),
    "p10": _p("basemap.de P10 – Rasterkarte, GeoTIFF 50 cm", "p10", "tif", "tif", 4,
              "p10_tif", "basemapde_p10_32{e}_{n}_4_de_col.tif"),
    "uek250utm": _p("ÜK250 – Übersichtskarte 1:250.000, GeoTIFF, ganz RLP",
                    "uek250utm", "zip", "zip", None, "uek250utm_zip", art="land"),
    # Landschaftsmodelle, Verzeichnisse, INSPIRE
    "basisdlm_shp": _p("Basis-DLM (ATKIS), Shapefile, ganz RLP", "basisdlm", "shp", "zip", None,
                       "basisdlm_shp", art="land"),
    "basisdlm_nas": _p("Basis-DLM (ATKIS), NAS-XML, ganz RLP", "basisdlm", "xml", "zip", None,
                       "basisdlm_xml", art="land"),
    "dlm50": _p("DLM50 (ATKIS), NAS-XML, ganz RLP", "dlm50", "xml", "zip", None, "dlm50_xml", art="land"),
    "wohnplatz": _p("Wohnplatzverzeichnis, CSV, ganz RLP", "wohnplatz", "zip", "zip", None,
                    "wohnplatz_zip", art="land"),
    "inspire-annexi": _p("INSPIRE Annex I (Verwaltungseinheiten, Flurstücke, Adressen, Gewässer, "
                         "Verkehr …), GML", "inspire-annexi", "xml", "zip", None,
                         "inspire-annexi_xml", art="land"),
    "inspire-annexii": _p("INSPIRE Annex II (Bodenbedeckung), GML", "inspire-annexii", "xml", "zip", None,
                          "inspire-annexii_xml", art="land"),
    "inspire-annexiii": _p("INSPIRE Annex III (Gebäude 2D, Bodennutzung, Boden), GML",
                           "inspire-annexiii", "xml", "zip", None, "inspire-annexiii_xml", art="land"),
}

# Kreisliste: zuerst die Kopie neben diesem Skript, sonst die Serverdatei.
KREISE_JSON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kreise_rlp.json")
if not os.path.exists(KREISE_JSON):
    KREISE_JSON = "/var/geodata/kreise_amtlich.json"


def die(msg: str) -> None:
    print(f"Fehler: {msg}", file=sys.stderr)
    sys.exit(1)


def product(key: str) -> dict:
    if key not in PRODUCTS:
        die(f"unbekanntes Produkt {key!r}. Bekannt: {', '.join(PRODUCTS)}")
    return PRODUCTS[key]


# --- HTTP ---------------------------------------------------------------------
def fetch(url: str, timeout: int = 120, rng: str | None = None) -> bytes:
    headers = dict(UA)
    if rng:
        headers["Range"] = rng
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        die(f"HTTP {e.code} für {url}")
    except Exception as e:  # noqa: BLE001
        die(f"{type(e).__name__} für {url}: {e}")


def head_ok(url: str, timeout: int = 25) -> tuple[bool, int]:
    """(existiert, groesse_bytes) via HEAD."""
    req = urllib.request.Request(url, headers=UA, method="HEAD")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return True, int(r.headers.get("Content-Length") or 0)
    except urllib.error.HTTPError:
        return False, 0
    except Exception:  # noqa: BLE001
        return False, 0


def cached(url: str, max_age_h: int = 24) -> bytes:
    """Metalink-Indizes lokal zwischenspeichern (sie sind groß und ändern sich selten)."""
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, re.sub(r"[^A-Za-z0-9._-]", "_", url))
    if os.path.exists(path) and (time.time() - os.path.getmtime(path)) < max_age_h * 3600:
        with open(path, "rb") as f:
            return f.read()
    data = fetch(url)
    with open(path, "wb") as f:
        f.write(data)
    return data


# --- Reprojektion -------------------------------------------------------------
def lonlat_to_utm32(lon: float, lat: float) -> tuple[float, float]:
    try:
        from osgeo import osr  # type: ignore

        src, dst = osr.SpatialReference(), osr.SpatialReference()
        src.ImportFromEPSG(4326)
        dst.ImportFromEPSG(25832)
        src.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
        dst.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
        x, y, _ = osr.CoordinateTransformation(src, dst).TransformPoint(lon, lat)
        return x, y
    except Exception:  # noqa: BLE001
        pass
    # Fallback: Transversale Mercator-Projektion, GRS80, Zone 32 (9°E), k0=0.9996
    a, f = 6378137.0, 1 / 298.257222101
    e2 = f * (2 - f)
    ep2 = e2 / (1 - e2)
    k0, lon0 = 0.9996, math.radians(9.0)
    p, l = math.radians(lat), math.radians(lon)
    N = a / math.sqrt(1 - e2 * math.sin(p) ** 2)
    T = math.tan(p) ** 2
    C = ep2 * math.cos(p) ** 2
    A = math.cos(p) * (l - lon0)
    M = a * (
        (1 - e2 / 4 - 3 * e2**2 / 64 - 5 * e2**3 / 256) * p
        - (3 * e2 / 8 + 3 * e2**2 / 32 + 45 * e2**3 / 1024) * math.sin(2 * p)
        + (15 * e2**2 / 256 + 45 * e2**3 / 1024) * math.sin(4 * p)
        - (35 * e2**3 / 3072) * math.sin(6 * p)
    )
    x = k0 * N * (A + (1 - T + C) * A**3 / 6
                  + (5 - 18 * T + T**2 + 72 * C - 58 * ep2) * A**5 / 120) + 500000.0
    y = k0 * (M + N * math.tan(p) * (A**2 / 2 + (5 - T + 9 * C + 4 * C**2) * A**4 / 24
              + (61 - 58 * T + T**2 + 600 * C - 330 * ep2) * A**6 / 720))
    return x, y


# --- Kachelmathematik ---------------------------------------------------------
def tiles_in_bbox(minx: float, miny: float, maxx: float, maxy: float, km: int):
    """SW-Ecken (in km) aller Kacheln, die die UTM32-Bbox berühren."""
    e0 = int(math.floor(minx / 1000 / km)) * km
    n0 = int(math.floor(miny / 1000 / km)) * km
    e1 = int(math.ceil(maxx / 1000 / km)) * km
    n1 = int(math.ceil(maxy / 1000 / km)) * km
    return [(e, n) for e in range(e0, e1, km) for n in range(n0, n1, km)]


# --- Metalink -----------------------------------------------------------------
FILE_RE = re.compile(
    r'<file name="([^"]+)">\s*<size>(\d+)</size>.*?<url>([^<]+)</url>', re.S
)
TILE_RE = re.compile(r"_32_(\d+)_(\d+)_\d_rp")


def parse_metalink(xml: bytes) -> list[tuple[str, int, str]]:
    """-> [(dateiname, groesse, url)]"""
    return [(m[0], int(m[1]), m[2]) for m in FILE_RE.findall(xml.decode("utf-8", "replace"))]


def meta4_url(pkey: str, ags: str) -> str:
    p = product(pkey)
    return f"{ROOT}/{p['dir']}/current/meta4/{p['meta4_prefix']}_{ags}.meta4"


def index_by_tile(pkey: str, ags: str = "07") -> dict[tuple[int, int], tuple[str, int, str]]:
    """Landesweiter (oder AGS-beschränkter) Index, nach Kachel-SW-Ecke geschlüsselt.

    Worldfiles (.tfw/.j2w) werden übersprungen — nur die eigentlichen Rasterdateien.
    """
    p = product(pkey)
    entries = parse_metalink(cached(meta4_url(pkey, ags)))
    out: dict[tuple[int, int], tuple[str, int, str]] = {}
    for name, size, url in entries:
        if not name.endswith("." + p["ext"]):
            continue
        m = TILE_RE.search(name)
        if m:
            out[(int(m[1]), int(m[2]))] = (name, size, url)
    return out


# --- Kommandos ----------------------------------------------------------------
def cmd_produkte(args) -> None:
    print(f"{'key':<18}{'Raster':<11}{'Format':<7}{'URL aus Kachel':<16}Titel")
    print("-" * 110)
    for k, p in PRODUCTS.items():
        raster = f"{p['km']} km" if p["km"] else p["art"]
        det = "ja" if p["direct"] else ("Index" if p["km"] else "-")
        print(f"{k:<18}{raster:<11}{p['ext']:<7}{det:<16}{p['title']}")


def cmd_ags(args) -> None:
    """AGS suchen: Kreisnamen lokal, alle gültigen Codes vom Server."""
    q = args.suchbegriff.lower()
    hits = []
    if os.path.exists(KREISE_JSON):
        import json

        with open(KREISE_JSON, encoding="utf-8") as f:
            for x in json.load(f):
                if x["ags"].startswith("07") and q in x["name"].lower():
                    hits.append((x["ags"], x["typ"], x["name"]))
    if hits:
        print("Kreise / kreisfreie Städte:")
        for ags, typ, name in sorted(hits):
            print(f"  {ags:<10}{typ:<20}{name}")
    else:
        print(f"Kein Kreis mit {args.suchbegriff!r} in {KREISE_JSON}.")
    print()
    print("Alle gültigen AGS-Codes (Gemeinde-Ebene) listen:")
    p = product(args.product)
    print(f'  curl -s "{ROOT}/{p["dir"]}/current/meta4/" | grep -oP \'(?<=href=")[^"]+\\.meta4\'')


def cmd_gebiet(args) -> None:
    p = product(args.product)
    url = meta4_url(args.product, args.ags)
    xml = fetch(url)
    entries = parse_metalink(xml)
    data = [e for e in entries if e[0].endswith("." + p["ext"])]
    # Manche Metalinks (hu, hk, uek250utm, basisdlm_shp, wohnplatz) führen alte
    # Versionen mit alter Prüfsumme unter derselben URL weiter. Dann zählt nur
    # die Datei, die wirklich auf dem Server liegt.
    urls = list(dict.fromkeys(u for _, _, u in data))
    veraltet = len(urls) < len(data)
    total = (sum(head_ok(u)[1] for u in urls) if veraltet else sum(s for _, s, _ in entries))
    print(f"# {p['title']}", file=sys.stderr)
    print(f"# AGS {args.ags}: {len(urls)} Datendateien, {total / 1024**3:.2f} GB", file=sys.stderr)
    print(f"# Metalink: {url}", file=sys.stderr)
    if veraltet:
        print("# Achtung: der Metalink enthält veraltete Einträge (alte Prüfsummen) – "
              "aria2c mit diesem Metalink kann an der Prüfsumme scheitern, besser die URL-Liste laden", file=sys.stderr)
    if args.meta4:
        if veraltet:
            die("Metalink nicht speicherbar (veraltete Einträge), ohne --meta4 die URL-Liste nehmen")
        with open(args.meta4, "wb") as f:
            f.write(xml)
        print(f"# geschrieben: {args.meta4}  ->  aria2c -i {args.meta4}", file=sys.stderr)
        return
    for u in urls:
        print(u)


def cmd_alkis(args) -> None:
    """ALKIS-Bestandsdatenauszug (NAS) einer Gemarkung. Die Dateien heißen
    bda_<Katasteramt>_<Gemarkungsnr. ohne 07>_<Name>.zip, z. B. bda_6600_3831_Alzey.zip."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from lod2_gebiet import finde_gemarkungen, zeige
    treffer = finde_gemarkungen(args.gemarkung)
    if len(treffer) != 1:
        zeige(treffer)
        die(f"{len(treffer)} Gemarkungen passen zu {args.gemarkung!r}, bitte die Nummer angeben")
    g = treffer[0]
    ordner = f"{ROOT}/bda/current/xml/"
    m = re.search(rf'href="(bda_\d+_{g["nr"][2:]}_[^"]+\.zip)"', cached(ordner).decode("utf-8", "replace"))
    if not m:
        die(f"keine bda-Datei für Gemarkung {g['name']} ({g['nr']})")
    ok, size = head_ok(ordner + m[1])
    print(f"# ALKIS-Bestandsdaten Gemarkung {g['name']} ({g['nr']}), Gemeinde {g['gemeinde']}"
          + (f", {size / 1024**2:.1f} MB" if ok else ""), file=sys.stderr)
    print(ordner + m[1])


def cmd_punkt(args) -> None:
    x, y = (args.lon, args.lat) if args.utm else lonlat_to_utm32(args.lon, args.lat)
    _emit(args, x, y, x, y)


def cmd_bbox(args) -> None:
    if args.utm:
        minx, miny, maxx, maxy = args.west, args.sued, args.ost, args.nord
    else:
        minx, miny = lonlat_to_utm32(args.west, args.sued)
        maxx, maxy = lonlat_to_utm32(args.ost, args.nord)
    _emit(args, minx, miny, maxx, maxy)


def _emit(args, minx, miny, maxx, maxy) -> None:
    pkey = args.product
    p = product(pkey)
    if not p["km"]:
        die(f"{pkey} hat kein Kachelraster ({p['art']}) – über 'gebiet <AGS>' laden"
            + (" oder 'alkis <Gemarkung>'" if p["art"] == "gemarkung" else ""))
    tiles = tiles_in_bbox(minx, miny, maxx, maxy, p["km"])
    print(f"# {p['title']}", file=sys.stderr)
    print(f"# UTM32-Bbox {minx:.0f},{miny:.0f},{maxx:.0f},{maxy:.0f} "
          f"-> {len(tiles)} Kachel(n) à {p['km']} km", file=sys.stderr)

    if p["direct"]:
        base = f"{ROOT}/{p['dir']}/current/{p['subdir']}/"
        found = 0
        for e, n in tiles:
            url = base + p["direct"].format(e=e, n=n)
            if args.pruefen:
                ok, size = head_ok(url)
                if not ok:
                    print(f"#   fehlt: {os.path.basename(url)}", file=sys.stderr)
                    continue
                found += 1
                print(f"#   {os.path.basename(url)}  {size / 1024**2:.1f} MB", file=sys.stderr)
            print(url)
        if args.pruefen:
            print(f"# {found}/{len(tiles)} vorhanden", file=sys.stderr)
    else:
        print(f"# Jahr im Dateinamen -> lade Landesindex ({p['meta4_prefix']}_07.meta4, "
              f"gecacht in {CACHE})", file=sys.stderr)
        idx = index_by_tile(pkey)
        total = 0
        for e, n in tiles:
            hit = idx.get((e, n))
            if not hit:
                print(f"#   keine Kachel für {e}/{n}", file=sys.stderr)
                continue
            name, size, url = hit
            total += size
            print(url)
        print(f"# Summe {total / 1024**2:.1f} MB", file=sys.stderr)


def cmd_info(args) -> None:
    """LAS/LAZ-Public-Header per Range-Request (512 Byte statt Vollabruf)."""
    d = fetch(args.url, rng="bytes=0-511")
    if d[:4] != b"LASF":
        die("keine LAS/LAZ-Datei (Signatur fehlt)")
    ver = (d[24], d[25])
    maxx, minx, maxy, miny, maxz, minz = struct.unpack_from("<6d", d, 179)
    n = (struct.unpack_from("<Q", d, 247)[0] if ver >= (1, 4)
         else struct.unpack_from("<I", d, 107)[0])
    print(f"LAS-Version : {ver[0]}.{ver[1]}")
    print(f"BBox EPSG:25832: {minx:.0f}, {miny:.0f}, {maxx:.0f}, {maxy:.0f}")
    print(f"Höhe        : {minz:.1f} – {maxz:.1f} m")
    print(f"Punkte      : {n:,}".replace(",", "."))


def main() -> None:
    ap = argparse.ArgumentParser(
        description="RLP-Open-Data-Downloads auflösen (geobasis-rlp.de)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Beispiele:
  rlp_dl.py produkte
  rlp_dl.py ags Altenkirchen
  rlp_dl.py gebiet 07132 -p dgm1 --meta4 ak.meta4
  rlp_dl.py gebiet 07 -p hu                      # Hausumringe ganz RLP
  rlp_dl.py alkis Alzey                          # ALKIS-NAS der Gemarkung Alzey
  rlp_dl.py punkt 7.5886 50.3569 -p dgm1
  rlp_dl.py bbox 7.55 50.33 7.62 50.38 -p las --pruefen > urls.txt
  rlp_dl.py info https://geobasis-rlp.de/data/las/current/las/lpolpg_32_368_5579_1_rp.laz

URLs gehen nach stdout, Diagnostik nach stderr — '> urls.txt' liefert also eine
saubere Liste für aria2c oder wget.""",
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add_product(sp):
        sp.add_argument("-p", "--product", default="las", choices=list(PRODUCTS))

    sub.add_parser("produkte", help="verfügbare Produkte auflisten").set_defaults(fn=cmd_produkte)

    s = sub.add_parser("ags", help="AGS zu einem Ortsnamen suchen")
    s.add_argument("suchbegriff")
    add_product(s)
    s.set_defaults(fn=cmd_ags)

    s = sub.add_parser("gebiet", help="alle Kacheln eines AGS-Gebiets")
    s.add_argument("ags")
    add_product(s)
    s.add_argument("--meta4", metavar="DATEI", help="Metalink speichern statt URLs auszugeben")
    s.set_defaults(fn=cmd_gebiet)

    s = sub.add_parser("alkis", help="ALKIS-Bestandsdaten (NAS) einer Gemarkung (Name oder Nummer)")
    s.add_argument("gemarkung")
    s.set_defaults(fn=cmd_alkis)

    s = sub.add_parser("punkt", help="Kachel an einem Punkt")
    s.add_argument("lon", type=float)
    s.add_argument("lat", type=float)
    add_product(s)
    s.add_argument("--utm", action="store_true", help="Eingabe ist EPSG:25832 statt lon/lat")
    s.add_argument("--pruefen", action="store_true", help="Existenz per HEAD prüfen")
    s.set_defaults(fn=cmd_punkt)

    s = sub.add_parser("bbox", help="alle Kacheln einer Bounding-Box")
    for n in ("west", "sued", "ost", "nord"):
        s.add_argument(n, type=float)
    add_product(s)
    s.add_argument("--utm", action="store_true", help="Eingabe ist EPSG:25832 statt lon/lat")
    s.add_argument("--pruefen", action="store_true", help="Existenz per HEAD prüfen")
    s.set_defaults(fn=cmd_bbox)

    s = sub.add_parser("info", help="LAS/LAZ-Header per Range-Request lesen")
    s.add_argument("url")
    s.set_defaults(fn=cmd_info)

    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
