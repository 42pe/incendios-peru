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
Out:  data/peru.geojson, data/summary.json
"""
import csv
import io
import json
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

BASE = ("https://dataserver-coids.inpe.br/queimadas/queimadas/focos/"
        "csv/diario/America_Sul")
DAYS = int(sys.argv[1]) if len(sys.argv) > 1 else 2
TIMEOUT = 90

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
                    "reg": (row.get("estado") or "").strip(),
                    "mun": (row.get("municipio") or "").strip(),
                    "frp": num(row.get("frp")),
                    "biome": (row.get("bioma") or "").strip(),
                },
            })
        sources.append({"day": d.strftime("%Y%m%d"), "ok": True, "peru_rows": rows})

    features.sort(key=lambda f: f["properties"]["t"], reverse=True)

    by_region = {}
    for f in features:
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
