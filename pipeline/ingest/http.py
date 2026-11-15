"""Única puerta de salida a la red: reintentos con espera creciente, caché por respuesta y secretos a salvo.

Reglas (ARQUITECTURA-DEV §4.1, ingest/README.md):
  - Reintenta ante 429, 502, 503 y 504 y ante fallos de red, con espera de 2, 4, 8, 16 s más algo de azar.
  - NO reintenta 400, 401, 403 ni 404: son errores de la petición, no de la red.
  - Una petición `sensitive` (lleva un secreto en la ruta) no se guarda en caché ni se imprime.
  - Nunca se registran encabezados.
"""

from __future__ import annotations

import hashlib
import http.cookiejar
import json
import random
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlencode, urljoin, urlparse

from .contract import SourceError, now_utc

USER_AGENT = "kinilum-pipeline/0.1 (+https://github.com/notyorch/kinilum-agtech)"
RETRY_STATUS = frozenset({429, 502, 503, 504})

# (método, url, encabezados, cuerpo, tiempo máximo) → (código, bytes, url final)
Transport = Callable[[str, str, dict[str, str], "bytes | None", float], "tuple[int, bytes, str]"]


def urllib_transport(method: str, url: str, headers: dict[str, str], body: bytes | None, timeout: float) -> tuple[int, bytes, str]:
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read(), r.geturl()
    except urllib.error.HTTPError as e:
        return e.code, e.read(), url


@dataclass
class Response:
    body: Any
    sha256: str
    url: str
    from_cache: bool = False


