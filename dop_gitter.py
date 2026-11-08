# -*- coding: utf-8 -*-
"""Luftbild (DOP20 RGBI) als vier Kanaele auf dem Gitter des DGM.

Die Kacheln liegen als JPEG2000 mit 20 cm; gebraucht wird der Ausschnitt in
der Rasterweite des DGM, damit Klassifikation und Hoehe Zelle fuer Zelle
zusammenpassen. Beim Herunterrechnen wird gemittelt, nicht gepickt - sonst
entscheidet ein einzelnes Pixel, ob eine 2-m-Zelle Wald ist.
"""
import os, glob, numpy as np

def _gdal():
    from osgeo import gdal
    gdal.UseExceptions()
    return gdal


def kacheln_fuer(muster, bbox, km=2):
    """Nur die Kacheln, die den Ausschnitt beruehren - ein VRT ueber alles
    waere hier wie beim DGM der teuerste Schritt."""
    from lib import areas
    xmin, ymin, xmax, ymax = bbox
    aus = []
    for m in muster:
        for f in glob.glob(os.path.expanduser(m)):
            c = areas.parse(f)
            if c is None:
                continue
            e, n = c[0] * 1000.0, c[1] * 1000.0
            if e < xmax and e + km * 1000 > xmin and n < ymax and n + km * 1000 > ymin:
                aus.append(f)
    return sorted(set(aus))


def laden(bbox, res, muster, cache_dir):
    """(4, ny, nx) uint8: R, G, B, NIR - oder None, wenn keine Kachel da ist.
    Liegt das Ergebnis schon im Cache, kommt es von dort."""
    tag = f"dop_{int(bbox[0])}_{int(bbox[1])}_{int(bbox[2] - bbox[0])}_{res}"
    pfad = os.path.join(cache_dir, tag + ".npy")
    if os.path.exists(pfad):
        return np.load(pfad)
    fs = kacheln_fuer(muster, bbox)
    if not fs:
        return None
    gdal = _gdal()
    os.makedirs(cache_dir, exist_ok=True)
    vrt = os.path.join(cache_dir, tag + ".vrt")
    gdal.BuildVRT(vrt, fs)
    ds = gdal.Warp("", vrt, format="MEM",
                   outputBounds=tuple(bbox), xRes=res, yRes=res,
                   resampleAlg="average")
    if ds is None:
        return None
    b = ds.ReadAsArray()                       # (bands, ny, nx)
    ds = None
    if b.ndim == 2:
        b = b[None]
    if b.shape[0] < 4:
        print(f"[!] Luftbild hat nur {b.shape[0]} Kanaele - kein Nahinfrarot, "
              f"die Klassifikation muss ueber Gruen raten")
    a = b.astype(np.uint8)
    np.save(pfad, a)
    return a
