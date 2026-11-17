#!/usr/bin/env python3
"""Move lucidrum.sf2's drum kits to GM drum bank 128 with Roland GS program numbers.

Only the wPreset/wBank fields of the preset headers (phdr) are rewritten; samples,
instruments and every other byte are left untouched. The original file is copied to
<name>.orig.sf2 before patching (an existing backup is never overwritten).

Usage: patch_lucidrum_banks.py [path/to/lucidrum.sf2] [--dry-run]
"""
import shutil
import struct
import sys
from pathlib import Path

BANK = 128
# preset name (case-insensitive) -> GS program number
PROGRAMS = {
    "standard drum set": 0,
    "mash": 1,
    "warehouse perc": 2,
    "room set": 8,
    "power set": 16,
    "electronic set": 24,
    "tr-808 set": 25,
    "jazz set": 32,
    "brush set": 40,
    "orchestral set": 48,
    "sfx set": 56,
    "cm-64/32l set": 127,
}
PHDR_FMT = "<20sHHHIII"  # achPresetName, wPreset, wBank, wPresetBagNdx, dwLibrary, dwGenre, dwMorphology
PHDR_SIZE = struct.calcsize(PHDR_FMT)  # 38


def find_phdr(data: bytes) -> tuple[int, int]:
    """Return (offset, size) of the phdr sub-chunk inside LIST/pdta."""
    if data[:4] != b"RIFF" or data[8:12] != b"sfbk":
        raise SystemExit("not a SoundFont 2 file")
    off = 12
    while off < len(data):
        cid, size = struct.unpack_from("<4sI", data, off)
        if cid == b"LIST" and data[off + 8:off + 12] == b"pdta":
            sub, end = off + 12, off + 8 + size
            while sub < end:
                sid, ssize = struct.unpack_from("<4sI", data, sub)
                if sid == b"phdr":
                    return sub + 8, ssize
                sub += 8 + ssize + (ssize & 1)
        off += 8 + size + (size & 1)
    raise SystemExit("phdr chunk not found")


def preset_name(raw: bytes) -> str:
    return raw.split(b"\0")[0].decode("latin1")


def main() -> None:
    args = [a for a in sys.argv[1:] if a != "--dry-run"]
    dry_run = "--dry-run" in sys.argv
    path = Path(args[0] if args else "../sf2/lucidrum.sf2").resolve()

    data = bytearray(path.read_bytes())
    phdr_off, phdr_size = find_phdr(data)
    count = phdr_size // PHDR_SIZE - 1  # last record is the EOP terminal

    seen, changes = set(), []
    for i in range(count):
        rec = phdr_off + i * PHDR_SIZE
        name, prog, bank, *_ = struct.unpack_from(PHDR_FMT, data, rec)
        name = preset_name(name)
        key = name.lower()
        if key not in PROGRAMS:
            raise SystemExit(f"unexpected preset {name!r} (bank {bank}, prog {prog}); aborting")
        if key in seen:
            raise SystemExit(f"duplicate preset {name!r}; aborting")
        seen.add(key)
        changes.append((rec, name, bank, prog, BANK, PROGRAMS[key]))

    if missing := set(PROGRAMS) - seen:
        raise SystemExit(f"presets not found: {sorted(missing)}; aborting")

    for _, name, ob, op, nb, np in changes:
        print(f"  {name:20} bank {ob:3} prog {op:3}  ->  bank {nb:3} prog {np:3}")

    if all(ob == nb and op == np for _, _, ob, op, nb, np in changes):
        print("already patched; nothing to do")
        return
    if dry_run:
        print("dry run; file not modified")
        return

    backup = path.with_suffix(".orig.sf2")
    if backup.exists():
        print(f"backup already exists, keeping it: {backup}")
    else:
        shutil.copy2(path, backup)
        print(f"backup: {backup}")

    for rec, *_, nb, np in changes:
        struct.pack_into("<HH", data, rec + 20, np, nb)

    tmp = path.with_suffix(".sf2.tmp")
    tmp.write_bytes(data)
    tmp.replace(path)
    print(f"patched: {path}")


if __name__ == "__main__":
    main()
