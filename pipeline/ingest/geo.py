"""Geografía mínima para leer píxeles: UTM directa y las celdas que quedan dentro de una parcela.

UTM con la serie de Krüger (WGS84, 4 términos): error de milímetros dentro de la zona. Sin pyproj.
"""

from __future__ import annotations

import math

_A = 6378137.0
_F = 1 / 298.257223563
_N = _F / (2 - _F)
_AA = _A / (1 + _N) * (1 + _N**2 / 4 + _N**4 / 64 + _N**6 / 256)
_ALPHA = (
    _N / 2 - 2 * _N**2 / 3 + 5 * _N**3 / 16 + 41 * _N**4 / 180,
    13 * _N**2 / 48 - 3 * _N**3 / 5 + 557 * _N**4 / 1440,
    61 * _N**3 / 240 - 103 * _N**4 / 140,
    49561 * _N**4 / 161280,
)
_K0 = 0.9996


def utm_zone_of_epsg(epsg: int) -> tuple[int, bool]:
    """(zona, ¿hemisferio norte?) de un EPSG de UTM sobre WGS84: 326zz (norte) o 327zz (sur)."""
    if 32601 <= epsg <= 32660:
        return epsg - 32600, True
    if 32701 <= epsg <= 32760:
        return epsg - 32700, False
    raise ValueError(f"EPSG:{epsg} no es una zona UTM de WGS84")


def utm_forward(lon: float, lat: float, zone: int, north: bool = True) -> tuple[float, float]:
    """(este, norte) en metros del punto en la zona UTM dada."""
    lam = math.radians(lon - ((zone - 1) * 6 - 180 + 3))
    phi = math.radians(lat)
    c = 2 * math.sqrt(_N) / (1 + _N)
    t = math.sinh(math.atanh(math.sin(phi)) - c * math.atanh(c * math.sin(phi)))
    xi0 = math.atan2(t, math.cos(lam))
    eta0 = math.atanh(math.sin(lam) / math.sqrt(1 + t * t))
    xi = xi0 + sum(a * math.sin(2 * j * xi0) * math.cosh(2 * j * eta0) for j, a in enumerate(_ALPHA, 1))
    eta = eta0 + sum(a * math.cos(2 * j * xi0) * math.sinh(2 * j * eta0) for j, a in enumerate(_ALPHA, 1))
    return 500_000 + _K0 * _AA * eta, (0 if north else 10_000_000) + _K0 * _AA * xi


def core_cells(pos: float, size_m: float, half_m: float, *, center_registered: bool = False) -> list[int]:
    """Índices de las celdas COMPLETAS dentro de `half_m` metros a cada lado del punto, en un eje.

    `pos` es la posición fraccionaria del punto en unidades de celda; `size_m` el tamaño de la celda. Con malla de área
    (`center_registered=False`, como HLS) la celda `i` cubre [i, i+1) y su centro está en i + 0.5; con malla de centros
    (NASADEM) la muestra `i` está en i.
    """
    shift = 0.0 if center_registered else 0.5
    lo = math.floor(pos - half_m / size_m) - 1
    hi = math.ceil(pos + half_m / size_m) + 1
    return [i for i in range(lo, hi + 1) if abs(i + shift - pos) * size_m + size_m / 2 <= half_m]
