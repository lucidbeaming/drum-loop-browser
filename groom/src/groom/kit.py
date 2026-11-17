"""Kong kits: pads read from a screenshot, their drum roles, and the GM -> pad note map.

Kong's pads form a 4x4 grid numbered from the bottom left (pad 1) to the top right (pad 16),
and pad n plays MIDI note 35 + n. A screenshot is OCR'd (module ocr) into text boxes; this module
groups them into the 16 pads, matches each label to a role (kit-labels.yaml), and derives which
pad each General MIDI drum note should go to, folding GM's many toms and cymbals onto the pads
the kit has. Kit files (data/kits/<name>.yaml) are meant to be checked and edited by hand.
"""

import re
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml
from rapidfuzz import fuzz

LABELS_PATH = Path(__file__).resolve().parents[2] / "kit-labels.yaml"
GRID = 4
FIRST_PAD_NOTE = 36  # pad 1; pad n = 35 + n (Kong's default)
MATCH_THRESHOLD = 80.0
UNKNOWN = "?"

GM_NAMES = {
    27: "High Q", 28: "Slap", 29: "Scratch Push", 30: "Scratch Pull", 31: "Sticks",
    32: "Square Click", 33: "Metronome Click", 34: "Metronome Bell", 35: "Acoustic Bass Drum",
    36: "Bass Drum 1", 37: "Side Stick", 38: "Acoustic Snare", 39: "Hand Clap",
    40: "Electric Snare", 41: "Low Floor Tom", 42: "Closed Hi-Hat", 43: "High Floor Tom",
    44: "Pedal Hi-Hat", 45: "Low Tom", 46: "Open Hi-Hat", 47: "Low-Mid Tom", 48: "Hi-Mid Tom",
    49: "Crash Cymbal 1", 50: "High Tom", 51: "Ride Cymbal 1", 52: "Chinese Cymbal",
    53: "Ride Bell", 54: "Tambourine", 55: "Splash Cymbal", 56: "Cowbell",
    57: "Crash Cymbal 2", 58: "Vibraslap", 59: "Ride Cymbal 2", 60: "Hi Bongo",
    61: "Low Bongo", 62: "Mute Hi Conga", 63: "Open Hi Conga", 64: "Low Conga",
    65: "High Timbale", 66: "Low Timbale", 67: "High Agogo", 68: "Low Agogo", 69: "Cabasa",
    70: "Maracas", 71: "Short Whistle", 72: "Long Whistle", 73: "Short Guiro",
    74: "Long Guiro", 75: "Claves", 76: "Hi Wood Block", 77: "Low Wood Block",
    78: "Mute Cuica", 79: "Open Cuica", 80: "Mute Triangle", 81: "Open Triangle",
    82: "Shaker", 83: "Jingle Bell", 84: "Belltree", 85: "Castanets", 86: "Mute Surdo",
    87: "Open Surdo",
}  # fmt: skip
GM_TOMS = (50, 48, 47, 45, 43, 41)  # high to low
# the GM notes a pad of each role stands for, its own note first; others folded onto it
PREFERRED: dict[str, tuple[int, ...]] = {
    "kick": (36, 35), "snare": (38, 40, 37), "rim": (37,), "clap": (39,),
    "closed-hat": (42, 44, 46), "pedal-hat": (44,), "open-hat": (46,),
    "tom-high": GM_TOMS, "tom-mid": GM_TOMS, "tom-low": GM_TOMS, "tom": GM_TOMS,
    "crash": (49, 57, 52, 55), "china": (52,), "splash": (55,),
    "ride": (51, 59, 53), "ride-bell": (53,),
    "tambourine": (54,), "cowbell": (56,), "cabasa": (69,),
}  # fmt: skip


@dataclass(frozen=True)
class TextBox:
    """One OCR result; x, y are the centre and w, h the size, as fractions of the image, with
    y measured from the top."""

    text: str
    x: float
    y: float
    w: float
    h: float
    confidence: float = 1.0


@dataclass
class Pad:
    pad: int
    label: str
    role: str
    note: int
    group: int | None = None  # the number in the pad's corner (e.g. the hi-hat choke group)
    confidence: float = 1.0
    remarks: list[str] = field(default_factory=list)


@dataclass
class Kit:
    name: str
    source_image: str
    pads: list[Pad]
    gm_map: dict[int, int]  # GM note -> pad note
    unmapped: list[int]  # GM notes with no pad

    def pad_for_note(self, note: int) -> Pad | None:
        return next((p for p in self.pads if p.note == note), None)

    def folded(self) -> set[int]:
        """GM notes that play on a pad standing for another note (e.g. 48 Hi-Mid Tom on a kit's
        only high tom pad, whose own note is 50 High Tom)."""
        by_pad: dict[int, list[int]] = defaultdict(list)
        for gm, note in self.gm_map.items():
            by_pad[note].append(gm)
        folded: set[int] = set()
        for note, gms in by_pad.items():
            if len(gms) < 2:
                continue
            pad = self.pad_for_note(note)
            order = PREFERRED.get(pad.role, ()) if pad else ()
            own = next((n for n in order if n in gms), min(gms))
            folded.update(n for n in gms if n != own)
        return folded


