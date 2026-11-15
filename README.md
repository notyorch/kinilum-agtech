# kinilum

*Resumen en español: kinilum compara rotaciones de cultivo para una parcela antes de sembrar, con datos satelitales de la NASA, y muestra el rango de resultados en vez de una sola cifra. Apoya la decisión; no la toma. 

**kinilum** is a decision-support tool for NASA Space Apps 2026, challenge *Field Shift: Adapting Farms with NASA Data*. It compares crop rotations for a plot before planting, using NASA Earth observations, local data and the farmer's priorities, and it shows a range of outcomes instead of a single number.

The case study is **irrigated maize in Guasave, Sinaloa**, where reservoir water is the main risk. The question is which rotation uses less irrigation water without losing the harvest. The decision always stays with the farmer and the local technician.

## Honest status

- The plot `sin-demo-001` is an **illustrative case**, not a real farm. Its point was drawn at random near Guasave (seed `20261115`) and nobody has visited it.
- The six values on the **My plot** screen come from the NASA data listed below, read for that point.
- The **order of the rotations** on the Compare, What-if and Evidence screens is still a hand-written example. The simulator that will compute it from these data is not built yet, and the screens say so.
- Local crop parameters (cycle length, sowing dates, yield, price, root depth) are **"no data"** until a source or a technician provides them. We do not invent values.

## NASA data we use

Every source below is read by code in [`pipeline/ingest/`](pipeline/ingest/README.md), with its provenance recorded. Access to the Earthdata-hosted products uses a personal Earthdata Login token kept in a git-ignored `.env`.

| NASA resource | Link | How kinilum uses it |
|---|---|---|
| **NASA POWER** (daily point API) | https://power.larc.nasa.gov/ | Daily temperature, humidity, solar radiation and wind for the zone (regional context, about 50 km). Gives the May maximum temperature and the heat days and crop water demand during maize flowering. |
| **GPM IMERG Final Daily V07** (GES DISC) | https://disc.gsfc.nasa.gov/datasets/GPM_3IMERGDF_07/summary | Satellite rainfall estimate for the plot's 0.1° cell, 2016–2025 (the Final run ends on 2025-09-30). Gives the May–October rain total, this season's rainfall and the rainfall normals. Zone context, labelled "estimated". |
| **HLS Landsat 30 m** (HLSL30 v2.0, LP DAAC) | https://www.earthdata.nasa.gov/data/catalog/lpcloud-hlsl30-2.0 | 30 m NDVI of the plot, with the 30 m inner edge discarded and clouds masked with Fmask. Gives the months without green plants. |
| **HLS Sentinel-2 30 m** (HLSS30 v2.0, LP DAAC) | https://www.earthdata.nasa.gov/data/catalog/lpcloud-hlss30-2.0 | The Sentinel-2 half of the HLS time series, used the same way. |
| **NASADEM Merged DEM** (NASADEM_HGT V001, LP DAAC) | https://www.earthdata.nasa.gov/data/catalog/lpcloud-nasadem-hgt-001 | 30 m elevation and slope of the plot's clean pixels. Gives the slope value and the elevation used in the water balance. |
| **SMAP L4 Soil Moisture** (SPL4SMGP V008, NSIDC DAAC) | https://nsidc.org/data/spl4smgp/versions/8 | Root-zone soil moisture of the 9 km cell, one granule per day over the last year. Zone context only; it is never drawn inside the plot. |
| **NASA CMR API and Earthdata Login** | https://cmr.earthdata.nasa.gov/search | Discovery of HLS scenes and of IMERG and SMAP granules, and authentication. (Earthdata Login: https://urs.earthdata.nasa.gov/) |

### Other data, not from NASA

| Resource | Link | How kinilum uses it |
|---|---|---|
| **Sentinel-2 L2A** (ESA, via Element 84 Earth Search) | https://earth-search.aws.element84.com/v1 | Backup for months with no clear HLS scene: NDVI from the plot's clean pixels. *Contains modified Copernicus Sentinel data.* |
| **ISRIC SoilGrids** | https://soilgrids.org/ | Clay content (0–5 cm) at 250 m, as context only. It does not feed any result; root depth never comes from SoilGrids. |
| **Open-Meteo** (ERA5 reanalysis) | https://open-meteo.com/ | Cross-check of rainfall and reference evapotranspiration against POWER and IMERG, and one of the sources behind the water-deficit range. |
| **FAO Irrigation and Drainage Paper 56** | https://www.fao.org/4/x0490e/x0490e00.htm | Crop coefficients (Kc) for the water criterion, only where they could be read with certainty. |

### Not used

MODIS, ECOSTRESS, GRACE and ERA5-Land are stubs marked "to integrate". They have never read any data and are **not** part of the results.

## How the data become what the app shows

```
NASA, ESA and ISRIC sources  →  pipeline/ingest (provenance, caching)
                              →  pipeline/harmonize (the six contract values, seasons, normals)
                              →  pipeline/package (one JSON package per plot, under 500 KB)
                              →  app (PWA, works offline once the package is saved)
```

Each value carries its source, native resolution, support level (plot, surroundings, zone or region), method (measured, interpolated, modeled or assumed), p10–p90 range and provenance, as defined in [`shared/schema/`](shared/schema/README.md). Zone and regional data are shown as context ("in your area"), never as detail inside the plot.

The first real run and what it found are written up in [`pipeline/EDA-hallazgos.md`](pipeline/EDA-hallazgos.md).

## Run it

```bash
# the app (Node 24)
cd app
npm install
npm run dev        # http://localhost:5173
npm run build      # tests + type check + build + offline and schema checks

# the pipeline (Python 3.14)
cd pipeline
python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest
echo "EARTHDATA_TOKEN=<your token>" > ../.env          # never commit it
.venv/bin/python -m ingest.run --parcel sin-demo-001 --lon -108.45673 --lat 25.50826
.venv/bin/python -m package.build --parcel sin-demo-001
```

## Privacy

The exact outline of a plot is never published. A package carries only a point rounded to two decimals and the area in hectares. The app uses no analytics, no external fonts or map tiles, and keeps everything the user chooses on their own phone.

## Team and license
* Jorge Enrique Vargas Pech
* Angel Isabella Morales Barrera
* David Eduardo Martín Dzul
* Isabella Cuevas Hernández
