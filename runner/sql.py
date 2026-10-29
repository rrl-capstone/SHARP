"""Splits a step's SQL into statements and reads the comment lines the runner understands:

  -- result: <name>          the SELECT below is saved as results/<run>/<stage>/<name>.csv
  -- expect: a = b           stop the run unless column a equals column b (or a number) on every row
  -- for each year: study    run the statement once per study year, with ${year}, ${next_year}
  -- for each year: lookback same, from the measures look-back start to the last study year

Every SELECT must carry a result name, so every check a step prints is also kept.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from string import Template

import sqlparse

_RESULT = re.compile(r"^--\s*result:\s*(\S+)\s*$", re.MULTILINE)
_FOR_EACH_YEAR = re.compile(r"^--\s*for each year:\s*(\S+)\s*$", re.MULTILINE)
_EXPECT = re.compile(r"^--\s*expect:\s*([a-z][a-z0-9_]*)\s*=\s*([a-z][a-z0-9_]*|\d+)\s*$", re.MULTILINE)
_RESULT_NAME = re.compile(r"^[a-z][a-z0-9_]*$")
_YEAR_RANGES = ("study", "lookback")


class StepError(ValueError):
    """A step file the runner cannot use."""


@dataclass(frozen=True)
class Statement:
    text: str                  # not yet rendered: still holds ${variables}
    is_query: bool             # SELECT or WITH: returns rows
    result_name: str | None
    for_each_year: str | None  # None, "study" or "lookback"
    expect: tuple[str, str] | None = None  # (column, column or number)


def _first_keyword(text: str) -> str:
    code = "\n".join(line for line in text.splitlines() if not line.strip().startswith("--"))
    words = code.split()
    return words[0].upper().rstrip("(") if words else ""


def parse(sql_text: str, where: str) -> list[Statement]:
    statements = []
    for chunk in sqlparse.split(sql_text):
        if not _first_keyword(chunk):
            continue  # comments only
        names = _RESULT.findall(chunk)
        years = _FOR_EACH_YEAR.findall(chunk)
        expects = _EXPECT.findall(chunk)
        is_query = _first_keyword(chunk) in ("SELECT", "WITH")
        if len(names) > 1 or len(years) > 1:
            raise StepError(f"{where}: one statement has two result or year lines.")
        name = names[0] if names else None
        if is_query and name is None:
            raise StepError(f"{where}: every SELECT needs a '-- result: <name>' line above it.\n{chunk[:200]}")
        if name is not None and (not is_query or not _RESULT_NAME.match(name)):
            raise StepError(f"{where}: result {name!r} must name a SELECT, in lowercase words with _.")
        if years and years[0] not in _YEAR_RANGES:
            raise StepError(f"{where}: '-- for each year:' must be one of {_YEAR_RANGES}.")
        if years and is_query:
            raise StepError(f"{where}: '-- for each year:' is for INSERT statements, not SELECTs.")
        if expects and (len(expects) > 1 or not is_query):
            raise StepError(f"{where}: one '-- expect: a = b' line, above a SELECT.")
        if "-- expect:" in chunk and not expects:
            raise StepError(f"{where}: write expectations as '-- expect: column = column_or_number'.")
        statements.append(Statement(chunk.strip().rstrip(";").strip(), is_query, name,
                                    years[0] if years else None, expects[0] if expects else None))
    return statements


def render(text: str, variables: dict[str, str], where: str) -> str:
    try:
        return Template(text).substitute(variables)
    except KeyError as missing:
        raise StepError(f"{where}: unknown variable ${{{missing.args[0]}}}.") from missing
    except ValueError as bad:
        raise StepError(f"{where}: a '$' that is not a ${{variable}}: {bad}") from bad
