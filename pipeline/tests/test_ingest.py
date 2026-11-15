"""La capa de ingesta, sin red: respuestas grabadas de cada servicio, un transporte falso y reintentos sin esperar."""

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest

from common.schema import REPO
from ingest import catalog, cmr, credentialed, load, openmeteo, power, soilgrids, stac
from ingest.contract import (
    Fetch, Provenance, Series, SourceError, SourcePending, clean_pixels, contract_value, plot_bbox, support_level,
)
from ingest.http import Client

FIXTURES = Path(__file__).parent / "fixtures"


def fx(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def router(routes):
    """Transporte falso. `routes` es una lista de (método, texto de la URL, respuesta); gana la primera que calce."""
    seen = []

    def transport(method, url, headers, body, timeout):
        seen.append((method, url, body))
        for m, part, response in routes:
            if m == method and part in url:
                status, payload = response if isinstance(response, tuple) else (200, response)
                return status, (payload if isinstance(payload, bytes) else json.dumps(payload).encode()), url
        return 404, b"{}", url

    transport.seen = seen
    return transport


def client(routes=(), cache=None, slept=None):
    slept = [] if slept is None else slept
    return Client(cache, transport=router(routes), sleep=slept.append, jitter=lambda: 0)


# ---- Contrato -----------------------------------------------------------------------------------------------------

def test_support_level_cuts_follow_the_proposal():
    assert [support_level(m) for m in (30, 70, 250, 1000, 9000, 15000, 55000, 300000)] == [
        "parcel", "parcel", "surroundings", "surroundings", "zone", "zone", "region", "region",
    ]


def test_clean_pixels_discards_the_30m_edge():
    assert clean_pixels(200, 30) == 16  # núcleo de 140 m → 4 × 4 píxeles de HLS
    assert clean_pixels(200, 250) == 0  # MODIS nunca sostiene una afirmación de parcela de ese tamaño
    assert clean_pixels(50, 30) == 0


def test_plot_bbox_is_centered_and_about_200m():
    w, s, e, n = plot_bbox(-89.42, 20.30, 200)
    assert (w + e) / 2 == pytest.approx(-89.42) and (s + n) / 2 == pytest.approx(20.30)
    assert (n - s) * 111_320 == pytest.approx(200, rel=1e-6)


def prov():
    return Provenance("NASA POWER", "daily point (AG)", power.URL, {}, response_sha256="ab" * 32)


def test_contract_value_is_valid_against_the_schema():
    v = contract_value("tmax_may", 39, 37, 41, "°C", prov(), "0.5° × 0.625°", 55_000, "modeled", "2025", quality="medium", assumptions=["modeledClimate"])
    assert v["support_level"] == "region" and v["p10"] == 37 and v["provenance"][0].startswith("NASA POWER")


def test_contract_value_without_value_has_no_range_and_bad_enums_are_rejected():
    v = contract_value("rain_season", None, 1, 2, "mm", prov(), "0.1°", 11_000, "modeled", "2025")
    assert (v["value"], v["p10"], v["p90"]) == (None, None, None)
    with pytest.raises(ValueError):
        contract_value("rain_season", 1, 0, 2, "mm", prov(), "0.1°", 11_000, "guessed", "2025")


def test_series_rejects_columns_of_the_wrong_length():
    with pytest.raises(ValueError):
        Series(np.array(["2024-01-01"], dtype="datetime64[D]"), {"x": np.array([1.0, 2.0])})


# ---- Cliente HTTP -------------------------------------------------------------------------------------------------

def test_retries_with_growing_waits_then_succeeds():
    calls = {"n": 0}

    def flaky(method, url, headers, body, timeout):
        calls["n"] += 1
        return (503, b"", url) if calls["n"] < 4 else (200, b'{"ok": true}', url)

    slept = []
    c = Client(transport=flaky, sleep=slept.append, jitter=lambda: 0)
    assert c.get_json("https://x.test/a").body == {"ok": True}
    assert slept == [2, 4, 8]


def test_gives_up_after_the_tries_and_says_so_without_inventing_data():
    slept = []
    c = client([("GET", "x.test", (429, b""))], slept=slept)
    with pytest.raises(SourceError, match="sin respuesta tras 5 intentos"):
        c.get_json("https://x.test/a")
    assert slept == [2, 4, 8, 16]


def test_network_errors_are_retried():
    def broken(method, url, headers, body, timeout):
        raise TimeoutError("lento")

    c = Client(transport=broken, sleep=lambda s: None, jitter=lambda: 0)
    with pytest.raises(SourceError, match="TimeoutError"):
        c.get_json("https://x.test/a", tries=3)


@pytest.mark.parametrize("status", [400, 401, 403, 404])
def test_request_errors_are_not_retried(status):
    c = client([("GET", "x.test", (status, b"{}"))])
    with pytest.raises(SourceError, match=f"HTTP {status}"):
        c.get_json("https://x.test/a")
    assert len(c.transport.seen) == 1


def test_a_non_json_answer_is_no_data():
    with pytest.raises(SourceError, match="no es JSON"):
        client([("GET", "x.test", (200, b"<html>"))]).get_json("https://x.test/a")


def test_second_call_comes_from_the_cache(tmp_path):
    c = client([("GET", "x.test", {"v": 1})], cache=tmp_path)
    first = c.get_json("https://x.test/a", params={"q": 1})
    second = c.get_json("https://x.test/a", params={"q": 1})
    assert (first.from_cache, second.from_cache) == (False, True)
    assert second.body == {"v": 1} and second.sha256 == first.sha256
    assert len(c.transport.seen) == 1 and len(c.used) == 2


def test_sensitive_requests_are_not_cached_and_the_secret_never_shows(tmp_path):
    secret_url = "https://api.test/token/SECRETO123/data"
    c = client([("GET", "api.test", (500, b""))], cache=tmp_path)
    with pytest.raises(SourceError) as e:
        c.get_json(secret_url, sensitive=True, tries=2)
    assert "SECRETO123" not in str(e.value) and "api.test" in str(e.value)
    ok = client([("GET", "api.test", {"v": 1})], cache=tmp_path)
    ok.get_json(secret_url, sensitive=True)
    assert list(tmp_path.glob("*.json")) == []


# ---- POWER --------------------------------------------------------------------------------------------------------

def test_power_parses_the_recorded_response_into_a_series():
    c = client([("GET", power.URL, fx("power_daily.json"))])
    f = power.fetch_power(c, -89.42, 20.30, "2024-01-01", "2024-01-05")
    assert len(f.data) == 5 and str(f.data.dates[0]) == "2024-01-01" and set(f.data.columns) == set(power.PARAMETERS)
    assert f.units["WS2M"] == "m/s" and f.prov.source == "NASA POWER" and len(f.prov.response_sha256) == 64
    assert catalog.BY_ID["power"]["native_res_m"] == power.NATIVE_RES_M


def test_power_turns_the_fill_value_into_missing_not_into_a_number():
    body = fx("power_daily.json")
    day = next(iter(body["properties"]["parameter"]["T2M"]))
    body["properties"]["parameter"]["T2M"][day] = -999
    f = power.fetch_power(client([("GET", power.URL, body)]), -89.42, 20.30, "2024-01-01", "2024-01-05")
    assert np.isnan(f.data.col("T2M")[0]) and not np.isnan(f.data.col("T2M")[1])


def test_power_asks_one_year_at_a_time():
    c = client([("GET", power.URL, fx("power_daily.json"))])
    power.fetch_power(c, -89.42, 20.30, "2023-12-30", "2024-01-02")
    urls = [u for _, u, _ in c.transport.seen]
    assert len(urls) == 2 and "start=20231230&end=20231231" in urls[0] and "start=20240101&end=20240102" in urls[1]


def test_power_without_data_is_no_data():
    c = client([("GET", power.URL, {"messages": ["fuera de rango"]})])
    with pytest.raises(SourceError, match="POWER respondió sin datos"):
        power.fetch_power(c, -89.42, 20.30, "2024-01-01", "2024-01-05")


# ---- Open-Meteo ---------------------------------------------------------------------------------------------------

def test_openmeteo_parses_and_keeps_missing_as_nan():
    body = fx("openmeteo_archive.json")
    body["daily"]["precipitation_sum"][1] = None
    f = openmeteo.fetch_openmeteo(client([("GET", openmeteo.URL, body)]), -89.42, 20.30, "2024-01-01", "2024-01-05")
    assert len(f.data) == 5 and np.isnan(f.data.col("precipitation_sum")[1]) and f.prov.source == "Open-Meteo (ERA5)"


def test_openmeteo_error_body_is_no_data():
    c = client([("GET", openmeteo.URL, {"error": True, "reason": "fecha fuera de rango"})])
    with pytest.raises(SourceError, match="sin datos"):
        openmeteo.fetch_openmeteo(c, -89.42, 20.30, "2024-01-01", "2024-01-05")


# ---- SoilGrids ----------------------------------------------------------------------------------------------------

def test_soilgrids_all_null_is_no_data_not_ok():
    """El servicio contesta 200 con todo nulo en este punto: eso es «sin dato»."""
    c = client([("GET", soilgrids.URL, fx("soilgrids_null.json"))])
    with pytest.raises(SourceError, match="llegaron nulas"):
        soilgrids.fetch_soilgrids(c, -89.42, 20.30, ("clay", "soc"), ("0-5cm", "15-30cm"))


def test_soilgrids_converts_units_and_uses_quantiles_5_and_95():
    c = client([("GET", soilgrids.URL, fx("soilgrids_values.json"))])
    f = soilgrids.fetch_soilgrids(c, -89.42, 20.30, ("clay", "soc"), ("0-5cm", "15-30cm"))
    clay = next(r for r in f.data if r["property"] == "clay" and r["depth"] == "0-5cm")
    assert (clay["mean"], clay["q05"], clay["q95"], clay["units"]) == (25.0, 20.0, 31.0, "%")
    assert any("cuantiles 5 y 95" in n for n in f.notes)


def test_soilgrids_partial_nulls_are_reported():
    body = fx("soilgrids_values.json")
    body["properties"]["layers"][0]["depths"][0]["values"] = {"Q0.05": None, "Q0.95": None, "mean": None}
    f = soilgrids.fetch_soilgrids(client([("GET", soilgrids.URL, body)]), -89.42, 20.30, ("clay", "soc"), ("0-5cm", "15-30cm"))
    assert any("1 de 4 capas sin valor" in n for n in f.notes)


# ---- STAC y CMR ---------------------------------------------------------------------------------------------------

def stac_routes():
    return [
        ("GET", "stac/LPCLOUD/collections?cursor=PAGINA2", fx("cmr_stac_collections_p2.json")),
        ("GET", "stac/LPCLOUD/collections", fx("cmr_stac_collections_p1.json")),
        ("GET", "stac/LPCLOUD/search?cursor=PAGINA2", fx("hls_search_p2.json")),
        ("POST", "stac/LPCLOUD/search", fx("hls_search_p1.json")),
        ("POST", "earth-search", fx("s2_search.json")),
    ]


def test_hls_collections_skip_the_vegetation_index_copies_and_follow_pages():
    ids = stac.hls_collection_ids(client(stac_routes()))
    assert ids == ["HLSL30_2.0", "HLSS30_2.0"]


def test_hls_search_follows_the_next_link_and_parses_dates():
    c = client(stac_routes())
    f = stac.fetch_hls_scenes(c, -89.42, 20.30, "2025-02-01", "2025-02-28")
    assert len(f.data) == 3 and all(isinstance(s["datetime"], datetime) for s in f.data)
    assert any(m == "GET" and "cursor=PAGINA2" in u for m, u, _ in c.transport.seen)
    body = next(b for m, u, b in c.transport.seen if m == "POST")
    assert json.loads(body)["collections"] == ["HLSL30_2.0", "HLSS30_2.0"]
    # CMR-STAC responde 502 con páginas de más de ~1 MB: nunca se piden más de 75 escenas por página.
    assert json.loads(body)["limit"] == stac.HLS_PAGE_LIMIT == 50 and stac.HLS_PAGE_LIMIT <= 75
    assert f.notes[0] == "Solo metadatos de escenas; sin píxeles."


def test_parse_datetime_accepts_every_format_the_services_mix():
    """El notebook falló aquí: una fecha sin fracción de segundo después de otra con fracción."""
    for text in ("2025-02-02T16:38:23Z", "2025-02-27T16:38:01.850000Z", "2025-02-04T16:22:36.136Z"):
        assert stac.parse_datetime(text).tzinfo == timezone.utc


def test_s2_search_survives_mixed_datetime_formats():
    body = fx("s2_search.json")
    body["features"][0]["properties"]["datetime"] = "2025-02-02T16:38:23Z"
    f = stac.fetch_s2_scenes(client([("POST", "earth-search", body)]), -89.42, 20.30, "2025-02-01", "2025-02-28")
    assert len(f.data) == 3 and f.data[0]["datetime"] == datetime(2025, 2, 2, 16, 38, 23, tzinfo=timezone.utc)


def test_the_same_scene_in_two_products_counts_once():
    assert stac.scene_key("HLS.L30.T16QBH.2025003T162235.v2.0") == stac.scene_key("HLS-VI.L30.T16QBH.2025003T162235.v2.0")
    day = datetime(2025, 1, 3, tzinfo=timezone.utc)
    scenes = [{"id": "HLS.L30.T16QBH.2025003T162235.v2.0", "collection": "HLSL30_2.0", "datetime": day, "cloud": 5.0},
              {"id": "HLS-VI.L30.T16QBH.2025003T162235.v2.0", "collection": "HLSL30_VI_2.0", "datetime": day, "cloud": 5.0},
              {"id": "S2B_16QBH_20250227_0_L2A", "collection": "sentinel-2-l2a", "datetime": day, "cloud": 1.0}]
    assert len(stac.unique_scenes(scenes)) == 2


def test_cmr_discovery_returns_short_name_and_version():
    found = cmr.find_collections(client([("GET", cmr.URL, fx("cmr_collections.json"))]), "GPM IMERG Final daily")
    assert found[0]["short_name"] and set(found[0]) == {"short_name", "version", "title", "provider", "start"}


# ---- Fuentes con credencial ---------------------------------------------------------------------------------------

def test_credentialed_sources_are_pending_and_never_touch_the_network(monkeypatch):
    monkeypatch.delenv("EARTHDATA_TOKEN", raising=False)
    with pytest.raises(SourcePending, match="falta EARTHDATA_TOKEN"):
        credentialed.fetch_imerg()
    monkeypatch.setenv("EARTHDATA_TOKEN", "x" * 20)
    with pytest.raises(SourcePending, match="por integrar") as e:
        credentialed.fetch_nasadem()
    assert "xxxx" not in str(e.value)  # el token jamás aparece en un mensaje


# ---- Catálogo y cargador ------------------------------------------------------------------------------------------

def test_catalog_support_comes_from_the_resolution():
    rows = {r["id"]: r for r in catalog.rows()}
    assert (rows["hls_stac"]["support"], rows["modis"]["support"], rows["imerg"]["support"], rows["power"]["support"]) == (
        "parcel", "surroundings", "zone", "region",
    )
    assert set(rows) == set(load.CONNECTORS) and catalog.CORE == ["power", "imerg", "hls_stac", "nasadem"]


def all_routes():
    return [*stac_routes(), ("GET", power.URL, fx("power_daily.json")), ("GET", openmeteo.URL, fx("openmeteo_archive.json")),
            ("GET", soilgrids.URL, fx("soilgrids_null.json"))]


PARAMS = load.Params(-89.42, 20.30, "2024-01-01", "2024-01-05")


def test_each_source_ends_in_one_of_three_states_and_none_stops_the_rest(monkeypatch, tmp_path):
    for var in ("EARTHDATA_TOKEN", "CDS_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    results = load.load_sources(client(all_routes()), PARAMS, bronze_dir=tmp_path)
    states = {k: r.status for k, r in results.items()}
    assert states["power"] == states["openmeteo"] == states["hls_stac"] == states["s2_earthsearch"] == "ok"
    assert states["soilgrids"] == "no_data"
    assert states["imerg"] == states["nasadem"] == states["modis"] == states["era5land"] == "pending"
    assert len(results) == 12


def test_bronze_gets_a_manifest_per_source_with_the_files_that_fed_it(monkeypatch, tmp_path):
    monkeypatch.delenv("EARTHDATA_TOKEN", raising=False)
    load.load_sources(client(all_routes()), PARAMS, bronze_dir=tmp_path, parcel_id="yuc-demo-001")
    m = json.loads((tmp_path / "yuc-demo-001" / "power" / "manifest.json").read_text())
    assert (m["status"], m["parcel"], m["requested"]) == ("ok", "yuc-demo-001", {"start": "2024-01-01", "end": "2024-01-05"})
    assert m["files"] and all((tmp_path / "yuc-demo-001" / "power" / f).exists() for f in m["files"])
    pending = json.loads((tmp_path / "yuc-demo-001" / "imerg" / "manifest.json").read_text())
    assert pending["status"] == "pending" and pending["files"] == [] and "EARTHDATA_TOKEN" in pending["notes"][0]
    nodata = json.loads((tmp_path / "yuc-demo-001" / "soilgrids" / "manifest.json").read_text())
    assert nodata["status"] == "no_data"


def test_a_source_that_fails_on_purpose_is_retried_then_declared_no_data():
    slept = []
    c = client([("GET", power.URL, (503, b"")), ("GET", openmeteo.URL, fx("openmeteo_archive.json"))], slept=slept)
    results = load.load_sources(c, PARAMS, enabled=["power", "openmeteo"])
    assert results["power"].status == "no_data" and "sin respuesta tras 5 intentos" in results["power"].detail
    assert results["openmeteo"].status == "ok" and slept == [2, 4, 8, 16]


def test_an_unexpected_error_in_a_connector_does_not_stop_the_system(monkeypatch):
    def boom(c, p):
        raise KeyError("campo")

    monkeypatch.setitem(load.CONNECTORS, "power", boom)
    results = load.load_sources(client(all_routes()), PARAMS, enabled=["power", "openmeteo"])
    assert results["power"].status == "no_data" and results["power"].detail.startswith("inesperado: KeyError")
    assert results["openmeteo"].status == "ok"


def test_unknown_sources_are_refused():
    with pytest.raises(ValueError, match="no están en el catálogo"):
        load.load_sources(client(), PARAMS, enabled=["power", "inventada"])


def test_downloaded_data_never_gets_versioned():
    ignored = (REPO / ".gitignore").read_text(encoding="utf-8").split()
    assert "pipeline/data/" in ignored  # bronce, plata y oro (y las respuestas guardadas) no se suben