class Client:
    def __init__(
        self,
        cache_dir: Path | str | None = None,
        *,
        transport: Transport = urllib_transport,
        sleep: Callable[[float], None] = time.sleep,
        jitter: Callable[[], float] = lambda: random.uniform(0, 1),
    ) -> None:
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.transport = transport
        self.sleep = sleep
        self.jitter = jitter
        self.calls = 0  # peticiones reales a la red (la caché no cuenta)
        self.used: list[str] = []  # archivos de caché que sirvieron a las últimas llamadas
        self.once: "Once | None" = None  # transporte de las descargas autenticadas (las pruebas lo reemplazan)
        self._lock = threading.Lock()  # los conectores con muchas peticiones usan varios hilos
        self._resolved: dict[str, str] = {}  # archivo → su URL firmada de la sesión (solo en memoria: es un secreto)

    def get_json(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        *,
        method: str = "GET",
        body: Any = None,
        headers: dict[str, str] | None = None,
        sensitive: bool = False,
        tries: int = 5,
        timeout: float = 90,
    ) -> Response:
        shown = urlparse(url).netloc if sensitive else url
        full = f"{url}?{urlencode(params, doseq=True)}" if params else url
        key = hashlib.sha256(json.dumps([method, url, params, body], sort_keys=True, default=str).encode()).hexdigest()
        cached = self._cache_file(key) if not sensitive else None
        if cached and cached.exists():
            c = json.loads(cached.read_text(encoding="utf-8"))
            self._note(cached.name)
            return Response(c["body"], c["sha256"], c["url"], from_cache=True)

        payload = None if body is None else json.dumps(body).encode()
        head = {"User-Agent": USER_AGENT, "Accept": "application/json", **({"Content-Type": "application/json"} if payload else {}), **(headers or {})}
        last = "sin respuesta"
        for attempt in range(tries):
            if attempt:
                self.sleep(2**attempt + self.jitter())
            self._count()
            try:
                status, raw, final = self.transport(method, full, head, payload, timeout)
            except OSError as e:  # fallo de red o tiempo agotado: se reintenta
                last = type(e).__name__
                continue
            if status in RETRY_STATUS:
                last = f"HTTP {status}"
                continue
            if status >= 400:
                raise SourceError(f"{shown}: HTTP {status}")
            try:
                data = json.loads(raw)
            except ValueError as e:
                raise SourceError(f"{shown}: la respuesta no es JSON") from e
            sha = hashlib.sha256(raw).hexdigest()
            if cached:
                cached.parent.mkdir(parents=True, exist_ok=True)
                cached.write_text(json.dumps({"body": data, "sha256": sha, "url": final, "at": now_utc()}, ensure_ascii=False), encoding="utf-8")
                self._note(cached.name)
            return Response(data, sha, final)
        raise SourceError(f"{shown}: sin respuesta tras {tries} intentos ({last})")

    def _cache_file(self, key: str, ext: str = "json") -> Path | None:
        return self.cache_dir / f"{key}.{ext}" if self.cache_dir else None

    def _count(self, n: int = 1) -> None:
        with self._lock:
            self.calls += n

    def _note(self, name: str) -> None:
        with self._lock:
            self.used.append(name)

    def get_range(self, url: str, start: int, length: int, *, token: str | None = None, timeout: float = 90) -> bytes:
        """`length` bytes de un archivo desde `start`, con caché. Los COG se leen por rangos: solo lo que se necesita.

        La primera lectura de un archivo resuelve su redirección (la URL firmada); las siguientes la reutilizan sin
        volver a pasar por Earthdata. La URL firmada NO se guarda en disco ni se imprime. Sin token, es un archivo público.
        """
        key = hashlib.sha256(json.dumps(["RANGE", url, start, length]).encode()).hexdigest()
        cached = self._cache_file(key, "bin")
        if cached and cached.exists():
            self._note(cached.name)
            return cached.read_bytes()
        where = f"{urlparse(url).hostname}{urlparse(url).path}"
        for attempt in (0, 1):
            with self._lock:
                target = self._resolved.get(url, url)
            self._count()
            probe = fetch_prefix(target, token=token, nbytes=length, start=start, timeout=timeout, once=self.once, sleep=self.sleep)
            if probe.status in (401, 403) and target != url and attempt == 0:  # la firma venció: se resuelve de nuevo
                with self._lock:
                    self._resolved.pop(url, None)
                continue
            break
        if probe.error:
            raise SourceError(f"{where}: {probe.error}")
        if probe.status in (401, 403):
            raise SourceError(f"{where}: sin acceso (HTTP {probe.status})")
        if probe.status == 200 and start > 0:
            raise SourceError(f"{where}: el servidor ignoró el rango pedido")
        if probe.status not in (200, 206):
            raise SourceError(f"{where}: HTTP {probe.status}")
        expected = length if probe.total_bytes is None else min(length, max(probe.total_bytes - start, 0))
        if len(probe.data) != expected:
            raise SourceError(f"{where}: llegaron {len(probe.data)} bytes y se esperaban {expected}")
        with self._lock:
            self._resolved[url] = probe.signed_url
        if cached:
            cached.parent.mkdir(parents=True, exist_ok=True)
            cached.write_bytes(probe.data)
            self._note(cached.name)
        return probe.data

    def get_authenticated(self, url: str, *, token: str, max_bytes: int = 2_000_000, timeout: float = 90, binary: bool = False) -> Response:
        """Descarga con `Authorization: Bearer` (OPeNDAP, archivos de datos). Texto, o bytes si `binary`.

        La URL y el token nunca se mezclan: el token solo va en el encabezado y solo a dominios de la NASA (ver
        `fetch_prefix`). La respuesta se guarda en la caché de la fuente; no se guarda nada del token.
        `max_bytes` es un tope: una respuesta más grande es un error, no un archivo cortado.
        """
        shown = urlparse(url)
        where = f"{shown.hostname}{shown.path}"
        key = hashlib.sha256(json.dumps(["AUTH", url], sort_keys=True).encode()).hexdigest()
        cached = self._cache_file(key, "bin" if binary else "json")
        if cached and cached.exists():
            raw = cached.read_bytes()
            self._note(cached.name)
            if binary:
                return Response(raw, hashlib.sha256(raw).hexdigest(), where, from_cache=True)
            c = json.loads(raw)
            return Response(c["body"], c["sha256"], where, from_cache=True)

        self._count()
        probe = fetch_prefix(url, token=token, nbytes=max_bytes, timeout=timeout, once=self.once, sleep=self.sleep)
        if probe.error:
            raise SourceError(f"{where}: {probe.error}")
        if probe.status in (401, 403):
            raise SourceError(f"{where}: sin acceso (HTTP {probe.status})")
        if probe.status not in (200, 206):
            raise SourceError(f"{where}: HTTP {probe.status}")
        if probe.status == 206 and probe.total_bytes and probe.total_bytes > len(probe.data):
            raise SourceError(f"{where}: el archivo ({probe.total_bytes} bytes) pasa del tope de {max_bytes}")
        sha = hashlib.sha256(probe.data).hexdigest()
        body: Any = probe.data if binary else probe.data.decode("utf-8", "replace")
        if cached:
            cached.parent.mkdir(parents=True, exist_ok=True)
            if binary:
                cached.write_bytes(probe.data)
            else:
                cached.write_text(json.dumps({"body": body, "sha256": sha, "at": now_utc()}, ensure_ascii=False), encoding="utf-8")
            self._note(cached.name)
        return Response(body, sha, where)


