"""Saving query results. Only aggregates leave Redshift, and the small-cell rule is applied
here, once, for every saved table:

  label columns (LABEL_COLUMNS)      left as they are
  every other number                 a count: 1 to 10 becomes "<11"; any other count becomes an
                                     approximation: the nearest 10 (never below 20), then 3
                                     significant figures (14,123 is saved as 14,100)
  derived columns (pct_*, mean_*, smd*, lift)  rounded (percentages to one decimal) and blanked on
                                     any row where a count was hidden

Rounding every published count means a hidden count cannot be worked out by subtracting other
cells from a total: the rounding error of the other cells is larger than the hidden count.
A fractional column with any other name stops the run, so nothing is saved unchecked.

python -m runner.results re-applies the rule to every CSV already saved under results/ (run it
after the rule changes). It is safe to run more than once.
"""
from __future__ import annotations

import csv
import logging
import numbers
import sys
from decimal import Decimal
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)

LABEL_COLUMNS = frozenset({"yr", "analysis_year", "concept_year", "hiv", "gagne_group", "score", "diff",
                           "n_conditions", "step_order", "group_a", "group_b", "higher_is_better"})
DERIVED_DECIMALS = {"pct_": 1, "mean_": 2, "smd": 3, "lift": 2}
DERIVED_PREFIXES = tuple(DERIVED_DECIMALS)
HIDDEN = "<11"
ROUND_TO = 10
SMALLEST_SHOWN = 20
SIGNIFICANT_FIGURES = 3

RESULTS_DIR = Path(__file__).resolve().parents[1] / "results"


class UnsafeResultError(ValueError):
    """A result column the small-cell rule cannot classify."""


def _is_number(value: object) -> bool:
    return isinstance(value, numbers.Number) and not isinstance(value, bool) \
        and type(value).__name__ != "bool_"


def _is_whole(value: object) -> bool:
    if isinstance(value, Decimal):
        return value == value.to_integral_value()
    return float(value).is_integer()  # type: ignore[arg-type]


def _round_half_up(value: int, unit: int) -> int:
    return (value + unit // 2) // unit * unit


def publishable_count(value: int) -> int | str:
    """0 stays 0 and 1 to 10 is hidden. Anything else is an approximation: rounded to the nearest
    10 (at least 20), then to 3 significant figures (14,123 -> 14,100; 116,049,829 -> 116,000,000)."""
    if value == 0:
        return 0
    if 1 <= value <= 10:
        return HIDDEN
    rounded = max(SMALLEST_SHOWN, _round_half_up(value, ROUND_TO))
    return _round_half_up(rounded, 10 ** max(0, len(str(rounded)) - SIGNIFICANT_FIGURES))


def _decimals(name: str) -> int:
    return next(places for prefix, places in DERIVED_DECIMALS.items() if name.startswith(prefix))


def suppress(df: pd.DataFrame) -> pd.DataFrame:
    """Works on plain Python values, so pandas never turns a count column with a blank into
    floats and back. A value that is already "<11" (a CSV read back) stays hidden."""
    columns: dict[str, list[object]] = {}
    hidden_rows = [False] * len(df)
    for column in df.columns:
        name = str(column)
        values: list[object] = [None if v is None or (not isinstance(v, str) and pd.isna(v)) else v
                                for v in df[column].tolist()]
        for i, v in enumerate(values):
            if v == HIDDEN:
                hidden_rows[i] = True
        present = [v for v in values if v is not None and v != HIDDEN]
        is_count = (name not in LABEL_COLUMNS and not name.startswith(DERIVED_PREFIXES)
                    and bool(present) and all(_is_number(v) for v in present))
        if is_count:
            if not all(_is_whole(v) for v in present):
                raise UnsafeResultError(
                    f"Column {name!r} has fractions: name it pct_*, mean_*, smd* or lift, "
                    "or add it to LABEL_COLUMNS if it labels rows.")
            for i, v in enumerate(values):
                if v is None:
                    continue
                shown = HIDDEN if v == HIDDEN else publishable_count(int(v))  # type: ignore[call-overload]
                values[i] = shown
                hidden_rows[i] = hidden_rows[i] or shown == HIDDEN
        columns[name] = values
    for name, values in columns.items():
        if name.startswith(DERIVED_PREFIXES):
            places = _decimals(name)
            columns[name] = [None if hidden or v is None else round(float(v), places)  # type: ignore[arg-type]
                             for v, hidden in zip(values, hidden_rows)]
    return pd.DataFrame(columns, index=df.index, dtype=object)


def save(df: pd.DataFrame, path: Path) -> pd.DataFrame:
    """Apply the small-cell rule, write the CSV, and return what was written."""
    safe = suppress(df)
    path.parent.mkdir(parents=True, exist_ok=True)
    safe.to_csv(path, index=False)
    log.info("saved %s (%d rows)", path.as_posix(), len(safe))
    return safe


def _cell(text: str) -> object:
    if text == "":
        return None
    try:
        return int(text)
    except ValueError:
        pass
    try:
        return float(text)
    except ValueError:
        return text


def resuppress(path: Path) -> None:
    """Re-apply the rule to a CSV saved earlier, in place."""
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.reader(handle))
    if not rows:
        return
    df = pd.DataFrame([[_cell(v) for v in row] for row in rows[1:]], columns=pd.Index(rows[0]), dtype=object)
    suppress(df).to_csv(path, index=False)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    paths = sorted(RESULTS_DIR.glob("*/*/*.csv"))
    try:
        for path in paths:
            resuppress(path)
    except (UnsafeResultError, OSError, csv.Error) as error:
        log.error("%s", error)
        return 1
    log.info("re-applied the small-cell rule to %d result files", len(paths))
    return 0


if __name__ == "__main__":
    sys.exit(main())
