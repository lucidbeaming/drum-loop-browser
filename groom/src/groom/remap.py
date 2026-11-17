"""`groom remap`: copy a folder of GM drum MIDI files with their notes moved to a kit's pads.

The input (e.g. a folder of dashboard exports) is only read. The output goes to
data/remapped/<input folder name> (<kit>)/, with the same file names and subfolders, plus
remap-report.csv saying, per file, which notes were folded onto a shared pad, and which notes the
kit has no pad for were kept as they are, moved to a chosen pad, or dropped.
"""

import csv
from dataclasses import dataclass, field
from pathlib import Path

import mido

from groom.kit import GM_NAMES, Kit

DRUM_RANGE = range(27, 88)  # GM's drum notes
DEFAULT_CHANNEL = 10


class NotDrums(Exception):
    pass


@dataclass
class FileReport:
    path: str
    notes: int = 0
    folded: set[int] = field(default_factory=set)
    kept: set[int] = field(default_factory=set)  # unmapped, left as they were
    moved: set[int] = field(default_factory=set)  # unmapped, sent to the --unmapped pad
    dropped: set[int] = field(default_factory=set)

    def row(self) -> dict[str, object]:
        def names(notes: set[int]) -> str:
            return "; ".join(f"{n} {GM_NAMES.get(n, '?')}" for n in sorted(notes))

        return {
            "file": self.path,
            "notes": self.notes,
            "folded": names(self.folded),
            "unmapped_kept": names(self.kept),
            "unmapped_moved": names(self.moved),
            "unmapped_dropped": names(self.dropped),
        }


def output_dir(remapped: Path, source: Path, kit: Kit) -> Path:
    return remapped / f"{source.name} ({kit.name})"


def remap_file(
    mid: mido.MidiFile, kit: Kit, unmapped: str | int, channel: int, report: FileReport,
    force: bool = False,
) -> mido.MidiFile:  # fmt: skip
    """A copy of ``mid`` with every note moved by the kit's GM map. ``unmapped`` says what to
    do with notes the kit has no pad for: "keep", "drop", or a pad number to send them to."""
    folded = kit.folded()
    target = None
    if isinstance(unmapped, int):
        pad = next((p for p in kit.pads if p.pad == unmapped), None)
        if pad is None:
            raise ValueError(f"the kit has no pad {unmapped}")
        target = pad.note

    out = mido.MidiFile(type=mid.type, ticks_per_beat=mid.ticks_per_beat)
    for track in mid.tracks:
        new = mido.MidiTrack()
        carry = 0  # delta time of dropped messages, passed on to the next one kept
        for msg in track:
            if msg.type not in ("note_on", "note_off"):
                new.append(msg.copy(time=msg.time + carry))
                carry = 0
                continue
            note = msg.note
            if note not in DRUM_RANGE and not force:
                raise NotDrums(f"{report.path}: note {note} is outside the GM drum range")
            if msg.type == "note_on" and msg.velocity:
                report.notes += 1
            if note in kit.gm_map:
                if note in folded:
                    report.folded.add(note)
                note = kit.gm_map[note]
            elif target is not None:
                report.moved.add(note)
                note = target
            elif unmapped == "drop":
                report.dropped.add(note)
                carry += msg.time
                continue
            else:
                report.kept.add(note)
            new.append(msg.copy(note=note, channel=channel - 1, time=msg.time + carry))
            carry = 0
        out.tracks.append(new)
    return out


def remap_folder(
    source: Path, out: Path, kit: Kit, unmapped: str | int = "keep",
    channel: int = DEFAULT_CHANNEL, dry_run: bool = False, force: bool = False,
) -> list[FileReport]:  # fmt: skip
    """Remap every .mid under ``source`` into ``out`` (unless ``dry_run``), keeping subfolders.
    Every file is checked before anything is written."""
    files = sorted(
        p for p in source.rglob("*") if p.is_file() and p.suffix.lower() in (".mid", ".midi")
    )
    reports = []
    done: list[tuple[Path, mido.MidiFile]] = []
    for path in files:
        rel = path.relative_to(source)
        report = FileReport(str(rel))
        done.append((rel, remap_file(mido.MidiFile(path), kit, unmapped, channel, report, force)))
        reports.append(report)
    if dry_run:
        return reports
    for rel, remapped in done:
        (out / rel).parent.mkdir(parents=True, exist_ok=True)
        remapped.save(out / rel)
    if reports:
        with (out / "remap-report.csv").open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(reports[0].row()))
            writer.writeheader()
            writer.writerows(r.row() for r in reports)
    return reports
