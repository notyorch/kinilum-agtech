import json
from pathlib import Path

import pytest

from common.schema import REPO

PACKAGES: Path = REPO / "app" / "public" / "packages"


@pytest.fixture(scope="session")
def example_package() -> dict:
    """El paquete de ejemplo que publica la app (el que dice el índice)."""
    index = json.loads((PACKAGES / "index.json").read_text(encoding="utf-8"))
    entry = index["parcels"]["yuc-demo-001"]
    return json.loads((PACKAGES / entry["file"]).read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def hermetic_credentials(monkeypatch, tmp_path):
    """Las pruebas no leen el .env ni las variables de quien las corre: ninguna depende de un token real."""
    from ingest import env

    monkeypatch.setattr(env, "DOTENV_PATH", tmp_path / "sin-dotenv")
    for name in ("EARTHDATA_TOKEN", "CDS_API_KEY", "INEGI_TOKEN"):
        monkeypatch.delenv(name, raising=False)
