---
name: rlp-opendata
description: Use this skill for any open geodata of Rheinland-Pfalz from the LVermGeo (geobasis-rlp.de) — finding, downloading, explaining or cutting it. Covers every product on the open data server — LiDAR (LAZ), DGM1/DOM1, DOP20 orthophotos, bDOM, LoD2 3D buildings (CityGML), ALKIS (Bestandsdaten NAS per Gemarkung, Liegenschaftskarte, Hausumringe, Hauskoordinaten, Landnutzung, ALKIS-WFS), Bodenschätzung, DTK5/25/50/100, basemap P10, ÜK250, Basis-DLM, DLM50, Wohnplatzverzeichnis, Landbedeckung and INSPIRE — plus tile numbers, Gemarkungen and the AdV key lists (Gebäudefunktion, Dachform). Triggers on "RLP Daten laden", "geobasis-rlp", "Kacheln runterladen", "LAZ/DGM1/DOP für <Ort>", "LoD2", "3D-Gebäude", "CityGML", "ALKIS", "Flurstücke", "Liegenschaftskarte", "Hausumringe", "Hauskoordinaten", "Gemarkung <Name>", "Gebäudefunktion 31001_1000", "zuschneiden auf <Gebiet>", "open data Rheinland-Pfalz".
---

# RLP Open Data (geobasis-rlp.de)

Alle offenen Geobasisdaten des Landesamts für Vermessung und Geobasisinformation
Rheinland-Pfalz (LVermGeo) liegen frei unter **https://geobasis-rlp.de/data/**.
Nur Rheinland-Pfalz; andere Länder haben eigene Server und Kachelnamen.

Lizenz: **Datenlizenz Deutschland Namensnennung 2.0** (`dl-de/by-2-0`).
Der Quellenvermerk ist **Pflicht**, bei jeder Weitergabe oder Veröffentlichung:

> © GeoBasis-DE / LVermGeo RLP (Jahr), dl-de/by-2-0

Koordinaten überall: **EPSG:25832** (ETRS89 / UTM Zone 32N), Höhen DHHN2016.

## Werkzeuge in diesem Ordner

Alle nur Python-Standardbibliothek (Python ≥ 3.9), kein venv nötig.
URLs und Ergebnisdateien gehen nach stdout, Meldungen nach stderr.

| Datei | Wofür |
|---|---|
| `rlp_dl.py` | Download-URLs für **jedes** Produkt: Punkt, Rechteck, Gemeindeschlüssel (AGS), ALKIS je Gemarkung |
| `lod2_gebiet.py` | LoD2-Gebäude auf Gemarkung, Gemeinde, Rechteck oder 1-km-Kacheln zuschneiden; AdV-Schlüssellisten als CSV |
| `rlp_mcp.py` | derselbe Katalog als **MCP-Server** (stdio) für Claude Desktop, OpenCode & Co. — zehn Werkzeuge inkl. `download`; Einrichtung in LIESMICH.md |
| `kreise_rlp.json` | Namen und AGS der 36 Kreise und kreisfreien Städte (für `rlp_dl.py ags`) |
| `dop_gitter.py`, `dop_klassen.py` | DOP20 auf ein Raster schneiden und klassifizieren (braucht GDAL + numpy) |

```bash
S=<pfad zu diesem ordner>      # z. B. ~/.claude/skills/rlp-opendata
python3 $S/rlp_dl.py produkte   # alle Produkte mit Raster und Format
```

## Alle Produkte

Ordner = `key` in `rlp_dl.py`. Aufbau immer `/data/<ordner>/current/<format>/<datei>`,
dazu `meta4/` (Metalinks) und meist `metadata/`.

### Gekachelt (Kachelnummer = Südwest-Ecke in km, Ost/Nord)

