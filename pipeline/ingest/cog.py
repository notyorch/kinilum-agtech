"""Lector mínimo de GeoTIFF en la nube (COG): solo lo que HLS y Sentinel-2 necesitan, sin GDAL ni rasterio.

Un COG es un TIFF con teselas: el encabezado dice dónde está cada tesela y se piden por rangos solo las que cubren la
ventana que interesa (una tesela de HLS pesa ~80 KB; el archivo, 24 MB). Soporta TIFF clásico, una banda, teselas con
deflate y predictor horizontal (o sin predictor), y proyección UTM sobre WGS84. Con cualquier otra cosa dice qué no
soporta; no adivina.

Se valida contra rasterio en una prueba de desarrollo (no es dependencia): ver pipeline/ingest/README.md.
"""

from __future__ import annotations

import math
import struct
import zlib
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .contract import SourceError
from .geo import utm_forward, utm_zone_of_epsg
from .http import Client

HEADER_BYTES = (32_768, 262_144)  # primero poco; si el encabezado no cabe, más
_TYPE = {1: ("B", 1), 2: ("s", 1), 3: ("H", 2), 4: ("I", 4), 6: ("b", 1), 7: ("B", 1), 8: ("h", 2), 9: ("i", 4), 11: ("f", 4), 12: ("d", 8)}
_DTYPE = {(1, 8): "u1", (1, 16): "u2", (2, 16): "i2", (1, 32): "u4", (2, 32): "i4", (3, 32): "f4"}
_DEFLATE = (8, 32946)


class NeedMore(Exception):
    """El encabezado no cabe en lo leído: hace falta leer hasta ese byte."""

    def __init__(self, upto: int) -> None:
        super().__init__(upto)
        self.upto = upto


def parse_header(data: bytes) -> dict[str, Any]:
    """Las etiquetas del primer IFD de un TIFF clásico. Lanza NeedMore si el encabezado sigue más allá de `data`."""
    if data[:2] not in (b"II", b"MM"):
        raise SourceError("el archivo no es un TIFF")
    bo = "<" if data[:2] == b"II" else ">"
    if struct.unpack(bo + "H", data[2:4])[0] != 42:
        raise SourceError("no es un TIFF clásico (¿BigTIFF?): no soportado")
    ifd = struct.unpack(bo + "I", data[4:8])[0]
    if ifd + 2 > len(data):
        raise NeedMore(ifd + 2)
    n = struct.unpack(bo + "H", data[ifd : ifd + 2])[0]
    if ifd + 2 + 12 * n > len(data):
        raise NeedMore(ifd + 2 + 12 * n)
    tags: dict[int, Any] = {"_byteorder": bo}
    for i in range(n):
        entry = data[ifd + 2 + 12 * i : ifd + 14 + 12 * i]
        tag, typ, count = struct.unpack(bo + "HHI", entry[:8])
        if typ not in _TYPE:
            continue  # tipos que no usamos (racionales, 64 bits)
        char, size = _TYPE[typ]
        total = size * count
        if total <= 4:
            raw = entry[8 : 8 + total]
        else:
            off = struct.unpack(bo + "I", entry[8:12])[0]
            if off + total > len(data):
                raise NeedMore(off + total)
            raw = data[off : off + total]
        tags[tag] = raw.decode("ascii", "replace").strip("\x00") if typ == 2 else np.frombuffer(raw, dtype=np.dtype(bo + char)).copy()
    return tags


def _need(tags: dict[int, Any], tag: int, what: str) -> Any:
    if tag not in tags:
        raise SourceError(f"al TIFF le falta {what} (etiqueta {tag})")
    return tags[tag]


USER_DEFINED = 32767  # «definido por el usuario»: el código EPSG no está, los parámetros sí
WGS84_A, WGS84_INVF = 6378137.0, 298.257223563


