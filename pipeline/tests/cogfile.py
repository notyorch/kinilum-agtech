"""Un escritor de GeoTIFF en la nube mínimo, solo para las pruebas: teselas, deflate, predictor horizontal y claves geográficas."""

import struct
import zlib

import numpy as np

_CHAR = {("u", 1): "B", ("u", 2): "H", ("i", 2): "h", ("u", 4): "I", ("i", 4): "i", ("f", 4): "f"}


def _pack(bo, typ, values):
    return {1: lambda v: struct.pack(bo + "B" * len(v), *v), 2: lambda v: v.encode() + b"\x00", 3: lambda v: struct.pack(bo + "H" * len(v), *v),
            4: lambda v: struct.pack(bo + "I" * len(v), *v), 12: lambda v: struct.pack(bo + "d" * len(v), *v)}[typ](values)


def build_cog(array, *, tile=16, predictor=2, compression=8, epsg=32616, user_defined_zone=None, origin=(199980.0, 2300040.0), pixel=(30.0, 30.0),
              nodata="-9999", byteorder="<", raster_type=1, tiled=True, bigtiff=False, samples=1):
    bo = byteorder
    kind, size = array.dtype.kind, array.dtype.itemsize
    h, w = array.shape
    ty_n, tx_n = -(-h // tile), -(-w // tile)
    padded = np.zeros((ty_n * tile, tx_n * tile), dtype=array.dtype)
    padded[:h, :w] = array
    tiles = []
    for ty in range(ty_n):
        for tx in range(tx_n):
            t = padded[ty * tile : (ty + 1) * tile, tx * tile : (tx + 1) * tile]
            if predictor == 2:
                u = t.view(np.dtype(f"u{size}")).copy()
                u[:, 1:] = t.view(np.dtype(f"u{size}"))[:, 1:] - t.view(np.dtype(f"u{size}"))[:, :-1]
                t = u
            tiles.append(zlib.compress(t.astype(np.dtype(bo + (t.dtype.kind + str(size)))).tobytes()))
    if user_defined_zone is None:
        keys = [1, 1, 0, 3, 1024, 0, 1, 1, 1025, 0, 1, raster_type, 3072, 0, 1, epsg]
        doubles = None
    else:
        keys = [1, 1, 0, 7, 1024, 0, 1, 1, 1025, 0, 1, raster_type, 2057, 34736, 1, 0, 2059, 34736, 1, 1, 3072, 0, 1, 32767, 3074, 0, 1, 16000 + user_defined_zone]
        keys[3] = 6
        keys = keys[:4 + 4 * 6]
        doubles = [6378137.0, 298.257223563]
    n_tiles = len(tiles)
    entries = [(256, 3, [w]), (257, 3, [h]), (258, 3, [8 * size]), (259, 3, [compression]), (262, 3, [1]), (277, 3, [samples]), (284, 3, [1])]
    if predictor == 2:
        entries.append((317, 3, [2]))
    if tiled:
        entries += [(322, 3, [tile]), (323, 3, [tile]), (324, 4, [0] * n_tiles), (325, 4, [len(t) for t in tiles])]
    else:
        entries += [(273, 4, [0]), (278, 3, [h]), (279, 4, [len(tiles[0])])]
    fmt = {"u": 1, "i": 2, "f": 3}[kind]
    entries += [(339, 3, [fmt]), (33550, 12, [pixel[0], pixel[1], 0.0]), (33922, 12, [0.0, 0.0, 0.0, origin[0], origin[1], 0.0]), (34735, 3, keys)]
    if doubles:
        entries.append((34736, 12, doubles))
    if nodata is not None:
        entries.append((42113, 2, nodata))
    entries.sort(key=lambda e: e[0])

    def layout(tile_offsets):
        n = len(entries)
        extra_start = 8 + 2 + 12 * n + 4
        extra, ifd = b"", b""
        for tag, typ, vals in entries:
            if tag == 324:
                vals = tile_offsets
            raw = _pack(bo, typ, vals)
            count = len(vals) if typ != 2 else len(vals) + 1
            if len(raw) <= 4:
                ifd += struct.pack(bo + "HHI", tag, typ, count) + raw.ljust(4, b"\x00")
            else:
                ifd += struct.pack(bo + "HHI", tag, typ, count) + struct.pack(bo + "I", extra_start + len(extra))
                extra += raw
        return ifd, extra, extra_start + len(extra)

    ifd, extra, data_start = layout([0] * n_tiles)
    offsets, cur = [], data_start
    for t in tiles:
        offsets.append(cur)
        cur += len(t)
    ifd, extra, _ = layout(offsets if tiled else [data_start])
    magic = 43 if bigtiff else 42
    head = (b"II" if bo == "<" else b"MM") + struct.pack(bo + "H", magic) + struct.pack(bo + "I", 8)
    return head + struct.pack(bo + "H", len(entries)) + ifd + struct.pack(bo + "I", 0) + extra + b"".join(tiles)


def serve(files):
    """Un `once` falso que sirve rangos de archivos en memoria: {url: bytes}. Anota cada petición en `.seen`."""
    seen = []

    def once(url, headers, timeout):
        seen.append((url, headers.get("Range")))
        if url not in files:
            return 404, {}, b""
        data = files[url]
        a, b = headers["Range"].removeprefix("bytes=").split("-")
        a, b = int(a), min(int(b), len(data) - 1)
        return 206, {"Content-Range": f"bytes {a}-{b}/{len(data)}"}, data[a : b + 1]

    once.seen = seen
    return once
