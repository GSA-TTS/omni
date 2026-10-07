"""Access runtime data from an installed package or a source checkout."""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path

_SOURCE_ROOT = Path(__file__).resolve().parent.parent


def resource_text(name: str) -> str:
    """Read a packaged resource, falling back to its canonical source file."""
    packaged = files("harness").joinpath("resources", name)
    if packaged.is_file():
        return packaged.read_text(encoding="utf-8")
    return (_SOURCE_ROOT / name).read_text(encoding="utf-8")
