"""Command-line entry point: ``groom <command>``."""

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from groom import __version__
from groom.fixtures import write_fixture_library
from groom.paths import project_paths

app = typer.Typer(help="Offline grooming of the MIDI drum loop library.", no_args_is_help=True)
console = Console()


@app.command()
def version() -> None:
    """Print the groom version."""
    console.print(__version__)


@app.command()
def paths() -> None:
    """Show the project locations groom reads from and writes to."""
    p = project_paths()
    table = Table("Location", "Path", "Exists")
    for name, path in (("data", p.data), ("library", p.library), ("soundfonts", p.soundfonts)):
        table.add_row(name, str(path), "yes" if path.exists() else "no")
    console.print(table)


@app.command()
def fixtures(
    out_dir: Annotated[
        Path, typer.Argument(help="Empty folder to write the synthetic library to.")
    ],
) -> None:
    """Write the synthetic test library (no licensed content) to OUT_DIR."""
    out = out_dir.expanduser().resolve()
    library = project_paths().library
    if out == library or library in out.parents:
        raise typer.BadParameter(
            "refusing to write inside the real loop library", param_hint="OUT_DIR"
        )
    if out.exists() and any(out.iterdir()):
        raise typer.BadParameter(f"{out} is not empty", param_hint="OUT_DIR")
    loops = write_fixture_library(out)
    console.print(f"wrote {len(loops)} fixture loops to {out}")