| key | Produkt | Format | Kachel | je Kachel | Dateiname |
|---|---|---|---|---|---|
| `las` | Laserpunkte Boden+Oberfläche | LAZ | 1 km | 90–320 MB | `lpolpg_32_{e}_{n}_1_rp.laz` |
| `bdom20rgbi` | bildbasiertes DOM, eingefärbte Punktwolke | LAZ | 2 km | ~290 MB | `bdom20rgbi_32_{e}_{n}_2_rp.laz` |
| `dgm1` | Geländemodell 1 m | GeoTIFF | 1 km | ~1,5 MB | `dgm1_32_{e}_{n}_1_rp_{jahr}.tif` |
| `dom1` | Oberflächenmodell 1 m | GeoTIFF | 1 km | ~3 MB | `dom1_32_{e}_{n}_1_rp_{jahr}.tif` |
| `dop20rgb` | Luftbild 20 cm RGB | JPEG2000 | 2 km | ~124 MB | `dop20rgb_32_{e}_{n}_2_rp_{jahr}.jp2` |
| `dop20rgbi` | Luftbild 20 cm RGB + Nahinfrarot | JPEG2000 | 2 km | ~171 MB | `dop20rgbi_32_{e}_{n}_2_rp_{jahr}.jp2` |
| `geb3dlo` | **LoD2** 3D-Gebäude | CityGML 1.0 | 2 km | 0,05–80 MB | `LoD2_32_{e}_{n}_2_RP.gml` |
| `lika` | Liegenschaftskarte (ALKIS) | GeoTIFF 1 Bit, ~6 cm | 1 km | 0,5–2 MB | `lika_0451_{e}_{n}.tif` |
| `bodensch` | Bodenschätzung (Karte) | GeoTIFF, ~6 cm | 1 km | 0,5–2,5 MB | `bodensch_0451_{e}_{n}.tif` |
| `dtk5` | Topographische Karte 1:5.000 | GeoTIFF 25 cm | 2 km | 2–3 MB | `DTK5_{e}{n}.tif` (z. B. `DTK5_4345510`) |
| `p10` | basemap.de Rasterkarte | GeoTIFF 50 cm | **4 km** | 9–47 MB | `basemapde_p10_32{e}_{n}_4_de_col.tif` |

- **2-km- und 4-km-Kacheln beginnen nur an geraden bzw. durch 4 teilbaren Kilometern.**
  Die 1-km-Kachel 435/5511 steckt in LoD2 `434_5510`, in P10 `432_5508`.
- **Mit Jahr im Namen** (DGM1, DOM1, DOP) ist die URL nicht berechenbar, das
  Befliegungsjahr wechselt je Kachel. `rlp_dl.py` liest dafür den Landesindex.
- LoD2 hat neben jeder `.gml` eine kleine `.txt` (Anzahl Gebäude, Aktualität, Ansprechpartner).

### Blattschnitt (keine Kachelnummer, Blattnummer)

| key | Produkt | Dateien |
|---|---|---|
| `dtk25` | DTK 1:25.000 | 194 Blätter `DTK25_5012.zip` (~5 MB, je Kartenebene ein TIFF + `_col` farbig) |
| `dtk50` | DTK 1:50.000 | 58 Blätter `DTK50_L5110.zip` |
| `dtk100` | DTK 1:100.000 | 19 Blätter `DTK100_C5110.zip` |

Laden über `rlp_dl.py gebiet <AGS> -p dtk25` (liefert die Blätter, die das Gebiet berühren).

### ALKIS je Gemarkung

| key | Produkt | Dateien |
|---|---|---|
| `bda` | ALKIS-Bestandsdatenauszug, NAS-XML (Flurstücke, Gebäude, Nutzung, Lagebezeichnungen …) | 3.111 ZIPs, eine je Gemarkung: `bda_<Katasteramt>_<Gemarkungsnr. ohne 07>_<Name>.zip`, z. B. `bda_6600_3831_Alzey.zip` (2–15 MB gepackt, bis ~65 MB XML) |

```bash
python3 $S/rlp_dl.py alkis Alzey          # oder die Nummer: alkis 073831
python3 $S/rlp_dl.py gebiet 07331 -p bda  # alle Gemarkungen eines Kreises
```

