"""Text in images, through macOS's built-in Vision framework.

groom builds its small Swift helper (vision.swift) with the system ``swiftc`` the first time it
is needed, into data/cache/bin, so nothing has to be installed. macOS only.
"""

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

from groom.kit import TextBox

SOURCE = Path(__file__).with_name("vision.swift")


class OcrUnavailable(Exception):
    pass


def available() -> bool:
    return sys.platform == "darwin" and shutil.which("swiftc") is not None


def helper(cache_dir: Path) -> Path:
    """The compiled helper, built if the source changed since it was last built."""
    if not available():
        raise OcrUnavailable("reading screenshots needs macOS with swiftc (xcode-select --install)")
    digest = hashlib.sha1(SOURCE.read_bytes()).hexdigest()[:12]
    binary = cache_dir / "bin" / f"groom-vision-{digest}"
    if not binary.exists():
        binary.parent.mkdir(parents=True, exist_ok=True)
        tmp = binary.with_suffix(".tmp")
        result = subprocess.run(
            ["swiftc", "-O", str(SOURCE), "-o", str(tmp)], capture_output=True, text=True
        )
        if result.returncode != 0:
            raise OcrUnavailable(f"could not build the OCR helper:\n{result.stderr.strip()}")
        tmp.rename(binary)
    return binary


def read_text(image: Path, cache_dir: Path) -> list[TextBox]:
    result = subprocess.run(
        [str(helper(cache_dir)), "ocr", str(image)], capture_output=True, text=True
    )
    if result.returncode != 0:
        raise OcrUnavailable(result.stderr.strip())
    return [TextBox(**box) for box in json.loads(result.stdout)]


def render_grid(spec: dict[str, object], out: Path, cache_dir: Path) -> None:
    """Draw a Kong-style pad grid (for test fixtures); see vision.swift."""
    spec_file = out.with_suffix(".json")
    spec_file.write_text(json.dumps(spec))
    subprocess.run([str(helper(cache_dir)), "render", str(spec_file), str(out)], check=True)
    spec_file.unlink()