def _crs(tags: dict[int, Any]) -> int:
    """El EPSG de una proyección UTM sobre WGS 84, o un error. Dos formas de declararla:

      - con su código EPSG (326zz norte, 327zz sur), como las escenas recientes de HLS;
      - «definida por el usuario» (32767) con la zona en `ProjectionGeoKey` (16001–16060 norte, 17001–17060 sur) y el
        elipsoide WGS 84 en los parámetros, como las escenas antiguas de HLS (de 2016).
    """
    keys = _need(tags, 34735, "las claves geográficas").astype(int).tolist()
    doubles = tags.get(34736, np.zeros(0))
    found: dict[int, int | list[float]] = {}
    for k in range(keys[3]):
        key_id, loc, count, value = keys[4 + 4 * k : 8 + 4 * k]
        found[key_id] = value if loc == 0 else doubles[value : value + count].tolist() if loc == 34736 else value
    pcs = found.get(3072)
    if pcs is None:
        raise SourceError("el GeoTIFF no declara una proyección (ProjectedCSTypeGeoKey)")
    if pcs != USER_DEFINED:
        return int(pcs)
    projection = found.get(3074)
    axis, invf = found.get(2057), found.get(2059)
    wgs84 = isinstance(axis, list) and isinstance(invf, list) and abs(axis[0] - WGS84_A) < 1e-3 and abs(invf[0] - WGS84_INVF) < 1e-6
    if isinstance(projection, int) and 16001 <= projection <= 16060 and wgs84:
        return 32600 + (projection - 16000)
    if isinstance(projection, int) and 17001 <= projection <= 17060 and wgs84:
        return 32700 + (projection - 17000)
    raise SourceError("la proyección definida por el usuario no es una zona UTM sobre WGS 84: no soportada")


