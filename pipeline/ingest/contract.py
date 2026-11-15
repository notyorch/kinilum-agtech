"""Contrato de la ingesta: errores, procedencia, series y valores del contrato de datos.

Un conector devuelve un `Fetch` o lanza una de dos excepciones. Nunca devuelve datos inventados:

  - `SourcePending`: falta una credencial o el conector aún es un esqueleto → estado `pending`.
  - `SourceError`:   la fuente respondió con error, no respondió o no tiene valores → estado `no_data`.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import numpy as np

from common.schema import schema_errors

STATUS_OK = "ok"
STATUS_PENDING = "pending"
STATUS_NO_DATA = "no_data"


class SourcePending(Exception):
    """La fuente aún no está integrada o falta una credencial. Se informa como «por integrar»."""


class SourceError(Exception):
    """La fuente respondió con error, no respondió o no tiene valores. Se informa como «sin dato»."""


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def support_level(native_res_m: float) -> str:
    """Nivel de soporte del contrato a partir de la resolución nativa en metros.

    Cortes propuestos (a validar): ≤ 70 m parcela · ≤ 1 km entorno · ≤ 15 km zona · mayor, región.
    """
    if native_res_m <= 70:
        return "parcel"
    if native_res_m <= 1000:
        return "surroundings"
    if native_res_m <= 15000:
        return "zone"
    return "region"


def clean_pixels(side_m: float, res_m: float, buffer_m: float = 30) -> int:
    """Píxeles completos dentro de la parcela tras descartar el borde interno (búfer de 30 m, regla del PRD)."""
    inner = max(side_m - 2 * buffer_m, 0)
    return int(inner // res_m) ** 2


def plot_bbox(lon: float, lat: float, side_m: float) -> list[float]:
    """[oeste, sur, este, norte] de una parcela cuadrada de `side_m` centrada en el punto."""
    dlat = side_m / 2 / 111_320
    dlon = side_m / 2 / (111_320 * math.cos(math.radians(lat)))
    return [lon - dlon, lat - dlat, lon + dlon, lat + dlat]


@dataclass
class Provenance:
    source: str
    product: str
    endpoint: str
    params: dict[str, Any]
    requested_at: str = field(default_factory=now_utc)
    response_sha256: str = ""
    license: str = ""
    citation: str = ""

    def steps(self, *extra: str) -> list[str]:
        """El campo `provenance` del contrato: de dónde salió, paso a paso."""
        out = [f"{self.source} · {self.product}", f"pedido el {self.requested_at}"]
        if self.response_sha256:
            out.append(f"respuesta sha256:{self.response_sha256[:16]}")
        return [*out, *extra]


def combined_sha(shas: list[str]) -> str:
    return hashlib.sha256("".join(shas).encode()).hexdigest()


@dataclass
class Series:
    """Serie diaria: fechas y una columna por variable. `nan` = faltante (nunca se rellena)."""

    dates: np.ndarray  # datetime64[D], ordenadas
    columns: dict[str, np.ndarray]
    units: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name, col in self.columns.items():
            if len(col) != len(self.dates):
                raise ValueError(f"{name}: {len(col)} valores para {len(self.dates)} fechas")

    def __len__(self) -> int:
        return len(self.dates)

    def col(self, name: str) -> np.ndarray:
        return self.columns[name]


@dataclass
class Fetch:
    """Lo que devuelve un conector: datos (una `Series` o una lista de filas), procedencia y notas."""

    data: Any
    prov: Provenance
    units: dict[str, str] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


def contract_value(
    variable: str,
    value: float | None,
    p10: float | None,
    p90: float | None,
    unit: str,
    prov: Provenance,
    native_resolution: str,
    native_res_m: float,
    method: str,
    timestamp: str,
    *,
    quality: str = "none",
    assumptions: list[str] | None = None,
    derived_resolution: str | None = None,
    extra_steps: list[str] | None = None,
    provenance: list[str] | None = None,
) -> dict[str, Any]:
    """Un `ContractValue` válido contra shared/schema. Sin valor, sin rango: se declara, no se rellena.

    `provenance` reemplaza los pasos que salen de `prov` (para lo declarado por el técnico, que no se «pidió» a nadie).
    """
    out: dict[str, Any] = {
        "variable": variable,
        "value": None if value is None else float(value),
        "p10": None if value is None or p10 is None else float(p10),
        "p90": None if value is None or p90 is None else float(p90),
        "unit": unit,
        "source": prov.source,
        "native_resolution": native_resolution,
        "support_level": support_level(native_res_m),
        "timestamp": timestamp,
        "method": method,
        "quality": quality,
        "assumptions": assumptions or [],
        "provenance": provenance if provenance is not None else prov.steps(*(extra_steps or [])),
    }
    if derived_resolution:
        out["derived_resolution"] = derived_resolution
    errors = schema_errors("contract-value", out)
    if errors:
        raise ValueError(f"{variable}: no cumple el contrato: " + "; ".join(errors))
    return out
