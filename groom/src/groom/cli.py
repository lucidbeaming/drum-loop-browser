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
from groom.kit import (
    GM_NAMES,
    Kit,
    kit_from_text,
    kit_path,
    load_kit,
    load_labels,
    rebuild,
    save_kit,
)
from groom.ocr import OcrUnavailable, read_text
from groom.paths import project_paths
from groom.remap import NotDrums, output_dir, remap_folder
from groom.render import fluidsynth
from groom.rules import DEFAULT_RULES_PATH

app = typer.Typer(help="Offline grooming of the MIDI drum loop library.", no_args_is_help=True)
kit_app = typer.Typer(help="Kong kit maps (data/kits/), for `groom remap`.", no_args_is_help=True)
app.add_typer(kit_app, name="kit")
console = Console()
LOW_CONFIDENCE = 0.5


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


def _kit_file(name: str) -> Path:
    try:
        return kit_path(project_paths().kits, name)
    except ValueError as e:
        raise typer.BadParameter(str(e), param_hint="NAME") from e


def _print_kit(kit: Kit) -> None:
    pads = Table("Pad", "Label", "Role", "Note", "Group", "GM notes", "Check", title=kit.name)
    folded = kit.folded()
    for p in sorted(kit.pads, key=lambda p: p.pad):
        gm = [n for n, note in kit.gm_map.items() if note == p.note]
        check = list(p.remarks)
        if p.confidence < LOW_CONFIDENCE and not check:
            check.append(f"low confidence ({p.confidence:.1f})")
        pads.add_row(
            str(p.pad), p.label, p.role, str(p.note), "" if p.group is None else str(p.group),
            ", ".join(f"{n}{' (fold)' if n in folded else ''}" for n in gm),
            "[yellow]" + "; ".join(check) + "[/]" if check else "",
        )  # fmt: skip
    console.print(pads)
    console.print(
        "Unmapped GM notes (kept as they are by default): "
        + ", ".join(f"{n} {GM_NAMES[n]}" for n in kit.unmapped if n <= 59)
        + (" and the Latin percussion above 59" if any(n > 59 for n in kit.unmapped) else "")
    )


@kit_app.command("from-screenshot")
def kit_from_screenshot(
    image: Annotated[
        Path,
        typer.Argument(
            help="Screenshot of the kit's 4x4 pad grid, cropped to the pads.",
            exists=True,
            dir_okay=False,
        ),
    ],
    name: Annotated[str, typer.Option(help="Kit name; saved as data/kits/NAME.yaml.")],
    overwrite: Annotated[bool, typer.Option(help="Replace an existing kit file.")] = False,
) -> None:
    """Read a Kong kit's pads from a screenshot (macOS Vision OCR) into a kit map."""
    path = _kit_file(name)
    if path.exists() and not overwrite:
        raise typer.BadParameter(f"{path} exists (you may have edited it); use --overwrite")
    try:
        boxes = read_text(image, project_paths().data / "cache")
    except OcrUnavailable as e:
        raise typer.BadParameter(str(e)) from e
    kit = kit_from_text(name, str(image.resolve()), boxes, load_labels())
    save_kit(kit, path)
    _print_kit(kit)
    console.print(f"Saved {path}. Check it, edit any pad, then `groom kit rebuild {name}`.")


@kit_app.command("show")
def kit_show(name: Annotated[str, typer.Argument(help="Kit name.")]) -> None:
    """Print a kit's pads and GM map."""
    path = _kit_file(name)
    if not path.exists():
        raise typer.BadParameter(f"no kit {path}")
    _print_kit(load_kit(path))


@kit_app.command("rebuild")
def kit_rebuild(name: Annotated[str, typer.Argument(help="Kit name.")]) -> None:
    """Re-derive a kit's GM map from its pads' roles, after editing them."""
    path = _kit_file(name)
    if not path.exists():
        raise typer.BadParameter(f"no kit {path}")
    kit = rebuild(load_kit(path))
    save_kit(kit, path)
    _print_kit(kit)


@app.command()
def remap(
    folder: Annotated[
        Path,
        typer.Argument(
            help="Folder of GM drum MIDI files (read only).", exists=True, file_okay=False
        ),
    ],
    kit: Annotated[str, typer.Option(help="Kit name (data/kits/KIT.yaml).")],
    unmapped: Annotated[
        str, typer.Option(help="Notes the kit has no pad for: keep, drop, or a pad number.")
    ] = "keep",
    channel: Annotated[int, typer.Option(min=1, max=16, help="MIDI channel to write.")] = 10,
    dry_run: Annotated[bool, typer.Option(help="Report only; write nothing.")] = False,
    force: Annotated[bool, typer.Option(help="Accept notes outside the GM drum range.")] = False,
) -> None:
    """Copy FOLDER's MIDI files with GM drum notes moved to the kit's pads, into
    data/remapped/<folder> (<kit>)/, with remap-report.csv."""
    path = _kit_file(kit)
    if not path.exists():
        raise typer.BadParameter(f"no kit {path}; make one with `groom kit from-screenshot`")
    k = load_kit(path)
    policy: str | int = unmapped
    if unmapped.isdigit():
        policy = int(unmapped)
    elif unmapped not in ("keep", "drop"):
        raise typer.BadParameter("keep, drop or a pad number", param_hint="--unmapped")
    source = folder.resolve()
    out = output_dir(project_paths().remapped, source, k)
    if out == source or out in source.parents or source in out.parents:
        raise typer.BadParameter("the output folder can't be inside the input, or vice versa")
    try:
        reports = remap_folder(source, out, k, policy, channel, dry_run, force)
    except (NotDrums, ValueError) as e:
        raise typer.BadParameter(f"{e} (nothing written)") from e
    table = Table("File", "Notes", "Folded", "Unmapped", title=f"{source.name} → {k.name}")
    for r in reports:
        row = r.row()
        lost = "; ".join(
            f"{verb}: {row[key]}"
            for verb, key in (("kept", "unmapped_kept"), ("moved", "unmapped_moved"),
                              ("dropped", "unmapped_dropped"))
            if row[key]
        )  # fmt: skip
        table.add_row(r.path, str(r.notes), str(row["folded"]), lost)
    console.print(table)
    if dry_run:
        console.print(f"Dry run: nothing written. Without --dry-run: {out}")
    else:
        console.print(f"{len(reports)} files remapped into {out} (report: remap-report.csv)")
