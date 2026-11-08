# -*- coding: utf-8 -*-
"""Grobe Landbedeckung aus Luftbild und Gelaende: Wald, Offenland,
versiegelt, Wasser.

Kein Lernverfahren, sondern Schwellen - fuer eine Zeichnung, die hinterher
von Hand ausgemalt wird, reicht das, und man versteht, warum eine Flaeche
so klassifiziert wurde. Der NDVI trennt Bewuchs von allem anderen; ob der
Bewuchs Wald ist, sagt das Oberflaechenmodell (wo es eins gibt) oder die
Dunkelheit im Nahinfrarot. Wasser ist dunkel, flach und ohne Bewuchs;
versiegelt ist hell, grau und ohne Bewuchs.

Danach wird morphologisch aufgeraeumt, bis keine Fitzel mehr bleiben: die
Zeichnung soll wenige, ruhige Umrisse haben, keine Rasterkanten.
"""
import numpy as np
from scipy import ndimage

KLASSEN = ("wasser", "versiegelt", "wald", "offen")   # Vorrang von links nach rechts


def merkmale(dop, dgm, res):
    d = dop.astype(np.float32)
    r, g, b = d[0], d[1], d[2]
    nir = d[3] if d.shape[0] >= 4 else None
    hell = (r + g + b) / 3.0
    # Saettigung nach HSV, ohne den Umweg ueber HSV: Spannweite zu Maximum
    mx = np.maximum(np.maximum(r, g), b)
    mn = np.minimum(np.minimum(r, g), b)
    satt = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1.0), 0.0)
    if nir is not None:
        ndvi = (nir - r) / np.maximum(nir + r, 1.0)
    else:
        # Ersatz ohne Nahinfrarot: Gruenueberschuss, auf -1..1 gebracht
        ndvi = (2 * g - r - b) / np.maximum(2 * g + r + b, 1.0)
    z = dgm.astype(np.float32)
    zf = np.where(np.isfinite(z), z, np.nanmean(z))
    gy, gx = np.gradient(ndimage.gaussian_filter(zf, 1.0), res)
    neigung = np.rad2deg(np.arctan(np.hypot(gy, gx)))
    return dict(ndvi=ndvi, hell=hell, satt=satt, neigung=neigung, nir=nir)


def _aufraeumen(m, res, min_m2, radius_m):
    """Oeffnen, schliessen, Kleinstflaechen und -loecher weg."""
    r = max(int(round(radius_m / res)), 1)
    k = np.zeros((2 * r + 1, 2 * r + 1), bool)
    yy, xx = np.ogrid[-r:r + 1, -r:r + 1]
    k[yy * yy + xx * xx <= r * r] = True
    m = ndimage.binary_opening(m, k)
    m = ndimage.binary_closing(m, k)
    min_px = max(int(min_m2 / (res * res)), 1)
    lab, n = ndimage.label(m)
    if n:
        gr = ndimage.sum(m, lab, range(1, n + 1))
        weg = np.isin(lab, np.nonzero(np.asarray(gr) < min_px)[0] + 1)
        m = m & ~weg
    lab, n = ndimage.label(~m)
    if n:
        gr = ndimage.sum(~m, lab, range(1, n + 1))
        loch = np.isin(lab, np.nonzero(np.asarray(gr) < min_px)[0] + 1)
        m = m | loch
    return m