`bda`-Metalinks gibt es für RLP (`07`), Kreise (5 Stellen), Katasterämter
(`07` + 4 Stellen) und Verbandsgemeinden (7 Stellen), **nicht** für einzelne Gemeinden.

### Eine Datei für ganz RLP

| key | Produkt | Inhalt | Größe |
|---|---|---|---|
| `hu` | Hausumringe (ALKIS-Grundrisse) | Shapefile `gebaeude_hu.*` + Schlüsselliste | 319 MB (1,8 GB entpackt) |
| `hk` | Hauskoordinaten (Adressen) | CSV `HAUSKOORDINATEN_RP_hk.csv` + Schlüssel | 25 MB (206 MB) |
| `ln` | Landnutzung (ALKIS tatsächliche Nutzung) | GeoPackage `ln.gpkg` | 544 MB (1,5 GB) |
| `lb` | Landbedeckung | GeoPackage `lb_32_rp_<jahr>_01.gpkg` | 1,9 GB (6,2 GB) |
| `basisdlm_shp` / `basisdlm_nas` | Basis-DLM (ATKIS) | Shapefiles / NAS-XML | 336 MB / 523 MB |
| `dlm50` | DLM50 (ATKIS) | NAS-XML | 278 MB |
| `uek250utm` | Übersichtskarte 1:250.000 | GeoTIFF | 81 MB |
| `wohnplatz` | Wohnplatzverzeichnis | CSV | 0,4 MB |
| `inspire-annexi` | INSPIRE Annex I: Verwaltungseinheiten (`_au`), Flurstücke (`dlkm_cp`), Adressen (`dlkm_ad`), Namen (`_gn`), Gewässer (`_hy`), Verkehr (`_tn`) aus Basis-DLM, DLM50 und ALKIS (`dlkm`) | 28 GML-ZIPs | 2,3 GB |
| `inspire-annexii` | INSPIRE Bodenbedeckung (`dlkm_lc`) | GML | 891 MB (5,4 GB!) |
| `inspire-annexiii` | INSPIRE Gebäude 2D (`_bu-2d`), Bodennutzung (`dlkm_elu`), Boden (`dlkm_so`) | 4 GML-ZIPs | |

```bash
python3 $S/rlp_dl.py gebiet 07 -p hu > urls.txt
```

**Achtung:** Die Metalinks von `hu`, `hk`, `uek250utm`, `basisdlm_shp` und
`wohnplatz` führen alte Versionen mit alten Prüfsummen unter derselben URL
(Stand 2026-10-29). `rlp_dl.py` gibt dann jede URL nur einmal aus und
verweigert `--meta4`, sonst kann aria2c an der Prüfsumme scheitern.

## Gebiet wählen — `rlp_dl.py`

```bash
python3 $S/rlp_dl.py punkt 7.5886 50.3569 -p dgm1             # WGS84 lon lat
python3 $S/rlp_dl.py bbox 7.55 50.33 7.62 50.38 -p las > urls.txt
python3 $S/rlp_dl.py bbox 399000 5579000 401000 5581000 -p las --utm
python3 $S/rlp_dl.py ags Altenkirchen                         # AGS eines Kreises suchen
python3 $S/rlp_dl.py gebiet 07132 -p dgm1 --meta4 ak.meta4    # ganzes AGS-Gebiet
python3 $S/rlp_dl.py alkis Alzey                              # ALKIS-NAS einer Gemarkung
```

`--pruefen` macht pro Kachel einen HEAD-Request (Größe, fehlt?) – sinnvoll bei
Produkten mit berechneter URL.

Der **AGS** ist hierarchisch, und fast jedes Produkt hat Metalinks auf allen Ebenen:

| AGS-Länge | Ebene | Beispiel |
|---|---|---|
| 2 | ganz RLP | `07` |
| 5 | Kreis / kreisfreie Stadt | `07132` = LK Altenkirchen |
| 7 | Verbandsgemeinde | `0713101` |
| 8 | Gemeinde | `07111000` = Koblenz, `07331003` = Alzey |

