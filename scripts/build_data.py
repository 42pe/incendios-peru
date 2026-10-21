#!/usr/bin/env python3
"""
Build a small Peru-only hotspot GeoJSON from INPE Queimadas daily CSVs.

INPE publishes a daily "focos" CSV for all of South America, derived from the
same NASA/NOAA satellites SERFOR used (VIIRS, MODIS, NOAA, GOES). It is public,
needs no API key, and sends Access-Control-Allow-Origin: *.

We fetch the last N UTC days, keep only Peru rows, and emit a compact GeoJSON
plus a summary. A scheduled job runs this and publishes the output as a static
file, so end users only ever download the small Peru file from our CDN — never
hitting INPE themselves. That keeps the app infinitely scalable and $0 to serve.

Run:  python3 scripts/build_data.py [days]
Out:  public/data/peru.geojson, public/data/summary.json
"""
import csv
import io
import json
import math
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

BASE = ("https://dataserver-coids.inpe.br/queimadas/queimadas/focos/"
        "csv/diario/America_Sul")
DAYS = int(sys.argv[1]) if len(sys.argv) > 1 else 3
TIMEOUT = 90
REG_FIX = {"Lima Province": "Lima"}  # normalize region names
CORROB_KM = 5   # a GOES point counts only if a polar-orbiter detection is this close...
CORROB_H = 24   # ...and this close in time

# Peru bounding box, as a cheap sanity gate on top of the pais field.
LAT_MIN, LAT_MAX = -18.5, 0.5
LON_MIN, LON_MAX = -81.5, -68.5


def fetch(day):
    url = f"{BASE}/focos_diario_{day:%Y%m%d}.csv"
    req = urllib.request.Request(url, headers={"User-Agent": "IncendiosPeru/1.0"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read().decode("utf-8", errors="replace"), url


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def is_goes(f):
    return f["properties"]["sat"].startswith("GOES")


def parse_t(t):
    try:
        return datetime.strptime(t, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def corroborate_goes(features):
    """Mark GOES detections that a polar orbiter (VIIRS/MODIS/METOP) confirms.

    GOES has ~2 km pixels and, over Peru's coastal desert at midday, flags hot
    bare ground as fire (e.g. 286 of 298 Piura detections on 19-20 Oct, none
    confirmed). A GOES point gets "c": 1 only if a non-GOES detection lies
    within CORROB_KM and CORROB_H. The page only ever shows confirmed GOES.
    """
    polar = []
    for f in features:
        if not is_goes(f):
            lon, lat = f["geometry"]["coordinates"]
            polar.append((lon, lat, parse_t(f["properties"]["t"])))
    # bucket polar points on a ~0.1° grid so each lookup checks a few cells
    grid = {}
    for p in polar:
        grid.setdefault((int(p[0] * 10 // 1), int(p[1] * 10 // 1)), []).append(p)

    total = ok = 0
    for f in features:
        if not is_goes(f):
            continue
        total += 1
        lon, lat = f["geometry"]["coordinates"]
        t = parse_t(f["properties"]["t"])
        kx = math.cos(math.radians(lat)) * 111.0
        gx, gy = int(lon * 10 // 1), int(lat * 10 // 1)
        hit = False
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for plon, plat, pt in grid.get((gx + dx, gy + dy), ()):
                    if math.hypot((plon - lon) * kx, (plat - lat) * 111.0) > CORROB_KM:
                        continue
                    if t and pt and abs((t - pt).total_seconds()) > CORROB_H * 3600:
                        continue
                    hit = True
                    break
                if hit:
                    break
            if hit:
                break
        if hit:
            f["properties"]["c"] = 1
            ok += 1
    return total, ok


def main():
    now = datetime.now(timezone.utc)
    days = [now - timedelta(days=i) for i in range(DAYS)]

    features = []
    seen = set()
    sources = []
    for d in days:
        try:
            text, url = fetch(d)
        except Exception as e:  # a missing day is not fatal
            sources.append({"day": d.strftime("%Y%m%d"), "ok": False, "error": str(e)})
            continue
        rows = 0
        for row in csv.DictReader(io.StringIO(text)):
            if (row.get("pais") or "").strip().lower() != "peru":
                continue
            lat, lon = num(row.get("lat")), num(row.get("lon"))
            if lat is None or lon is None:
                continue
            if not (LAT_MIN <= lat <= LAT_MAX and LON_MIN <= lon <= LON_MAX):
                continue
            fid = row.get("id") or f"{lat},{lon},{row.get('data_hora_gmt')}"
            if fid in seen:
                continue
            seen.add(fid)
            rows += 1
            features.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [round(lon, 5), round(lat, 5)]},
                "properties": {
                    "t": (row.get("data_hora_gmt") or "").strip(),  # UTC
                    "sat": (row.get("satelite") or "").strip(),
                    "reg": REG_FIX.get((row.get("estado") or "").strip(), (row.get("estado") or "").strip()),
                    "mun": (row.get("municipio") or "").strip(),
                    "frp": num(row.get("frp")),
                    "biome": (row.get("bioma") or "").strip(),
                },
            })
        sources.append({"day": d.strftime("%Y%m%d"), "ok": True, "peru_rows": rows})

    features.sort(key=lambda f: f["properties"]["t"], reverse=True)
    goes_total, goes_ok = corroborate_goes(features)

    # Counts match the page's default view: polar-orbiter detections only.
    by_region = {}
    for f in features:
        if is_goes(f):
            continue
        by_region[f["properties"]["reg"] or "Sin region"] = \
            by_region.get(f["properties"]["reg"] or "Sin region", 0) + 1

    fc = {
        "type": "FeatureCollection",
        "generated": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "features": features,
    }
    summary = {
        "generated": fc["generated"],
        "days": DAYS,
        "total": len(features),
        "by_region": dict(sorted(by_region.items(), key=lambda kv: -kv[1])),
        "goes": {"total": goes_total, "corroborated": goes_ok},
        "sources": sources,
    }

    with open("public/data/peru.geojson", "w") as fh:
        json.dump(fc, fh, separators=(",", ":"))
    with open("public/data/summary.json", "w") as fh:
        json.dump(summary, fh, indent=2)

    print(f"Wrote {len(features)} Peru hotspots over {DAYS} day(s).")
    print(json.dumps(summary["by_region"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