# --- labels ---------------------------------------------------------------------------------


# Cyrillic and Greek letters OCR can return for Latin look-alikes (e.g. "TO\u041c H")
_LOOKALIKES = str.maketrans(
    {
        "\u0410": "A", "\u0411": "B", "\u0412": "B", "\u0415": "E", "\u0417": "3",
        "\u041a": "K", "\u041c": "M", "\u041d": "H", "\u041e": "O", "\u0420": "P",
        "\u0421": "C", "\u0422": "T", "\u0423": "Y", "\u0425": "X", "\u0430": "a",
        "\u0435": "e", "\u043a": "k", "\u043c": "m", "\u043e": "o", "\u0440": "p",
        "\u0441": "c", "\u0443": "y", "\u0445": "x", "\u0391": "A", "\u0392": "B",
        "\u0395": "E", "\u0396": "Z", "\u0397": "H", "\u0399": "I", "\u039a": "K",
        "\u039c": "M", "\u039d": "N", "\u039f": "O", "\u03a1": "P", "\u03a4": "T",
        "\u03a5": "Y", "\u03a7": "X",
    }
)  # fmt: skip


def clean_label(text: str) -> str:
    """OCR text with look-alike letters made Latin and spacing tidied."""
    return re.sub(r"\s+", " ", text.translate(_LOOKALIKES)).strip()


def _norm(text: str) -> str:
    text = text.translate(_LOOKALIKES).upper()
    return re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9]+", " ", text.upper())).strip()


def load_labels(path: Path = LABELS_PATH) -> dict[str, str]:
    """Normalised label -> role."""
    data = yaml.safe_load(path.read_text())
    return {_norm(label): role for role, labels in data["roles"].items() for label in labels}


def match_role(label: str, labels: dict[str, str]) -> tuple[str, float]:
    """The role for a pad label and how sure the match is (0-1); UNKNOWN if not sure enough."""
    key = _norm(label)
    if not key:
        return UNKNOWN, 0.0
    if key in labels:
        return labels[key], 1.0
    bare = re.sub(r"(\s*\d+)+$", "", key)
    if bare in labels:
        return labels[bare], 1.0
    score, role = max(
        (max(fuzz.ratio(key, k), fuzz.ratio(bare, k) if bare else 0.0), r)
        for k, r in labels.items()
    )
    if score < MATCH_THRESHOLD:
        return UNKNOWN, round(score / 100, 2)
    return role, round(score / 100, 2)


# --- screenshot text -> pads -----------------------------------------------------------------


def _is_number(text: str) -> bool:
    return text.strip().isdigit()


def _cell(fraction: float) -> int:
    return min(GRID - 1, max(0, int(fraction * GRID)))


def pads_from_text(boxes: list[TextBox], labels: dict[str, str]) -> list[Pad]:
    """Group OCR boxes into Kong's 4x4 pads and read each pad's label, number and group.

    The screenshot must be cropped to the pad grid, so each quarter of it is a column or row,
    and the position decides the pad (bottom-left = 1). The small number beside the label is the
    pad number and only checks that; a number above the label, nearest the pad's top-left
    corner, is its group (shared by e.g. the hi-hats), recorded but never used to pick a pad.
    """
    cells: dict[int, list[TextBox]] = defaultdict(list)
    for b in boxes:
        if b.text.strip():
            cells[(GRID - 1 - _cell(b.y)) * GRID + _cell(b.x) + 1].append(b)

    pads = []
    for n in range(1, GRID * GRID + 1):
        cell = cells.get(n, [])
        texts = sorted((b for b in cell if not _is_number(b.text)), key=lambda b: (b.y, b.x))
        numbers = [b for b in cell if _is_number(b.text)]
        remarks: list[str] = []
        label = " ".join(clean_label(b.text) for b in texts)

        group: int | None = None
        number: int | None = None
        if numbers:
            corner = min(numbers, key=lambda b: b.x + b.y)
            above_label = bool(texts) and corner.y < texts[0].y - texts[0].h
            if len(numbers) > 1 or above_label:
                group = int(corner.text)
                numbers.remove(corner)
            if numbers:
                level = texts[0].y if texts else 0.0
                number = int(min(numbers, key=lambda b: abs(b.y - level)).text)
        if number is None:
            # OCR may join the pad number to the label ("SD1 2")
            m = re.fullmatch(r"(.*\S)\s+(\d+)", label)
            if m and int(m.group(2)) == n:
                label, number = m.group(1), n
        if number is not None and number != n:
            remarks.append(f"the screenshot says pad {number}; its position says pad {n}")

        role, confidence = match_role(label, labels) if label else ("none", 1.0)
        if not label:
            remarks.append("no label found")
        if role == UNKNOWN:
            remarks.append(f"label {label!r} not recognised; set its role")
        pads.append(
            Pad(
                n,
                label,
                role,
                FIRST_PAD_NOTE + n - 1,
                group,
                confidence,
                remarks,
            )
        )
    return pads