# ---- Descargas autenticadas con Earthdata -------------------------------------------------------------------------
#
# Los datos de la NASA se piden con `Authorization: Bearer <token>`. Dos reglas que importan:
#   - El token viaja SOLO a dominios de la NASA. Los servidores suelen redirigir a una URL firmada de S3, que rechaza
#     la petición si además lleva `Authorization`: en cada salto el encabezado se pone o se quita según el destino.
#   - Nada del token ni de la URL firmada (su consulta) se guarda ni se imprime: solo host y ruta.

AUTH_HOST_SUFFIXES = (".earthdata.nasa.gov", ".earthdatacloud.nasa.gov")
REDIRECTS = frozenset({301, 302, 303, 307, 308})

# (url, encabezados, tiempo máximo) → (código, encabezados de respuesta, primeros bytes del cuerpo)
Once = Callable[[str, dict[str, str], float], "tuple[int, dict[str, str], bytes]"]


def sends_token(url: str) -> bool:
    """¿Este destino es de la NASA y por tanto puede recibir el token?"""
    parsed = urlparse(url)
    host = parsed.hostname or ""
    return parsed.scheme == "https" and (host == "earthdata.nasa.gov" or host.endswith(AUTH_HOST_SUFFIXES))


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None  # las redirecciones las sigue `fetch_prefix`, salto por salto


def make_urllib_once(nbytes: int) -> Once:
    """Una petición sin seguir redirecciones, con las cookies de sesión de Earthdata Login entre saltos."""
    opener = urllib.request.build_opener(_NoRedirect, urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def once(url: str, headers: dict[str, str], timeout: float) -> tuple[int, dict[str, str], bytes]:
        try:
            with opener.open(urllib.request.Request(url, headers=headers), timeout=timeout) as r:
                return r.status, dict(r.headers), r.read(nbytes)  # solo el principio: se cierra sin bajar el resto
        except urllib.error.HTTPError as e:  # con _NoRedirect, también las 3xx llegan aquí
            return e.code, dict(e.headers), e.read(1024)

    return once


@dataclass
class Probe:
    """Resultado de pedir el principio de un archivo. `data` vive solo en memoria."""

    status: int | None
    data: bytes
    hops: list[str]  # «host código» de cada salto, sin rutas ni consultas
    total_bytes: int | None
    final: str  # host y ruta del último salto, sin consulta (la URL firmada es un secreto)
    error: str | None = None
    token_hops: list[bool] = field(default_factory=list)  # en qué saltos viajó el token
    signed_url: str = field(default="", repr=False)  # la URL del último salto, con su firma: un SECRETO, solo en memoria


def fetch_prefix(
    url: str,
    *,
    token: str | None = None,
    nbytes: int = 65_536,
    timeout: float = 60,
    once: Once | None = None,
    sleep: Callable[[float], None] = time.sleep,
    max_hops: int = 10,
    tries: int = 3,
    start: int = 0,
) -> Probe:
    """Pide `nbytes` de un archivo desde el byte `start` (por omisión, el principio) siguiendo las redirecciones a mano."""
    once = once or make_urllib_once(nbytes)
    current, hops, token_hops = url, [], []
    where = ""
    for _ in range(max_hops):
        parsed = urlparse(current)
        where = f"{parsed.hostname}{parsed.path}"
        headers = {"User-Agent": USER_AGENT, "Range": f"bytes={start}-{start + nbytes - 1}"}
        with_token = bool(token) and sends_token(current)
        if with_token:
            headers["Authorization"] = f"Bearer {token}"
        token_hops.append(with_token)

        status: int | None = None
        resp: dict[str, str] = {}
        body = b""
        error: str | None = None
        for attempt in range(tries):
            if attempt:
                sleep(2**attempt)
            try:
                status, resp, body = once(current, headers, timeout)
                error = None
            except OSError as e:  # red o tiempo agotado: se reintenta
                status, error = None, type(e).__name__
                continue
            if status not in RETRY_STATUS:
                break
        hops.append(f"{parsed.hostname} {status if status is not None else error}")
        if status is None:
            return Probe(None, b"", hops, None, where, error, token_hops)
        lower = {k.lower(): v for k, v in resp.items()}
        if status in REDIRECTS:
            if not lower.get("location"):
                return Probe(status, b"", hops, None, where, "redirección sin Location", token_hops)
            current = urljoin(current, lower["location"])
            continue
        total = None
        if "content-range" in lower and "/" in lower["content-range"]:
            tail = lower["content-range"].rsplit("/", 1)[1]
            total = int(tail) if tail.isdigit() else None
        elif status == 200 and lower.get("content-length", "").isdigit():
            total = int(lower["content-length"])
        return Probe(status, body, hops, total, where, None, token_hops, signed_url=current)
    return Probe(None, b"", hops, None, where, f"más de {max_hops} redirecciones", token_hops)
