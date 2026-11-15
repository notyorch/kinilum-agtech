"""El acceso con token de Earthdata, sin red: el encabezado viaja solo donde debe y el token nunca se ve."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from common.schema import REPO
from ingest import access, earthdata, env
from ingest.contract import SourceError
from ingest.http import Client, fetch_prefix, sends_token

FIXTURES = Path(__file__).parent / "fixtures"
TOKEN = "tokenfalso." + "x" * 40
NASA = "https://data.gesdisc.earthdata.nasa.gov/data/GPM_L3/f.nc4"
LPDAAC = "https://data.lpdaac.earthdatacloud.nasa.gov/lp-prod-protected/NASADEM_HGT.001/n20w090/n20w090.zip"
S3 = "https://lp-prod-protected.s3.us-west-2.amazonaws.com/NASADEM_HGT.001/n20w090.zip"
SIGNED = S3 + "?X-Amz-Signature=FIRMA-SECRETA&X-Amz-Expires=3600"
URS = "https://urs.earthdata.nasa.gov/oauth/authorize?client_id=abc&redirect_uri=x"
ZIP = b"PK\x03\x04" + b"\x00" * 100
LOGIN_PAGE = b"<!DOCTYPE html><html>Earthdata Login</html>"


def scripted(*steps):
    """Un `once` falso: responde en orden con los pasos dados y anota los encabezados de cada salto."""
    it = iter(steps)
    seen = []

    def once(url, headers, timeout):
        seen.append((url, dict(headers)))
        step = next(it)
        if isinstance(step, Exception):
            raise step
        return step

    once.seen = seen
    return once


def redirect(to, status=302):
    return status, {"Location": to}, b""


# ---- A quién se le manda el token ---------------------------------------------------------------------------------

@pytest.mark.parametrize("url", [NASA, LPDAAC, URS, "https://earthdata.nasa.gov/x"])
def test_the_token_may_go_to_nasa_domains_over_https(url):
    assert sends_token(url)


@pytest.mark.parametrize("url", [
    S3, SIGNED, "http://data.gesdisc.earthdata.nasa.gov/f.nc4",  # sin HTTPS
    "https://earthdata.nasa.gov.evil.example/x", "https://evil-earthdata.nasa.gov.example/x", "https://nasa.gov/x", "https://example.com/earthdata.nasa.gov",
])
def test_the_token_never_goes_anywhere_else(url):
    assert not sends_token(url)


def test_the_header_is_added_to_the_first_hop_and_dropped_when_redirected_to_s3():
    once = scripted(redirect(SIGNED), (206, {"Content-Range": "bytes 0-103/6767530"}, ZIP))
    probe = fetch_prefix(LPDAAC, token=TOKEN, once=once)
    assert once.seen[0][1]["Authorization"] == f"Bearer {TOKEN}"
    assert "Authorization" not in once.seen[1][1]  # S3 rechaza la petición si además lleva Authorization
    assert probe.token_hops == [True, False] and probe.status == 206 and probe.total_bytes == 6_767_530
    assert probe.final == "lp-prod-protected.s3.us-west-2.amazonaws.com/NASADEM_HGT.001/n20w090.zip"
    assert "FIRMA-SECRETA" not in repr(probe) and TOKEN not in repr(probe)


def test_the_token_stays_through_earthdata_login_redirects():
    once = scripted(redirect(URS), redirect(NASA), (200, {"Content-Length": "26000000"}, b"\x89HDF\r\n\x1a\n"))
    probe = fetch_prefix(NASA, token=TOKEN, once=once)
    assert probe.token_hops == [True, True, True] and probe.total_bytes == 26_000_000
    assert [h.split()[0] for h in probe.hops] == ["data.gesdisc.earthdata.nasa.gov", "urs.earthdata.nasa.gov", "data.gesdisc.earthdata.nasa.gov"]


def test_without_a_token_no_hop_carries_authorization():
    once = scripted(redirect(URS), (200, {}, LOGIN_PAGE))
    fetch_prefix(NASA, token=None, once=once)
    assert all("Authorization" not in h for _, h in once.seen)


def test_only_the_start_of_the_file_is_requested():
    once = scripted((206, {}, b"x"))
    fetch_prefix(NASA, token=TOKEN, nbytes=1000, once=once)
    assert once.seen[0][1]["Range"] == "bytes=0-999"


# ---- Fallos -------------------------------------------------------------------------------------------------------

def test_transient_errors_are_retried_with_growing_waits():
    slept = []
    once = scripted((503, {}, b""), (502, {}, b""), (206, {}, ZIP))
    probe = fetch_prefix(NASA, token=TOKEN, once=once, sleep=slept.append)
    assert probe.status == 206 and slept == [2, 4] and probe.hops == ["data.gesdisc.earthdata.nasa.gov 206"]


def test_network_errors_become_an_error_not_a_crash():
    probe = fetch_prefix(NASA, token=TOKEN, once=scripted(*[TimeoutError("lento")] * 3), sleep=lambda s: None)
    assert probe.status is None and probe.error == "TimeoutError"


def test_redirect_loops_and_redirects_without_location_are_errors():
    loop = fetch_prefix(NASA, token=TOKEN, once=scripted(*[redirect(NASA)] * 20), max_hops=4)
    assert loop.status is None and "más de 4 redirecciones" in loop.error
    bare = fetch_prefix(NASA, token=TOKEN, once=scripted((302, {}, b"")))
    assert bare.error == "redirección sin Location"


def test_a_real_local_server_redirects_with_cookies_and_never_receives_the_token():
    """urllib de verdad: sigue redirecciones a mano, conserva la cookie de sesión y lee solo el principio."""
    seen = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append((self.path, self.headers.get("Authorization"), self.headers.get("Cookie"), self.headers.get("Range")))
            if self.path == "/start":
                self.send_response(302)
                self.send_header("Location", "/mid")
                self.send_header("Set-Cookie", "sesion=abc; Path=/")
            elif self.path == "/mid" and "sesion=abc" in (self.headers.get("Cookie") or ""):
                self.send_response(302)
                self.send_header("Location", "/file")
            elif self.path == "/file":
                body = b"PK\x03\x04" + b"a" * 300_000
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                try:
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    pass  # el cliente cerró tras leer el principio, como debe
                return
            else:
                self.send_response(403)
            self.end_headers()

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        probe = fetch_prefix(f"http://127.0.0.1:{server.server_port}/start", token=TOKEN, nbytes=1000)
    finally:
        server.shutdown()
        server.server_close()
    assert probe.status == 200 and len(probe.data) == 1000 and probe.data.startswith(b"PK\x03\x04")
    assert [p for p, *_ in seen] == ["/start", "/mid", "/file"] and probe.token_hops == [False, False, False]
    assert all(auth is None for _, auth, *_ in seen)  # el token no sale hacia un servidor que no es de la NASA


# ---- Veredicto ----------------------------------------------------------------------------------------------------

def probe_of(status, data=b"", error=None):
    from ingest.http import Probe

    return Probe(status, data, [], None, "h/p", error)


def test_a_200_that_is_the_login_page_is_not_access():
    p = earthdata.PRODUCTS["nasadem"]
    assert earthdata.verdict(p, probe_of(206, ZIP))[0] == "acceso"
    assert earthdata.verdict(p, probe_of(200, LOGIN_PAGE))[0] == "sin acceso"
    assert earthdata.verdict(p, probe_of(401))[0] == "sin acceso" and earthdata.verdict(p, probe_of(403))[0] == "sin acceso"
    assert earthdata.verdict(p, probe_of(500))[0] == "error" and earthdata.verdict(p, probe_of(None, error="TimeoutError"))[0] == "error"


@pytest.mark.parametrize("key,magic", [("imerg", b"\x89HDF\r\n"), ("nasadem", b"PK\x03\x04"), ("modis", b"\x0e\x03\x13\x01"), ("hls", b"II*\x00"), ("hls", b"MM\x00*")])
def test_each_product_is_recognised_by_its_file_signature(key, magic):
    assert earthdata.verdict(earthdata.PRODUCTS[key], probe_of(206, magic + b"\x00" * 50))[0] == "acceso"


# ---- Búsqueda de granulos en CMR ----------------------------------------------------------------------------------

def cmr_client(name):
    body = json.loads((FIXTURES / f"cmr_granule_{name}.json").read_text(encoding="utf-8"))
    calls = []

    def transport(method, url, headers, payload, timeout):
        calls.append(url)
        return 200, json.dumps(body).encode(), url

    c = Client(transport=transport, sleep=lambda s: None, jitter=lambda: 0)
    c.calls_seen = calls
    return c


BBOX = [-89.4209, 20.2991, -89.4191, 20.3009]


@pytest.mark.parametrize("key,suffix,host", [
    ("imerg", ".nc4", "data.gesdisc.earthdata.nasa.gov"), ("nasadem", ".zip", "data.lpdaac.earthdatacloud.nasa.gov"),
    ("modis", ".hdf", "data.lpdaac.earthdatacloud.nasa.gov"), ("hls", ".B04.tif", "data.lpdaac.earthdatacloud.nasa.gov"),
])
def test_each_product_finds_a_downloadable_https_file_on_a_nasa_host(key, suffix, host):
    g = earthdata.find_granule(cmr_client(key), earthdata.PRODUCTS[key], BBOX)
    assert g["url"].startswith("https://" + host) and g["url"].endswith(suffix) and sends_token(g["url"])


def test_the_cmr_query_names_the_product_the_point_and_the_cloud_limit():
    c = cmr_client("hls")
    earthdata.find_granule(c, earthdata.PRODUCTS["hls"], BBOX)
    q = c.calls_seen[0]
    assert "short_name=HLSL30" in q and "version=2.0" in q and "cloud_cover=0%2C30" in q and "bounding_box=-89.420900" in q


def test_cmr_reports_the_size_as_text_and_sometimes_not_at_all():
    assert earthdata._megabytes("26.7517862319946") == 26.8 and earthdata._megabytes(6.76753) == 6.8
    assert earthdata._megabytes(None) is None and earthdata._megabytes("") is None and earthdata._megabytes("n/d") is None


def test_a_granule_without_the_wanted_file_is_no_data():
    with pytest.raises(SourceError, match="no trae un archivo"):
        earthdata.find_granule(cmr_client("imerg"), earthdata.Product("x", "x", "GPM_3IMERGDF", "07", {}, ".h5", (b"x",)), BBOX)


# ---- Sondeo completo ----------------------------------------------------------------------------------------------

def good_and_login(url_headers):
    """Con token entrega el archivo; sin token, la página de inicio de sesión."""
    def once(url, headers, timeout):
        return (206, {"Content-Range": "bytes 0-9/100"}, b"\x89HDF" + b"0" * 6) if "Authorization" in headers else (200, {}, LOGIN_PAGE)

    return once


def test_each_product_is_tried_with_the_token_and_again_without_it_as_a_control():
    rows = earthdata.check_access(cmr_client("imerg"), TOKEN, -89.42, 20.30, only=["imerg"], once=good_and_login(None))
    r = rows[0]
    assert (r["veredicto"], r["con_token"]["veredicto"], r["sin_token"]["veredicto"]) == ("acceso", "acceso", "sin acceso")
    assert r["con_token"]["token_en_saltos"] == [True] and r["sin_token"]["token_en_saltos"] == [False]
    assert TOKEN not in json.dumps(r)


def test_unknown_products_are_refused_and_only_filters():
    with pytest.raises(ValueError, match="desconocidos"):
        earthdata.check_access(cmr_client("imerg"), TOKEN, -89.42, 20.30, only=["inventado"])
    assert [r["producto"] for r in earthdata.check_access(cmr_client("imerg"), TOKEN, -89.42, 20.30, only=["imerg"], once=good_and_login(None))] == ["imerg"]


def test_the_report_never_shows_the_token(capsys):
    rows = earthdata.check_access(cmr_client("imerg"), TOKEN, -89.42, 20.30, only=["imerg"], once=good_and_login(None))
    text = access.render(rows)
    assert "ACCESO" in text and "SIN ACCESO" in text and TOKEN not in text


def test_the_command_refuses_to_run_without_a_token(capsys):
    assert access.main(["--only", "imerg"]) == 2
    err = capsys.readouterr().err
    assert "EARTHDATA_TOKEN" in err and ".env" in err


# ---- Dónde vive el token ------------------------------------------------------------------------------------------

def test_dotenv_is_parsed_without_surprises(tmp_path):
    f = tmp_path / ".env"
    f.write_text('# comentario\n\nEARTHDATA_TOKEN="abc.def.ghi"\nexport CDS_API_KEY=clave\nINEGI_TOKEN=\nSIN_IGUAL\n  ESPACIOS  =  valor  \n', encoding="utf-8")
    assert env.dotenv_values(f) == {"EARTHDATA_TOKEN": "abc.def.ghi", "CDS_API_KEY": "clave", "ESPACIOS": "valor"}
    assert env.dotenv_values(tmp_path / "no-existe") == {}


def test_the_environment_wins_over_the_file_and_a_missing_secret_is_none(monkeypatch, tmp_path):
    f = tmp_path / ".env"
    f.write_text("EARTHDATA_TOKEN=del-archivo\n", encoding="utf-8")
    monkeypatch.setattr(env, "DOTENV_PATH", f)
    assert env.secret("EARTHDATA_TOKEN") == "del-archivo"
    monkeypatch.setenv("EARTHDATA_TOKEN", "del-entorno")
    assert env.secret("EARTHDATA_TOKEN") == "del-entorno" and env.secret("CDS_API_KEY") is None


def test_credentials_can_never_be_committed():
    ignored = (REPO / ".gitignore").read_text(encoding="utf-8").split()
    assert ".env" in ignored and ".env.*" in ignored and "!.env.example" in ignored
    example = (REPO / ".env.example").read_text(encoding="utf-8")
    assert "EARTHDATA_TOKEN=" in example and all(line.endswith("=") or line.startswith("#") or not line for line in example.splitlines())