@dataclass
class COG:
    client: Client = field(repr=False)
    url: str = field(repr=False)
    token: str | None = field(repr=False)
    width: int = 0
    height: int = 0
    tile_w: int = 0
    tile_h: int = 0
    dtype: np.dtype = field(default_factory=lambda: np.dtype("u1"))
    predictor: int = 1
    offsets: np.ndarray = field(default_factory=lambda: np.zeros(0), repr=False)
    counts: np.ndarray = field(default_factory=lambda: np.zeros(0), repr=False)
    origin_x: float = 0.0
    origin_y: float = 0.0
    pixel_x: float = 0.0
    pixel_y: float = 0.0
    epsg: int = 0
    nodata: float | None = None
    _tiles: dict[int, np.ndarray] = field(default_factory=dict, repr=False)

    @classmethod
    def open(cls, client: Client, url: str, token: str | None = None) -> "COG":
        tags: dict[int, Any] = {}
        for n in HEADER_BYTES:
            head = client.get_range(url, 0, n, token=token)
            try:
                tags = parse_header(head)
                break
            except NeedMore as m:
                if m.upto <= n:  # no debería pasar; evita un ciclo
                    raise
        else:
            raise SourceError("el encabezado del GeoTIFF es más grande de lo esperado")

        bo = tags["_byteorder"]
        scalar = lambda t, what: int(_need(tags, t, what)[0])  # noqa: E731
        if scalar(277, "las muestras por píxel") != 1:
            raise SourceError("solo se soportan archivos de una banda")
        if scalar(284, "la organización de planos") != 1:
            raise SourceError("solo se soporta la organización de planos contigua")
        compression = scalar(259, "la compresión")
        if compression not in _DEFLATE:
            raise SourceError(f"compresión {compression} no soportada (solo deflate)")
        predictor = int(tags.get(317, [1])[0])
        if predictor not in (1, 2):
            raise SourceError(f"predictor {predictor} no soportado")
        if 322 not in tags or 324 not in tags:
            raise SourceError("el GeoTIFF no está organizado en teselas")
        bits, fmt = scalar(258, "los bits por muestra"), int(tags.get(339, [1])[0])
        if (fmt, bits) not in _DTYPE:
            raise SourceError(f"formato de muestra no soportado (formato {fmt}, {bits} bits)")
        scale, tie = _need(tags, 33550, "la escala de píxel"), _need(tags, 33922, "el punto de amarre")
        if len(tie) < 6:
            raise SourceError("el punto de amarre del GeoTIFF está incompleto")
        raster_type = 1
        keys = _need(tags, 34735, "las claves geográficas").astype(int).tolist()
        for k in range(keys[3]):
            if keys[4 + 4 * k] == 1025:
                raster_type = keys[7 + 4 * k]
        if raster_type != 1:
            raise SourceError("solo se soportan rásteres de área (PixelIsArea)")
        nodata = tags.get(42113)
        try:
            nodata_value = float(nodata) if nodata not in (None, "") else None
        except ValueError:
            nodata_value = None
        return cls(
            client, url, token, width=scalar(256, "el ancho"), height=scalar(257, "el alto"), tile_w=scalar(322, "el ancho de tesela"),
            tile_h=scalar(323, "el alto de tesela"), dtype=np.dtype(bo + _DTYPE[(fmt, bits)]), predictor=predictor,
            offsets=tags[324].astype(np.int64), counts=tags[325].astype(np.int64),
            origin_x=float(tie[3]) - float(tie[0]) * float(scale[0]), origin_y=float(tie[4]) + float(tie[1]) * float(scale[1]),
            pixel_x=float(scale[0]), pixel_y=float(scale[1]), epsg=_crs(tags), nodata=nodata_value,
        )

    def locate(self, lon: float, lat: float) -> tuple[float, float]:
        """(fila, columna) fraccionarias del punto: el píxel (r, c) cubre [r, r+1) × [c, c+1)."""
        zone, north = utm_zone_of_epsg(self.epsg)
        easting, northing = utm_forward(lon, lat, zone, north)
        return (self.origin_y - northing) / self.pixel_y, (easting - self.origin_x) / self.pixel_x

    def _tile(self, index: int) -> np.ndarray:
        if index in self._tiles:
            return self._tiles[index]
        count = int(self.counts[index])
        if count == 0:  # tesela vacía: todo sin dato
            fill = self.nodata if self.nodata is not None else 0
            tile = np.full((self.tile_h, self.tile_w), fill, dtype=self.dtype)
        else:
            raw = self.client.get_range(self.url, int(self.offsets[index]), count, token=self.token)
            try:
                data = zlib.decompress(raw)
            except zlib.error as e:
                raise SourceError(f"una tesela del GeoTIFF no se pudo descomprimir: {e}") from e
            if len(data) != self.tile_h * self.tile_w * self.dtype.itemsize:
                raise SourceError("una tesela del GeoTIFF tiene un tamaño inesperado")
            tile = np.frombuffer(data, dtype=self.dtype).reshape(self.tile_h, self.tile_w)
            if self.predictor == 2:  # diferencias horizontales: se deshacen con suma acumulada modular
                unsigned = tile.astype(self.dtype.newbyteorder("=")).view(np.dtype(f"u{self.dtype.itemsize}"))
                tile = np.cumsum(unsigned, axis=1, dtype=unsigned.dtype).view(self.dtype.newbyteorder("="))
            else:
                tile = tile.astype(self.dtype.newbyteorder("="))
        self._tiles[index] = tile
        return tile

    def window(self, row0: int, row1: int, col0: int, col1: int) -> np.ndarray:
        """Los píxeles [row0..row1] × [col0..col1] (ambos extremos incluidos), leyendo solo las teselas que los cubren."""
        if not (0 <= row0 <= row1 < self.height and 0 <= col0 <= col1 < self.width):
            raise SourceError("la ventana cae fuera del archivo")
        across = math.ceil(self.width / self.tile_w)
        out = np.empty((row1 - row0 + 1, col1 - col0 + 1), dtype=self.dtype.newbyteorder("="))
        for ty in range(row0 // self.tile_h, row1 // self.tile_h + 1):
            for tx in range(col0 // self.tile_w, col1 // self.tile_w + 1):
                tile = self._tile(ty * across + tx)
                r_lo, r_hi = max(row0, ty * self.tile_h), min(row1, (ty + 1) * self.tile_h - 1)
                c_lo, c_hi = max(col0, tx * self.tile_w), min(col1, (tx + 1) * self.tile_w - 1)
                out[r_lo - row0 : r_hi - row0 + 1, c_lo - col0 : c_hi - col0 + 1] = tile[r_lo - ty * self.tile_h : r_hi - ty * self.tile_h + 1, c_lo - tx * self.tile_w : c_hi - tx * self.tile_w + 1]
        return out