Alle gültigen Codes eines Produkts listet der Server:

```bash
curl -s "https://geobasis-rlp.de/data/dgm1/current/meta4/" | grep -oP '(?<=href=")[^"]+\.meta4'
```

Das Skript meldet vorab Dateizahl und Gesamtgröße — **immer erst lesen, dann laden**.

### Herunterladen

```bash
aria2c -i ak.meta4 --dir=./dgm1_ak -j 8 --max-connection-per-server=4   # Metalink: parallel, SHA-256-geprüft
aria2c -i urls.txt --dir=./daten -j 8                                   # oder URL-Liste
wget -i urls.txt -P ./daten                                             # ohne aria2c
```

### Vorher reinschauen, ohne zu laden

LAZ-Header per Range-Request — 512 Byte statt mehrerer hundert MB:

```bash
python3 $S/rlp_dl.py info "https://geobasis-rlp.de/data/las/current/las/lpolpg_32_399_5579_1_rp.laz"
```
```
LAS-Version : 1.2
BBox EPSG:25832: 399000, 5579000, 400000, 5580000
Höhe        : 61.1 – 125.7 m
Punkte      : 14.192.971
```


## Gemarkungen, Gemeinden, Fluren — amtliche Grenzen (WFS)

Die Verwaltungsgrenzen gibt es als WFS (nicht auf `/data`):
`https://geo5.service24.rlp.de/wfs/verwaltungsgrenzen_rp.fcgi`
mit den Typen `vermkv:gemarkungen_rlp`, `fluren_rlp`, `gemeinde_rlp`,
`verbandsgemeinde_rlp`, `landkreise_rlp`, `vermka_rlp` (Katasterämter), `landesgrenze_rlp`.

```bash
W=https://geo5.service24.rlp.de/wfs/verwaltungsgrenzen_rp.fcgi
# eine Gemarkung nach Nummer (Filter nur exakt, Platzhalter gehen nicht):
curl "$W?SERVICE=WFS&VERSION=2.0.0&REQUEST=GetFeature&TYPENAMES=vermkv:gemarkungen_rlp&SRSNAME=EPSG:25832&FILTER=<Filter><PropertyIsEqualTo><PropertyName>gmkgnr</PropertyName><Literal>073831</Literal></PropertyIsEqualTo></Filter>"
```

(Den FILTER URL-kodieren.) Felder einer Gemarkung: `gmkgnr` (6-stellig, `07…`),
`gemarkung`, `gemeinde`, `gmdesch` (= AGS ohne `07`), `vbgmde`, `ldkreis`,
`kanr`/`katamt` (Katasteramt), `amtsgrcht`, `finanzamt`. In `gemeinde_rlp` ist
`ags` **10-stellig** (`0733100003`) — dort nach `gmdesch` filtern.

**Gemarkung ≠ Gemeinde.** Die Stadt Alzey hat vier Gemarkungen (Alzey,
Dautenheim, Heimersheim, Weinheim). Namenssuche über alle 3.111 Gemarkungen:

```bash
python3 $S/lod2_gebiet.py suche alzey
```

## ALKIS live abfragen (WFS)

`https://geo5.service24.rlp.de/wfs/alkis_rp.fcgi` mit `ave:Flurstueck`,
`ave:GebaeudeBauwerk`, `ave:Nutzung` — vereinfachtes ALKIS mit **Klartext**
(z. B. Gebäude `funktion` = „Durchfahrt im Gebäude“, `gmdschl`, `lagebeztxt`; Flurstück
`flstkennz`, `gemarkung`, `flur`, `flaeche`). Für kleine Gebiete per `BBOX`,
für ganze Gemarkungen besser `bda` laden.

```bash
curl "https://geo5.service24.rlp.de/wfs/alkis_rp.fcgi?SERVICE=WFS&VERSION=2.0.0&REQUEST=GetFeature&TYPENAMES=ave:Flurstueck&SRSNAME=EPSG:25832&BBOX=436500,5511000,436600,5511100,EPSG:25832"
```