def klassifizieren(dop, dgm, res, p, ndsm=None):
    """p: Schwellen aus config.py (V_ROH_*). ndsm: Hoehe ueber Grund, falls
    ein Oberflaechenmodell da ist - dann entscheidet es ueber Wald."""
    from skimage.filters import threshold_otsu
    M = merkmale(dop, dgm, res)
    ndvi, hell, satt, neig = M["ndvi"], M["hell"], M["satt"], M["neigung"]
    # Schwellen unter null heissen: aus der Szene selbst nehmen (Otsu). Ein
    # Sommerbild und ein Maerzbild liegen im NDVI weit auseinander; eine feste
    # Zahl passt nie fuer beide.
    t_bew = p["bewuchs_ndvi"] if p["bewuchs_ndvi"] >= 0 else float(threshold_otsu(ndvi))
    bewuchs = ndvi > t_bew
    # Ein Wald ist kein Pixel. Bei 2 m Zellen wechseln sich Kronen und
    # Schattenluecken ab, und eine Schwelle je Zelle zerlegt ihn in
    # Tausende Flecken, die das Aufraeumen dann frisst. Darum wird der
    # Anteil im Fenster genommen: Wald ist, wo die Mehrheit dunkler
    # Bewuchs ist. Dasselbe fuer Siedlung: ein Dorf ist ein Gemisch aus
    # Daechern, Strassen und Gaerten, nicht eine Reihe grauer Zellen.
    fenster = max(p["glatt_radius"] / res, 1.0)
    anteil = lambda m: ndimage.uniform_filter(m.astype(np.float32), int(2 * fenster + 1))
    if ndsm is not None:
        wald_zelle = bewuchs & (ndsm > p["wald_hoehe"])
    else:
        # Ohne Oberflaechenmodell: Wald ist der im Sichtbaren dunklere
        # Bewuchs. Nicht das Nahinfrarot - dort ist Wald hell, nicht dunkel.
        t_w = p["wald_dunkel"] if p["wald_dunkel"] >= 0 else \
            float(threshold_otsu(hell[bewuchs])) if bewuchs.any() else 0.0
        wald_zelle = bewuchs & (hell < t_w)
    wald = anteil(wald_zelle) > 0.5
    wasser = (~bewuchs) & (hell < p["wasser_hell"]) & (neig < p["wasser_neigung"])
    # Was weder waechst noch Wasser ist und wenig Farbe hat: Dach, Strasse,
    # Hof. Helle wie dunkle Daecher, darum keine Helligkeitsschwelle.
    versiegelt_zelle = (~bewuchs) & (~wasser) & (satt < p["versiegelt_satt"])
    if p.get("textur", True) and versiegelt_zelle.any():
        # Ein Acker hat auch wenig Farbe und wenig Bewuchs - aber er ist glatt.
        # Ein Dorf wechselt auf zehn Metern zwischen Dach, Hof und Strasse.
        # Die Textur trennt beides; ohne sie waren 18% der Flaeche Siedlung,
        # darunter Brachen und die Kaeferflaechen im Wald. Mit ihr 9%.
        w = max(int(round(10.0 / res)), 3)
        tex = np.sqrt(np.maximum(ndimage.uniform_filter(hell * hell, w)
                                 - ndimage.uniform_filter(hell, w) ** 2, 0))
        rau = tex >= float(threshold_otsu(tex[versiegelt_zelle]))
        versiegelt_zelle = versiegelt_zelle & rau
    versiegelt = anteil(versiegelt_zelle) > 0.35
    masken = {"wasser": wasser, "versiegelt": versiegelt, "wald": wald}
    for k in masken:
        masken[k] = _aufraeumen(masken[k], res, p["min_flaeche"], p["glatt_radius"])
    # Vorrang aufloesen, dann bleibt Offenland als Rest
    belegt = np.zeros(dgm.shape, bool)
    for k in ("wasser", "versiegelt", "wald"):
        masken[k] &= ~belegt
        belegt |= masken[k]
    masken["offen"] = ~belegt
    masken["versiegelt_zelle"] = versiegelt_zelle     # roh, fuer die Wege
    return masken


def spuren(maske, res, min_laenge_m):
    """Duenne, lange Strukturen einer Maske als Polylinien: Skelett bilden
    und abgehen. Was zwischen zwei Endpunkten oder Kreuzungen liegt, ist eine
    Spur; kurze fliegen raus. So werden aus versiegelten Zellen Strassen und
    aus Vertiefungen im Relief Hohlwege - ohne dass Daecher oder Kuhlen
    mitkommen, denn die sind breit und kurz."""
    from skimage.morphology import skeletonize
    sk = skeletonize(maske)
    if not sk.any():
        return []
    k = np.ones((3, 3), int); k[1, 1] = 0
    n = ndimage.convolve(sk.astype(int), k, mode="constant")
    knoten = sk & (n != 2)                      # Endpunkte und Kreuzungen
    besucht = np.zeros(sk.shape, bool)
    ny, nx = sk.shape
    nb = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
    aus = []

    def gehe(y, x):
        pts = [(y, x)]
        besucht[y, x] = True
        while True:
            weiter = None
            for dy, dx in nb:
                yy, xx = y + dy, x + dx
                if 0 <= yy < ny and 0 <= xx < nx and sk[yy, xx] and not besucht[yy, xx]:
                    weiter = (yy, xx)
                    if knoten[yy, xx]:
                        break
            if weiter is None:
                break
            y, x = weiter
            pts.append((y, x)); besucht[y, x] = True
            if knoten[y, x]:
                break
        return pts

    starts = list(zip(*np.nonzero(knoten)))
    for y, x in starts:
        besucht[y, x] = False           # Knoten duerfen von mehreren Spuren aus betreten werden
    for y, x in starts:
        for dy, dx in nb:
            yy, xx = y + dy, x + dx
            if 0 <= yy < ny and 0 <= xx < nx and sk[yy, xx] and not besucht[yy, xx] and not knoten[yy, xx]:
                pts = [(y, x)] + gehe(yy, xx)
                aus.append(pts)
    # Ringe ohne Knoten
    for y, x in zip(*np.nonzero(sk & ~besucht & ~knoten)):
        if not besucht[y, x]:
            aus.append(gehe(y, x))
    min_px = min_laenge_m / res
    aus = [np.array(p_, np.float32) for p_ in aus
           if np.sum(np.hypot(*np.diff(np.array(p_, float), axis=0).T)) >= min_px]
    return aus


def umrisse(maske, min_len_zellen=8.0):
    """Konturen einer Maske als Polylinien in Gitterkoordinaten (zeile, spalte).
    Ueber die Isolinie bei 0.5 einer leicht geglaetteten Maske - so entstehen
    runde Kanten statt Treppen."""
    from lib import vector as V
    f = ndimage.gaussian_filter(maske.astype(np.float32), 1.0)
    return [c for _, c in V.isolines(f, [0.5], 0.0, min_len=min_len_zellen)]
