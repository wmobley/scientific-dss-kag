"""Locate data in source checkouts and installed wheels."""
import json
from importlib.resources import files
from pathlib import Path


def resource(path: str):
    # Paths are internal constants; never accept paths from API requests.
    installed = files("scientific_dss_kag").joinpath("resources", path)
    if installed.is_file():
        return installed
    root = Path(__file__).resolve().parents[2]
    if path.startswith("benchmarks/"):
        return root / "experiments" / path
    return root / path


def read_json(path: str):
    return json.loads(resource(path).read_text(encoding="utf-8"))


def resource_dir(path: str):
    """Directory in an installed wheel or a source checkout."""
    installed = files("scientific_dss_kag").joinpath("resources", path)
    if installed.is_dir():
        return installed
    return Path(__file__).resolve().parents[2] / path