## LoD2 — 3D-Gebäude zuschneiden (`lod2_gebiet.py`)

```bash
python3 $S/lod2_gebiet.py gemarkung Alzey --klartext --zip -o out/       # oder Nummer 073831
python3 $S/lod2_gebiet.py gemeinde 07331003 -o out/
python3 $S/lod2_gebiet.py bbox 435000 5510000 437000 5512000 -o out/      # UTM-Meter
python3 $S/lod2_gebiet.py kacheln 436/5511 4365510 435_5510 --einzeln --zusammen alle_3 -o out/
python3 $S/lod2_gebiet.py schluessel -o out/                              # AdV-Schlüssel als CSV
```

So arbeitet es, und das sollte man Empfängern so sagen:

- **Gebäude werden nie zerschnitten.** Ein Gebäude gehört zum Gebiet, wenn der
  Mittelpunkt seiner Grundfläche (`GroundSurface`) darin liegt. Randgebäude
  ragen deshalb etwas über die Grenze; jedes kommt genau einmal vor (nach `gml:id`).
- **Nachbarkacheln mitladen.** Gebäude auf einer Kachelgrenze stehen manchmal in
  der Nachbardatei, obwohl ihr Mittelpunkt ~1 m diesseits liegt. Das Skript lädt
  deshalb alle Kacheln bis 200 m um das Gebiet. Wer nur die „eigenen“ 2-km-Dateien
  nimmt, verliert solche Gebäude (bei 3 km² waren es 5).
- Kacheln werden temporär geladen und danach gelöscht; `--cache DIR` behält sie.
- Gebäude, Geometrie und Attribute bleiben **unverändert amtlich**. Neu sind nur
  `gml:name`, `gml:Envelope` im Kopf und, mit `--klartext`, zwei eigene Attribute
  `Gebaeudefunktion_Bezeichnung` und `Dachform_Bezeichnung`. Das Ergebnis ist eine
  Zusammenstellung amtlicher Daten, kein amtliches Produkt.

### Was in einem LoD2-Gebäude steht

| Element | Inhalt |
|---|---|
| `gml:id` | ALKIS-Objektkennung, z. B. `DERPLP150000PAjT` |
| `bldg:function` | Gebäudefunktion als AdV-Schlüssel, z. B. `31001_1000` |
| `bldg:roofType` | Dachform, z. B. `3100` |
| `bldg:measuredHeight` | Höhe in m |
| `bldg:storeysAboveGround` | Geschosse |
| `bldg:address` | Ort immer; Straße/Hausnummer nur, wo ALKIS eine Lagebezeichnung hat |
| `gen:stringAttribute` | `Gemeindeschluessel`, `Grundrissaktualitaet`, `DatenquelleLage/-Bodenhoehe/-Dachhoehe`, `Dachtyp_tdc` … |
| `bldg:consistsOfBuildingPart` | Gebäudeteile mit eigener Höhe/Dachform |

**Adressen fehlen bei vielen Gebäuden — das ist kein Fehler.** ALKIS hängt
Adressen an Hauptgebäude. Gemarkung Alzey: 44 % aller Gebäude haben Straße und
Hausnummer; Wohngebäude 83 %, Garagen 0,3 %, Überdachungen 0 %.

**Schlüssel** (vollständig: `lod2_gebiet.py schluessel`, Quelle AdV
`https://repository.gdi-de.org/schemas/adv/citygml/Codelisten/BuildingFunctionTypeAdV.xml`
und `RoofTypeTypeAdV.xml`):

| Gebäudefunktion | | Dachform | |
|---|---|---|---|
| `31001_1000` | Wohngebäude | `1000` | Flachdach |
| `31001_2000` | Gebäude für Wirtschaft oder Gewerbe | `2100` | Pultdach |
| `31001_2463` | Garage | `3100` | Satteldach |
| `31001_2523` | Umformer | `3200` | Walmdach |
| `31001_3021` | Allgemein bildende Schule | `3300` | Krüppelwalmdach |
| `51009_1610` | Überdachung | `3400` | Mansardendach |

