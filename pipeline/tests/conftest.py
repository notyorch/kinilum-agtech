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
