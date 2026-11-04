"""Redshift SQL to DuckDB SQL: the rewrites this pipeline needs, applied to rendered statements.

The step files stay in Redshift SQL. On the DuckDB backend (Explorer) every statement passes
through to_duckdb() just before it runs (runner/db.py, pipeline/5_gagne/gagne_config.py) or is
written out (--dry-run). Each rule below exists because the construct appears in a step:

  DISTKEY(...), SORTKEY(...), DISTSTYLE ALL   removed (Redshift's physical layout only)
  col ~* 'a|b'                                regexp_matches(col, 'a|b', 'i'): a case-insensitive
                                              partial match, like ~* (DuckDB's ~ is a full match)
  TO_DATE(x, 'YYYY-MM-DD')                    CAST(x AS DATE); any other format is refused
  ::FLOAT                                     ::DOUBLE (FLOAT is 8 bytes in Redshift, 4 in DuckDB)
  x IN ('a', 'b', 1)                          (x = 'a' OR x = 'b' OR x = 1), as the lab asks for
                                              DuckDB; IN (SELECT ...) is left alone

Everything else the steps use means the same in both (checked in tests/test_dialect.py and the
DuckDB end-to-end test). Behaviour that differs without any syntax to rewrite (integer
division, where NULLs sort) is set on the connection in runner/duckdb_backend.py.

String literals and comments are hidden before the rules run, so a quote inside a comment or an
"IN (" inside a value is never rewritten.
"""
from __future__ import annotations

import re

_HIDDEN = re.compile(r"'(?:[^']|'')*'|--[^\n]*|/\*.*?\*/", re.DOTALL)
_TOKEN = re.compile(r"\x00(\d+)\x00")
_LITERAL = r"(?:\x00\d+\x00|-?\d+(?:\.\d+)?)"
# The left side of IN: a column (a.b) or one function call without nesting (LEFT(dx_code, 3)).
_OPERAND = r"(?:\b[A-Za-z_]\w*\s*\([^()]*\)|\b[A-Za-z_][\w.]*)"

_PHYSICAL_LAYOUT = re.compile(
    r"\s*\b(?:DISTSTYLE\s+(?:ALL|EVEN|KEY|AUTO)\b|DISTKEY\s*\([^()]*\)"
    r"|(?:COMPOUND\s+|INTERLEAVED\s+)?SORTKEY\s*\([^()]*\))", re.IGNORECASE)
_FLOAT_CAST = re.compile(r"::\s*FLOAT\b", re.IGNORECASE)
_BARE_FLOAT = re.compile(r"\bFLOAT\b", re.IGNORECASE)
_REGEX_MATCH = re.compile(r"(?P<operand>\b[A-Za-z_][\w.]*)\s*~\*\s*(?P<pattern>\x00\d+\x00)")
_TO_DATE = re.compile(r"\bTO_DATE\s*\((?P<value>[^()]*?),\s*(?P<format>\x00\d+\x00)\s*\)", re.IGNORECASE)
_IN_LIST = re.compile(rf"(?P<operand>{_OPERAND})\s+IN\s*\(\s*(?P<items>{_LITERAL}(?:\s*,\s*{_LITERAL})*)\s*\)",
                      re.IGNORECASE)
_NOT_IN_LIST = re.compile(rf"\bNOT\s+IN\s*\(\s*{_LITERAL}", re.IGNORECASE)
_ITEM = re.compile(_LITERAL)
_BINDS_TIGHTER = frozenset("+-*/%|:^~&#")
_NOT_AN_OPERAND = frozenset({"END", "NOT", "NULL", "TRUE", "FALSE"})


class DialectError(ValueError):
    """A Redshift construct this module has no DuckDB rewrite for."""


def to_duckdb(sql: str) -> str:
    hidden: list[str] = []

    def hide(match: re.Match[str]) -> str:
        hidden.append(match.group(0))
        return f"\x00{len(hidden) - 1}\x00"

    def to_date(match: re.Match[str]) -> str:
        date_format = hidden[int(match["format"].strip("\x00"))]
        if date_format.upper() != "'YYYY-MM-DD'":
            raise DialectError(f"TO_DATE with format {date_format}: only 'YYYY-MM-DD' has a DuckDB rewrite.")
        return f"CAST({match['value'].strip()} AS DATE)"

    def or_chain(match: re.Match[str]) -> str:
        operand = match["operand"]
        before = match.string[:match.start()].rstrip()[-1:]
        # IN binds looser than arithmetic, || and ::, so in "a || b IN (...)" the left side is
        # "a || b", not "b". Refuse rather than rewrite the wrong operand.
        if before in _BINDS_TIGHTER or operand.upper() in _NOT_AN_OPERAND:
            raise DialectError(f"Cannot tell the left side of IN after {before + ' ' + operand!r}: "
                               "put the left side in a column or one function call.")
        return "(" + " OR ".join(f"{operand} = {item}" for item in _ITEM.findall(match["items"])) + ")"

    code = _HIDDEN.sub(hide, sql)
    if _NOT_IN_LIST.search(code):
        raise DialectError("NOT IN with a list of values has no DuckDB rewrite here; add one to runner/dialect.py.")
    code = _PHYSICAL_LAYOUT.sub("", code)
    code = _FLOAT_CAST.sub("::DOUBLE", code)
    if _BARE_FLOAT.search(code):
        raise DialectError("FLOAT is 8 bytes in Redshift and 4 in DuckDB: write FLOAT8 or ::FLOAT.")
    code = _REGEX_MATCH.sub(lambda m: f"regexp_matches({m['operand']}, {m['pattern']}, 'i')", code)
    code = _TO_DATE.sub(to_date, code)
    code = _IN_LIST.sub(or_chain, code)
    return _TOKEN.sub(lambda m: hidden[int(m.group(1))], code)