Das Präfix sagt die ALKIS-Objektart: `31001` = Gebäude, `51009` = sonstiges Bauwerk.

**LoD1** (Klötzchenmodell: Grundriss auf eine Höhe hochgezogen, flaches Dach)
liegt nicht auf dem Open-Data-Server. Aus LoD2 lässt es sich ableiten
(`GroundSurface` + Höhe), ist dann aber kein amtliches LoD1.

## Größenordnungen — vorher rechnen

Echte Zahlen aus den Metalink-Indizes (2026-08-27), nicht geschätzt:

| Gebiet | Kacheln | LAZ (`las`) | DGM1 |
|---|---|---|---|
| 1 Kachel | 1 | 90–320 MB | ~1,5 MB |
| Koblenz Stadt (`07111000`) | 142 | 22,6 GB | 0,21 GB |
| LK Altenkirchen (`07132`) | 777 | 227 GB | 1,18 GB |
| ganz RLP (`07`) | 21.160 | ~5 TB | 30,8 GB |

**LAZ ist rund 190× größer als DGM1.** Nur nehmen, wenn wirklich 0,25 m Auflösung
oder die Punktklassifikation gebraucht wird — für Hillshade in Kartenmaßstäben
reicht DGM1 fast immer. Vor großen Läufen `df -h /var` prüfen.

## Häufige Fehler

| Problem | Ursache | Fix |
|---|---|---|
| HTTP 404 auf konstruierte DGM/DOP-URL | Befliegungsjahr fehlt im Namen | Index nutzen (`rlp_dl.py` macht das automatisch) |
| `keine Kachel für <e>/<n>` | Kachel liegt außerhalb RLP oder ist eine Lücke (Wasser) | normal, ignorieren |
| Kachelkoordinaten passen nicht | 2-km-Produkt mit 1-km-Raster gerechnet | `-p` korrekt setzen, das Skript kennt das Raster |
| Download bricht bei ~100 Kacheln ab | zu viele parallele Verbindungen | `aria2c -j 8 --max-connection-per-server=4` |
| Platte voll mitten im Lauf | LAZ unterschätzt | vorher Größe aus dem Skript lesen, `df -h` prüfen |
| Erster Aufruf pro Produkt langsam | Landesindex wird geladen (bis 12 MB) | gecacht in `~/.cache/rlp-opendata`, 24 h gültig |
| JP2 lässt sich nicht öffnen | OpenJPEG-Treiber fehlt | `gdalinfo --formats \| grep JP2` prüfen |
| LoD2-Auszug hat weniger Gebäude als erwartet | Randgebäude stehen in der Nachbarkachel | `lod2_gebiet.py` nutzen (lädt Nachbarn mit) |
| aria2c meldet Prüfsummenfehler bei `hu`/`hk`/… | veraltete Einträge im Server-Metalink | URL-Liste statt `--meta4` |
| WFS-Filter mit `PropertyIsLike` liefert nichts | Dienst kann nur exakte Filter | exakt filtern oder `lod2_gebiet.py suche` |

## Nur auf dem jh54-Server (für andere Rechner ignorieren)

Diese Teile setzen Dateien und Dienste voraus, die es nur auf Jonas' Server gibt:

- Hintergrund zum Kachel- und Metalink-Schema: `/var/geodata/rlp_opendata_lidar_tiles.md`
- hillsha.de-API für einen Punkt, alle Produkte mit Größe:
  `curl -s 'https://hillsha.de/api/offer?lon=7.5886&lat=50.3569'`
- `/var/www/opengeoDE` (Resolver für andere Bundesländer), `/var/www/hillsha.de`
- `/var/www/rlpkarte` (Downloadkarte, Kachelauswahl im Browser)

**LAZ → Hillshade → WMS-fertiges COG** macht `dl2hillshade.sh` in einem Rutsch:

```bash
python3 $S/rlp_dl.py bbox 7.55 50.33 7.62 50.38 -p las > /var/geodata/rlpdgm025_arbeiten/urls.txt
cd /var/geodata/rlpdgm025_arbeiten
./dl2hillshade.sh urls.txt mein_gebiet_hillshade.tif
```

