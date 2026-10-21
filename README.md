# Monitor de Incendios Forestales — Perú

Independent, static rebuild of Peru's active-fire ("focos de calor") map, built
while **SERFOR's official platform has been inaccessible since 14 Oct 2026**.

It is **not an official source**. A *foco de calor* is a satellite thermal
detection — an indication, not a confirmed fire.

## How it works

- **Data:** [INPE Queimadas](https://terrabrasilis.dpi.inpe.br/queimadas/portal/)
  daily South America CSV, derived from the same NASA/NOAA satellites SERFOR used
  (VIIRS, MODIS, NOAA, GOES via NASA/LANCE). Public, no API key, CORS-open.
- **Pipeline:** `scripts/build_data.py` fetches the last N UTC days, keeps only
  Peru rows (by `pais` field + bounding box), and writes a compact
  `data/peru.geojson` (~350 KB) plus `data/summary.json`.
- **App:** `index.html` — a single static page (Leaflet) that loads
  `data/peru.geojson` from the same origin. No backend, no key, no database.

## Why it scales to zero cost

End users only ever download a small static file from the CDN. They never hit
INPE. The one moving part is a scheduled job (`.github/workflows/refresh-data.yml`)
that rebuilds the data every 30 min — a free cron, not a server.

```
INPE (once per refresh)  ->  build_data.py (GitHub Actions cron)  ->  peru.geojson
                                                                         |
                                       many users  <----  CDN  <---------+
```

## Run locally

```bash
python3 scripts/build_data.py 3     # writes data/peru.geojson
python3 -m http.server 8787         # open http://localhost:8787
```

## Deploy

Any static host. Recommended: **Cloudflare Pages** (unlimited free bandwidth)
connected to this repo — the Action commits fresh data, Pages redeploys on push.

### Open decisions
- **Basemap tiles.** Map data is free; tiles are not. v1 uses Esri's no-key gray
  canvas. For high traffic, use a domain-restricted free-tier key (MapTiler /
  Stadia, ~100k loads/mo free) so tiles don't rate-limit.
- **Deferred (see notes):** SERFOR's ground-confirmation / burn-scar layer
  (not a data feed) and GEOSERFOR's own WMS layers.
