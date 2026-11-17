"""Which keys each drum kit in a SoundFont (SF2) can sound: the audibility check.

Reads the preset and instrument zones straight from the file (no synth needed): a key is audible
in a preset if some preset zone's key range and some sampled instrument zone's key range both
include it.
"""

import struct
from dataclasses import dataclass
from pathlib import Path

DRUM_BANK = 128
GEN_KEY_RANGE = 43
GEN_INSTRUMENT = 41
GEN_SAMPLE_ID = 53
ALL_KEYS = (0, 127)


@dataclass(frozen=True)
class Kit:
    bank: int
    program: int
    name: str
    keys: frozenset[int]


def _chunks(data: bytes, start: int, end: int) -> dict[str, bytes]:
    out: dict[str, bytes] = {}
    pos = start
    while pos + 8 <= end:
        cid, size = struct.unpack_from("<4sI", data, pos)
        body = data[pos + 8 : pos + 8 + size]
        if cid == b"LIST":
            out[body[:4].decode()] = body
        else:
            out[cid.decode("latin-1")] = body
        pos += 8 + size + (size & 1)
    return out


def _records(body: bytes, fmt: str) -> list[tuple[object, ...]]:
    size = struct.calcsize(fmt)
    return [struct.unpack_from(fmt, body, i) for i in range(0, len(body) - size + 1, size)]


def _zones(
    bags: list[tuple[object, ...]], gens: list[tuple[object, ...]], first: int, last: int,
    terminal: int,
) -> list[tuple[tuple[int, int], int]]:  # fmt: skip
    """(key range, terminal value) for each zone in [first, last); the global zone's key range
    (a zone with no terminal generator) narrows all the others."""
    zones: list[tuple[tuple[int, int], int]] = []
    global_range = ALL_KEYS
    for b in range(first, last):
        g0, g1 = int(bags[b][0]), int(bags[b + 1][0])  # type: ignore[call-overload]
        key_range, target = ALL_KEYS, None
        for oper, amount in (gens[g][:2] for g in range(g0, g1)):
            if oper == GEN_KEY_RANGE:
                lo, hi = int(amount) & 0xFF, (int(amount) >> 8) & 0xFF  # type: ignore[call-overload]
                key_range = (lo, hi)
            elif oper == terminal:
                target = int(amount)  # type: ignore[call-overload]
        if target is None:
            global_range = key_range
        else:
            lo = max(key_range[0], global_range[0])
            zones.append(((lo, min(key_range[1], global_range[1])), target))
    return zones


def drum_kits(path: Path) -> list[Kit]:
    """Every bank-128 preset and the keys it has samples for."""
    data = path.read_bytes()
    if data[:4] != b"RIFF" or data[8:12] != b"sfbk":
        raise ValueError(f"{path} is not an SF2 SoundFont")
    top = _chunks(data, 12, len(data))
    pdta = top["pdta"]
    sub = _chunks(pdta, 4, len(pdta))
    phdr = _records(sub["phdr"], "<20sHHHIII")
    pbag = _records(sub["pbag"], "<HH")
    pgen = _records(sub["pgen"], "<HH")
    inst = _records(sub["inst"], "<20sH")
    ibag = _records(sub["ibag"], "<HH")
    igen = _records(sub["igen"], "<HH")

    def instrument_keys(i: int) -> set[int]:
        first, last = int(inst[i][1]), int(inst[i + 1][1])  # type: ignore[call-overload]
        keys: set[int] = set()
        for (lo, hi), _sample in _zones(ibag, igen, first, last, GEN_SAMPLE_ID):
            keys.update(range(lo, hi + 1))
        return keys

    kits = []
    for p in range(len(phdr) - 1):  # the last record is the terminal "EOP"
        name_raw, program, bank, bag = phdr[p][:4]
        if bank != DRUM_BANK:
            continue
        keys: set[int] = set()
        next_bag = int(phdr[p + 1][3])  # type: ignore[call-overload]
        for (lo, hi), inst_index in _zones(pbag, pgen, int(bag), next_bag, GEN_INSTRUMENT):  # type: ignore[call-overload]
            keys.update(k for k in instrument_keys(inst_index) if lo <= k <= hi)
        name = bytes(name_raw).split(b"\0")[0].decode("latin-1").strip()  # type: ignore[call-overload]
        kits.append(Kit(int(bank), int(program), name, frozenset(keys)))  # type: ignore[call-overload]
    return sorted(kits, key=lambda k: k.program)