Danach den **`wms-add-layer`-Skill** benutzen, um das Ergebnis in den WMS zu hängen.

**DGM1 → Hillshade direkt** (viel schneller als über LAZ, dafür nur 1 m statt 0,25 m):

```bash
python3 $S/rlp_dl.py gebiet 07132 -p dgm1 --meta4 ak.meta4
aria2c -i ak.meta4 --dir=./dgm -j 8
cd dgm && gdalbuildvrt dgm.vrt *.tif
gdaldem hillshade -z 1.5 -az 315 -alt 45 -compute_edges dgm.vrt hillshade.tif
```


## DOP20 anzapfen und auf ein Gitter schneiden

Erprobt im geokunst-Projekt (Rohzeichnung/Flur, September 2026, spaeter
gestrichen). Die beiden Bausteine liegen neben dieser Datei:
`dop_gitter.py` (Kacheln finden, Ausschnitt auf das DGM-Gitter warpen) und
`dop_klassen.py` (Wald/Offenland/Wasser/versiegelt daraus).

**Kacheln holen.** `dop20rgbi` (RGB + Nahinfrarot, JPEG2000, 2-km-Kacheln,
~170-190 MB je Kachel), Befliegungsjahr im Namen, also ueber den Index:

```
https://geobasis-rlp.de/data/dop20rgbi/current/jp2/dop20rgbi_32_{e}_{n}_2_rp_{jahr}.jp2
```

`e`,`n` sind die SW-Ecke in km, bei 2-km-Kacheln gerade Zahlen. Nur RGBI
nehmen - die RGB-Kacheln (`dop20rgb`) heissen gleich, haben aber keinen
vierten Kanal, und ohne NDVI bleibt von der Klassifikation nichts. GDAL braucht
`libgdal-jp2openjpeg` (`gdalinfo --formats | grep JP2`).

**Ausschneiden.** Nicht ein VRT ueber alles bauen, sondern nur die Kacheln,
die den Ausschnitt beruehren (`kacheln_fuer`), dann in einem Schritt auf
Ausschnitt und Zielraster:

```python
gdal.BuildVRT(vrt, kacheln)
ds = gdal.Warp("", vrt, format="MEM", outputBounds=bbox,
               xRes=res, yRes=res, resampleAlg="average")
b = ds.ReadAsArray()          # (4, ny, nx) uint8: R, G, B, NIR
```

`average`, nicht `near`: beim Herunterrechnen von 20 cm auf 2 m entscheidet
sonst ein einzelnes Pixel, ob eine Zelle Wald ist. Das Ergebnis als
`dop_<xmin>_<ymin>_<breite>_<res>.npy` cachen; das Warpen einer 4x4-km-Flaeche
dauert laenger als alles danach.

**Klassifizieren - was dabei gelernt wurde:**

- Wald ist im Nahinfrarot *hell*, nicht dunkel. Dunkel ist er im sichtbaren
  Licht (Median 77 gegen 130 im Offenland). Bewuchs ueber NDVI, Wald ueber
  die Helligkeit darin.
- Schwellen per Otsu aus der Szene, nicht fest: ein Sommer- und ein
  Maerzbild liegen im NDVI weit auseinander.
- Ein Wald ist kein Pixel. Je Zelle geschwellt zerfaellt er in Tausende
  Flecken; zaehlen muss der Anteil dunklen Bewuchses im Fenster (10-20 m).
- Versiegelt ist nicht "wenig Farbe, wenig Bewuchs" - das trifft auch Acker
  und Brache. Der Unterschied ist Textur: Standardabweichung der Helligkeit
  im 10-m-Fenster, Otsu darueber innerhalb der Kandidaten. Dann bleiben
  Doerfer, Strassen, Gewerbe, Steinbruch.
- Wasser: hell im Sichtbaren, dunkel im NIR, und flach (Hangneigung aus dem
  DGM). Wenig getestet.
