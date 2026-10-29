"""Builds the website's data:  python -m runner.site_data [--profile full]

Reads the aggregated results in results/<profile>/<stage>/*.csv and writes one script per
profile, docs/data/<profile>.js, which the GitHub Pages site in docs/ loads. It is a script that
sets window.SHARP_RESULTS["<profile>"] to the JSON, rather than a .json file, because browsers
refuse to fetch files when index.html is opened straight from disk. Nothing here touches the
database. Every CSV under results/ was written by runner.results.save, so the small-cell rule
has already been applied; hidden counts stay as the text "<11" and are shown as such.

Only the run's name, status, times and commit are published from run_info.json, never the
copied config (it names the Redshift host).
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import math
import sys
from pathlib import Path

from runner import config

log = logging.getLogger("runner.site_data")

RESULTS_DIR = config.REPO_ROOT / "results"
SITE_DATA_DIR = config.REPO_ROOT / "docs" / "data"
FIGURES_DIR = config.REPO_ROOT / "docs" / "figures"
WHITE = 246   # a pixel this light in every channel counts as background
RUN_INFO_FIELDS = ("run", "status", "started_utc", "finished_utc", "git_commit")

Cell = int | float | str | None


class SiteDataError(RuntimeError):
    """A profile's results are missing, unfinished, or not a clean table."""


def _cell(text: str) -> Cell:
    if text == "":
        return None
    try:
        return int(text)
    except ValueError:
        pass
    try:
        number = float(text)
    except ValueError:
        return text   # labels such as "50-64", "5+" and the hidden-count marker "<11"
    return number if math.isfinite(number) else text


def read_table(path: Path) -> dict[str, list[str] | list[list[Cell]]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        columns = next(reader, None)
        if not columns or len(set(columns)) != len(columns):
            raise SiteDataError(f"{path}: missing or repeated column names.")
        rows = [[_cell(value) for value in row] for row in reader]
    ragged = [i for i, row in enumerate(rows, start=2) if len(row) != len(columns)]
    if ragged:
        raise SiteDataError(f"{path}: line {ragged[0]} has {len(rows[ragged[0] - 2])} values, "
                            f"expected {len(columns)}.")
    return {"columns": columns, "rows": rows}


def profile_data(results_dir: Path) -> dict[str, object]:
    info_file = results_dir / "run_info.json"
    if not info_file.is_file():
        raise SiteDataError(f"{results_dir.as_posix()} has no run_info.json: run the pipeline for "
                            "this profile first.")
    info = json.loads(info_file.read_text(encoding="utf-8"))
    if info.get("status") != "complete":
        raise SiteDataError(f"The {results_dir.name} run did not finish (status: {info.get('status')}); "
                            "resume it before publishing.")
    tables = {path.relative_to(results_dir).with_suffix("").as_posix(): read_table(path)
              for path in sorted(results_dir.glob("*/*.csv"))}
    if not tables:
        raise SiteDataError(f"{results_dir.as_posix()} has no result tables.")
    return {"run": {field: info.get(field) for field in RUN_INFO_FIELDS}, "tables": tables}


def build(profile: str, results_root: Path = RESULTS_DIR, out_dir: Path = SITE_DATA_DIR) -> Path:
    data = profile_data(results_root / profile)
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{profile}.js"
    payload = json.dumps(data, separators=(",", ":"), allow_nan=False)   # JSON is valid JavaScript
    target.write_text("window.SHARP_RESULTS = window.SHARP_RESULTS || {};\n"
                      f"window.SHARP_RESULTS[{json.dumps(profile)}] = {payload};\n", encoding="utf-8")
    log.info("wrote %s (%d tables, %.0f KB)", target.as_posix(), len(data["tables"]),  # type: ignore[arg-type]
             target.stat().st_size / 1024)
    return target


def copy_figures(results_root: Path = RESULTS_DIR, out_dir: Path = FIGURES_DIR) -> int:
    """Rhea's Gagne figures, from the full cohort only: in the small test runs a single person could
    be read off the smallest bars, so their figures are never published."""
    figures = sorted((results_root / "full" / "5_gagne" / "plots").glob("*.png"))
    out_dir.mkdir(parents=True, exist_ok=True)
    for figure in figures:
        _without_white_background(figure, out_dir / figure.name)
    return len(figures)


def _without_white_background(source: Path, target: Path) -> None:
    """Make the plot's white background transparent, so the figure sits on the page like the others."""
    from PIL import Image, ImageChops   # only this step needs Pillow

    with Image.open(source) as image:
        rgba = image.convert("RGBA")
    red, green, blue, _ = rgba.split()
    lightest = ImageChops.darker(ImageChops.darker(red, green), blue)
    rgba.putalpha(lightest.point([0 if v >= WHITE else 255 for v in range(256)]))
    rgba.save(target)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m runner.site_data", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--profile", choices=list(config.PROFILES),
                        help="build one profile (default: all three)")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    try:
        for profile in [args.profile] if args.profile else list(config.PROFILES):
            build(profile)
        if args.profile in (None, "full"):
            log.info("copied %d full-cohort figures to %s", copy_figures(), FIGURES_DIR.as_posix())
    except (SiteDataError, OSError, json.JSONDecodeError) as error:
        log.error("%s", error)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
