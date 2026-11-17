"""Command-line entry point: ``groom <command>``."""

import json
import sqlite3
import time
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from groom import __version__, pipeline
from groom.curation import CurationError
from groom.fixtures import FIXTURE_RULES, write_fixture_library
from groom.paths import project_paths
from groom.render import fluidsynth
from groom.rules import DEFAULT_RULES_PATH

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
    rules_out: Annotated[
        Path | None,
        typer.Option(help="Also write the pack rules for the fixtures here (for `run --rules`)."),
    ] = None,
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
    if rules_out:
        rules_out.parent.mkdir(parents=True, exist_ok=True)
        rules_out.write_text(FIXTURE_RULES)
        console.print(f"wrote fixture rules to {rules_out}")


@app.command()
def run(
    audio: Annotated[
        bool, typer.Option(help="Check tempos against the WAV demos (cached after the first run).")
    ] = True,
    rules: Annotated[
        Path, typer.Option(help="Per-pack naming rules.", exists=True, dir_okay=False)
    ] = DEFAULT_RULES_PATH,
    render: Annotated[
        bool,
        typer.Option(
            help="Render every loop with the fluidsynth program and flag silent or clipping ones."
        ),
    ] = False,
) -> None:
    """Groom the library into data/: normalised MIDI, catalogue.sqlite and reports."""
    p = project_paths()
    if not p.library.is_dir():
        raise typer.BadParameter(f"library not found: {p.library}")
    if render and fluidsynth() is None:
        raise typer.BadParameter("--render needs the fluidsynth program (brew install fluid-synth)")
    started = time.perf_counter()
    with console.status("Grooming the library…"):
        try:
            result = pipeline.run(p, rules_path=rules, audio=audio, render=render)
        except CurationError as e:
            raise typer.BadParameter(str(e)) from e
    _print_coverage(result.coverage())
    console.print(
        f"{len(result.loops)} loops ({len(result.scan.loops)} files) groomed into {p.data} "
        f"in {time.perf_counter() - started:.1f}s"
    )
    if result.scan.unknown_packs:
        console.print(f"[yellow]Packs with no rules (skipped):[/] {result.scan.unknown_packs}")
    if result.scan.unmatched_demos:
        console.print(f"[yellow]{len(result.scan.unmatched_demos)} demos matched no loops[/]")
    console.print(f"Reports: {p.reports}")


@app.command()
def report() -> None:
    """Coverage summary from the last run's catalogue."""
    db = project_paths().data / "catalogue.sqlite"
    if not db.exists():
        raise typer.BadParameter("no catalogue yet; run `groom run` first")
    con = sqlite3.connect(db)
    rows = con.execute(
        "SELECT pack_id, count(*), sum(bpm IS NOT NULL), "
        + ", ".join(f"sum(bpm_check = '{c}')" for c in pipeline.BPM_CHECKS)
        + ", sum(meter_source IN ('folder', 'filename')), sum(status = 'review') "
        "FROM loops JOIN groups USING (group_id) GROUP BY pack_id ORDER BY pack_id"
    ).fetchall()
    keys = ["pack", "loops", "bpm_known", *pipeline.BPM_CHECKS, "meter_from_names", "review"]
    _print_coverage([dict(zip(keys, r, strict=True)) for r in rows])


@app.command()
def inspect(ref: Annotated[str, typer.Argument(help="Loop ID, or part of a source path.")]) -> None:
    """Everything the catalogue knows about one loop."""
    con = sqlite3.connect(project_paths().data / "catalogue.sqlite")
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT * FROM loops WHERE loop_id = ? OR src_rel_path LIKE ? LIMIT 5", (ref, f"%{ref}%")
    ).fetchall()
    if not rows:
        raise typer.BadParameter(f"no loop matches {ref!r}")
    for row in rows:
        table = Table("Field", "Value", show_header=False)
        for k in row.keys():  # noqa: SIM118 (sqlite3.Row has no __iter__ over keys)
            value = row[k]
            if k in ("bpm_candidates", "issues", "remarks", "also_at"):
                value = json.dumps(json.loads(value), indent=1) if value != "[]" else "—"
            table.add_row(k, str(value))
        tags = con.execute(
            "SELECT tag, source FROM tags WHERE loop_id = ? ORDER BY tag", (row["loop_id"],)
        ).fetchall()
        table.add_row("tags", ", ".join(f"{t} ({s})" for t, s in tags) or "—")
        similar = con.execute(
            "SELECT title, score FROM similar JOIN loops ON loops.loop_id = other_id "
            "WHERE similar.loop_id = ? ORDER BY rank LIMIT 5",
            (row["loop_id"],),
        ).fetchall()
        table.add_row("similar", "\n".join(f"{t} ({s:.2f})" for t, s in similar) or "—")
        console.print(table)


def _print_coverage(rows: list[dict[str, object]]) -> None:
    if not rows:
        return
    table = Table(*rows[0].keys())
    totals = {k: 0 for k in rows[0] if k != "pack"}
    for r in rows:
        table.add_row(*(str(v) for v in r.values()))
        for k in totals:
            totals[k] += int(r[k])  # type: ignore[call-overload]
    table.add_row("TOTAL", *(str(v) for v in totals.values()), style="bold")
    console.print(table)