# --- GM map ------------------------------------------------------------------------------------


def _label_order(p: Pad) -> tuple[int, int]:
    m = re.search(r"(\d+)\s*$", p.label)
    return (int(m.group(1)) if m else 0, p.pad)


def build_gm_map(pads: list[Pad]) -> tuple[dict[int, int], list[int]]:
    """GM note -> pad note, from the pads' roles; and the GM notes left without a pad.

    Exact roles first; a second pad of a role gets GM's alternate note (35 kick, 40 snare).
    GM's six toms fold onto the tom pads high to low, crash/china/splash and ride/bell onto the
    cymbal pads, side stick onto a rim pad or the second snare, pedal and open hats onto the
    closed hat when the kit has no pad for them.
    """
    by_role: dict[str, list[Pad]] = defaultdict(list)
    for p in sorted(pads, key=_label_order):
        by_role[p.role].append(p)
    m: dict[int, int] = {}

    def put(gm: int, *choices: Pad | None) -> None:
        pad = next((p for p in choices if p is not None), None)
        if pad is not None:
            m.setdefault(gm, pad.note)

    def nth(role: str, i: int) -> Pad | None:
        pads_ = by_role.get(role, [])
        return pads_[i] if len(pads_) > i else None

    kick0, snare0 = nth("kick", 0), nth("snare", 0)
    put(36, kick0)
    put(35, nth("kick", 1), kick0)
    put(38, snare0)
    put(40, nth("snare", 1), snare0)
    put(37, nth("rim", 0), nth("snare", 1), snare0)
    put(39, nth("clap", 0))

    closed = nth("closed-hat", 0) or nth("pedal-hat", 0) or nth("open-hat", 0)
    put(42, closed)
    put(44, nth("pedal-hat", 0), closed)
    put(46, nth("open-hat", 0), closed)

    toms = (
        by_role.get("tom-high", []) + by_role.get("tom", []) + by_role.get("tom-mid", [])
        + by_role.get("tom-low", [])
    )  # fmt: skip
    for i, gm in enumerate(GM_TOMS):
        if toms:
            put(gm, toms[i * len(toms) // len(GM_TOMS)])

    crash0 = nth("crash", 0) or nth("china", 0) or nth("splash", 0)
    put(49, crash0)
    put(57, nth("crash", 1), crash0)
    put(52, nth("china", 0), crash0)
    put(55, nth("splash", 0), crash0)
    ride0 = nth("ride", 0) or nth("ride-bell", 0)
    put(51, ride0)
    put(59, nth("ride", 1), ride0)
    put(53, nth("ride-bell", 0), ride0)

    put(54, nth("tambourine", 0))
    put(56, nth("cowbell", 0))
    put(69, nth("cabasa", 0))

    unmapped = [n for n in GM_NAMES if n not in m]
    return dict(sorted(m.items())), unmapped


def kit_from_text(name: str, image: str, boxes: list[TextBox], labels: dict[str, str]) -> Kit:
    pads = pads_from_text(boxes, labels)
    gm_map, unmapped = build_gm_map(pads)
    return Kit(name, image, pads, gm_map, unmapped)


def rebuild(kit: Kit) -> Kit:
    """Re-derive the GM map after the pads' roles were edited."""
    gm_map, unmapped = build_gm_map(kit.pads)
    return Kit(kit.name, kit.source_image, kit.pads, gm_map, unmapped)


# --- files -------------------------------------------------------------------------------------

_HEADER = """\
# Kong kit map written by `groom kit from-screenshot`; edit freely.
# pads: what was read from the screenshot. Fix a wrong label or role ("?" = not recognised),
#   then run `groom kit rebuild {name}` to re-derive gm_map from the roles.
# gm_map: GM drum note -> Kong pad note, used by `groom remap`. Edit it directly to override.
"""


def save_kit(kit: Kit, path: Path) -> None:
    data: dict[str, Any] = {
        "name": kit.name,
        "source_image": kit.source_image,
        "pads": [
            {k: v for k, v in asdict(p).items() if not (k == "remarks" and not v)} for p in kit.pads
        ],
        "gm_map": kit.gm_map,
        "unmapped": kit.unmapped,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_HEADER.format(name=kit.name) + yaml.safe_dump(data, sort_keys=False))


def load_kit(path: Path) -> Kit:
    data = yaml.safe_load(path.read_text())
    pads = [Pad(**p) for p in data["pads"]]
    gm_map = {int(k): int(v) for k, v in (data.get("gm_map") or {}).items()}
    return Kit(data["name"], data.get("source_image", ""), pads, gm_map, data.get("unmapped", []))


def kit_path(kits_dir: Path, name: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 ._-]*", name):
        raise ValueError(f"kit name {name!r}: use letters, digits, spaces, dots, - and _")
    return kits_dir / f"{name}.yaml"
