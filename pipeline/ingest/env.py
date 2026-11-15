"""Credenciales: primero la variable de entorno; si no está, el archivo `.env` de la raíz del repositorio.

`.env` lo ignora git (ver `.gitignore`); `.env.example` muestra qué variables existen. Nunca se imprime ni se
guarda un valor: ni en la caché, ni en informes, ni en mensajes de error.
"""

from __future__ import annotations

import os
from pathlib import Path

from common.schema import REPO

DOTENV_PATH = REPO / ".env"


def dotenv_values(path: Path | str | None = None) -> dict[str, str]:
    """Lee `CLAVE=valor` de un `.env`. Ignora comentarios y líneas vacías; un valor vacío cuenta como ausente."""
    p = Path(path) if path else DOTENV_PATH
    if not p.is_file():
        return {}
    out: dict[str, str] = {}
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip().removeprefix("export ").strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if sep and key.strip() and value:
            out[key.strip()] = value
    return out


def secret(name: str) -> str | None:
    return os.environ.get(name) or dotenv_values().get(name) or None
