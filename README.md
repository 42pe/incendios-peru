# Monitor de Incendios Forestales — Perú

Mapa independiente de **focos de calor activos en el Perú**, construido mientras la
plataforma oficial de **SERFOR** (módulo SAMI) permanece inaccesible (desde el
14 oct 2026).

> **No es una fuente oficial.** Un *foco de calor* es una detección satelital de
> una anomalía térmica: un indicio, no un incendio confirmado. Ante una
> emergencia, comunícate con el **INDECI (línea 115)**.

## Metodología

### 1. Fuente de datos

- **[INPE Queimadas](https://terrabrasilis.dpi.inpe.br/queimadas/portal/)**
  (Instituto Nacional de Pesquisas Espaciais, Brasil) publica un CSV diario con
  todos los focos de calor de Sudamérica. Es público, no requiere clave y
  etiqueta cada detección con país, región y municipio.
- Los satélites son los mismos que usaba SERFOR: **VIIRS** (Suomi-NPP, NOAA-20,
  NOAA-21), **MODIS** (Aqua, Terra), **METOP** y **GOES**, vía NASA/NOAA.
- INPE solo agrega y normaliza; las detecciones las producen NASA/NOAA.

### 2. Procesamiento ([`scripts/build_data.py`](scripts/build_data.py))

1. Cada 30 min, una tarea de GitHub Actions descarga los CSV de los **últimos
   3 días UTC** (el día en curso más los dos anteriores); es lo que muestra la pestaña **Historial**.
2. Conserva solo las filas con `pais = Peru` que además caen dentro de la caja
   geográfica del Perú.
3. Elimina filas duplicadas por `id`.
4. Unifica nombres de región inconsistentes (p. ej. "Lima Province" → "Lima").
5. Publica `public/data/peru.geojson` como archivo estático.

Como el corte es a medianoche UTC, el archivo cubre entre ~48 y ~72 h según la
hora del día. La página muestra el rango real ("detecciones del … al …") en
lugar de un número fijo.

### 3. Cómo contamos: focos distintos (~1 km)

Varios satélites detectan el mismo punto. Por ejemplo, NPP, NOAA-20 y NOAA-21
pasan con minutos de diferencia y registran el mismo fuego. Si sumáramos
detecciones crudas, el número inflaría la realidad (en una muestra del 21 oct:
335 detecciones correspondían a 199 lugares distintos).

Por eso:

- **La cifra principal es de *focos distintos (~1 km)*.** Agrupamos las
  detecciones en celdas de 0,01° (~1,1 km) y contamos celdas.
- **Debajo mostramos las detecciones satelitales crudas** como referencia.
- **Cada celda cuenta en una sola región**, así que la suma de la lista "Por
  región" coincide con la cifra principal.
- **Es un mínimo, no un conteo de incendios.** Un incendio grande ocupa varias
  celdas, y dos fuegos vecinos pueden caer en la misma celda.

### 4. GOES desactivado por defecto

GOES es geoestacionario: observa cada ~10 min con píxeles de ~2 km. Repite el
mismo punto muchas veces y es más propenso a falsos positivos. Entre el 19 y el
20 oct, 286 de los 298 focos de Piura eran detecciones GOES, lo que la ponía
primera en el ranking. Sin GOES, Piura no aparecía entre las 6 primeras.

Por eso GOES está **oculto por defecto** y se puede activar con una casilla.
Hay una contrapartida: un incendio visto solo por GOES entre dos pasadas de
VIIRS/MODIS no aparece en la vista por defecto hasta la siguiente pasada.

### 5. Ventanas de tiempo y estados vacíos

- **24 h / 48 h / Historial** se calculan respecto a la hora actual del
  visitante. La página explica cada pestaña bajo los botones:
  - **24 h:** lo más cercano a "activo ahora", sin confirmar que siga encendido.
  - **48 h:** incluye focos que pueden haberse apagado.
  - **Historial:** todo el archivo (~48–72 h). Es un historial, no incendios activos.
- **Los puntos se desvanecen con la antigüedad** (más transparente = detección
  más antigua), para no confundir historial con actividad actual.
- **Que un foco no vuelva a detectarse no significa que se apagó.** Entre
  pasadas no hay observación, y nubes, humo o fuego bajo el dosel pueden
  ocultarlo. Solo la confirmación en terreno lo asegura.
- Los satélites VIIRS y MODIS pasan sobre el Perú **unas dos veces al día**
  (aprox. 13:30 y 01:30 hora local), y INPE publica con 1–3 h de retraso.
  Puede haber horas sin detecciones nuevas aunque todo funcione bien.
- **Datos desactualizados:** si el archivo tiene más de 2 h sin regenerarse,
  la página muestra un aviso (problema del proceso o de la fuente).
- **Periodo sin detecciones:** si los datos están al día pero no hay focos en
  la ventana elegida, la página indica hace cuánto fue la última detección, para
  que no se confunda con "no hay incendios".

### 6. Intensidad (color)

El color y el tamaño de cada punto reflejan el **FRP** (potencia radiativa del
fuego, en MW). El FRP **no es directamente comparable entre sensores** con
distinto tamaño de píxel.

### 7. Limitaciones

- No hay confirmación en terreno: un foco es un indicio.
- **No filtramos fuentes de calor fijas**, como volcanes (Sabancaya, Ubinas) o
  la quema de gas industrial (Talara, La Pampilla). Preferimos advertirlo antes
  que filtrarlas, porque un filtro podría ocultar un incendio real cercano.
- Nubes, humo denso o el horario de pasada pueden ocultar focos reales.
- Las cifras pueden no coincidir con SENAMHI o SERFOR. No conocemos
  públicamente su método exacto de conteo (satélite de referencia o
  deduplicación), así que no afirmamos equivalencia.

### 8. Diferencias con la plataforma de SERFOR

| Función | Este mapa | SERFOR |
|---|---|---|
| Focos de calor satelitales (VIIRS, MODIS, NOAA, GOES) | Sí | Sí |
| Confirmación en terreno (COEN, bomberos, GORE) | No | Sí |
| Validación con imágenes satelitales | No | Sí (según reportes regionales) |
| Reporte de cicatriz / área quemada | No | Sí (según reportes regionales) |
| Alertas oficiales a autoridades | No | Sí |
| Eliminación de fuentes fijas (volcanes, industrias) | No | Sí |
| Actualización | cada 30 min | reporte diario |

Fuentes sobre SERFOR: [Andina](https://andina.pe/agencia/noticia-con-ayuda-del-satelite-serfor-intensifica-monitoreo-para-prevenir-incendios-forestales-993227.aspx),
[SINIA – reporte Amazonas](https://sinia.minam.gob.pe/sites/default/files/archivos/public/docs/ANEXO%2001.%20REPORTE%20DE%20INCENDIOS_AMAZONAS.pdf).

## Arquitectura

Todo es estático: los visitantes solo descargan archivos pequeños desde la CDN,
nunca consultan a INPE. Así el costo es ~$0 aunque haya mucho tráfico.

```
INPE Queimadas CSV ──(cada 30 min, GitHub Actions)──► scripts/build_data.py
                                                          │ filtra Perú
                                                          ▼
                                        public/data/peru.geojson
public/data/basemap-peru.pmtiles (mapa base OSM/Protomaps, autoalojado)
public/index.html (MapLibre GL + pmtiles)
                         visitantes ◄── Cloudflare CDN ◄──┘
```

| Ruta | Función |
|---|---|
| `public/index.html` | Toda la app: mapa, panel, conteo, modal "¿Cómo funciona?". |
| `public/data/peru.geojson` | Focos de calor, regenerados por el cron. No editar a mano. |
| `public/data/basemap-peru.pmtiles` | Mapa base del Perú (zoom 0–10). El mapa se limita a zoom 8,9 porque los niveles 9–10 del extracto actual tienen artefactos en polígonos de agua. |
| `scripts/build_data.py` | Descarga INPE, filtra Perú, escribe `public/data/`. |
| `.github/workflows/refresh-data.yml` | Cron cada 30 min; hace commit si los datos cambian. |
| `src/worker.js` | Worker de Cloudflare que responde peticiones HTTP Range (206) para el `.pmtiles`. |

## Desarrollo local

```bash
python3 scripts/build_data.py 3   # actualiza public/data/
npx wrangler dev                  # sirve public/ igual que Cloudflare (con Range)
```

`python3 -m http.server` no soporta peticiones Range, así que el mapa base no
carga con él.

## Despliegue

Cloudflare Workers con assets estáticos (`wrangler.jsonc`):

```bash
npx wrangler deploy
```

Cada push del cron de datos vuelve a desplegar automáticamente.

## Atribución

Focos: INPE Queimadas · NASA/NOAA. Mapa base: © OpenStreetMap ·
[Protomaps](https://protomaps.com).
