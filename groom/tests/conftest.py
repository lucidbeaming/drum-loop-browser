from pathlib import Path

import pytest

from groom.fixtures import FIXTURE_RULES, write_fixture_library
from groom.paths import Paths


@pytest.fixture(scope="session")
def library(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("library")
    write_fixture_library(root)
    return root


@pytest.fixture(scope="session")
def fixture_rules(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("rules") / "packs.yaml"
    path.write_text(FIXTURE_RULES)
    return path


@pytest.fixture
def paths(library: Path, tmp_path: Path) -> Paths:
    return Paths(data=tmp_path / "data", library=library, soundfonts=tmp_path / "sf2")
