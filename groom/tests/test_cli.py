from pathlib import Path

import pytest
from typer.testing import CliRunner

from groom.cli import app
from groom.fixtures import FIXTURES

runner = CliRunner()


def test_version() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert result.output.strip() == "0.1.0"


def test_fixtures_command_writes_library(tmp_path: Path) -> None:
    out = tmp_path / "fixtures"
    result = runner.invoke(app, ["fixtures", str(out)])
    assert result.exit_code == 0, result.output
    assert len(list(out.rglob("*.mid"))) == len(FIXTURES)


def test_fixtures_command_refuses_non_empty_dir(tmp_path: Path) -> None:
    (tmp_path / "existing.txt").write_text("x")
    result = runner.invoke(app, ["fixtures", str(tmp_path)])
    assert result.exit_code != 0


def test_fixtures_command_refuses_real_library(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    library = tmp_path / "patterns"
    library.mkdir()
    monkeypatch.setenv("DRUM_LIBRARY_DIR", str(library))
    result = runner.invoke(app, ["fixtures", str(library / "sub")])
    assert result.exit_code != 0
    assert not (library / "sub").exists()
