"""Project filesystem locations.

Groom only reads and writes inside the project: the git-ignored ``data/`` folder in the repo,
plus the read-only sibling folders ``../patterns`` (loop library) and ``../sf2`` (SoundFonts).
Each location can be overridden with an environment variable.
"""

import os
from dataclasses import dataclass
from pathlib import Path

# groom/src/groom/paths.py -> repo root is three levels above this package
REPO_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class Paths:
    data: Path
    library: Path
    soundfonts: Path

    @property
    def kits(self) -> Path:
        return self.data / "kits"

    @property
    def remapped(self) -> Path:
        return self.data / "remapped"

    @property
    def reports(self) -> Path:
        return self.data / "reports"


def _env_path(name: str, default: Path) -> Path:
    value = os.environ.get(name)
    return Path(value).expanduser().resolve() if value else default


def project_paths() -> Paths:
    return Paths(
        data=_env_path("DRUM_DATA_DIR", REPO_ROOT / "data"),
        library=_env_path("DRUM_LIBRARY_DIR", REPO_ROOT.parent / "patterns"),
        soundfonts=_env_path("DRUM_SOUNDFONT_DIR", REPO_ROOT.parent / "sf2"),
    )
