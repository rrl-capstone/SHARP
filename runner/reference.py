"""Loads a code list from reference/ into a small Redshift table, so SQL steps can join to it.
Values are checked against a pattern per column before they are written into SQL."""
from __future__ import annotations

import re

from runner.config import ConfigError, read_reference, sql_quote

CONCEPT = re.compile(r"^[a-z][a-z0-9_]*$")


def table_statements(table: str, columns: dict[str, re.Pattern[str]],
                     rows: list[dict[str, str]], where: str) -> list[str]:
    """DROP, CREATE and INSERT for a reference table with VARCHAR columns. DISTSTYLE ALL keeps
    a full copy on every node, so joining to it never moves data around."""
    values = []
    for row in rows:
        for column, pattern in columns.items():
            if not pattern.match(row[column]):
                raise ConfigError(f"{where}: {column} {row[column]!r} is not allowed here.")
        values.append("(" + ", ".join(sql_quote(row[c]) for c in columns) + ")")
    if not values:
        raise ConfigError(f"{where}: no rows.")
    ddl = ", ".join(f"{c} VARCHAR(200)" for c in columns)
    return [f"DROP TABLE IF EXISTS ${{work_schema}}.{table}${{sfx}}",
            f"CREATE TABLE ${{work_schema}}.{table}${{sfx}} ({ddl}) DISTSTYLE ALL",
            f"INSERT INTO ${{work_schema}}.{table}${{sfx}} VALUES\n" + ",\n".join(values)]


def explode(file_name: str, list_column: str, item_name: str,
            keep: tuple[str, ...]) -> list[dict[str, str]]:
    """One row per item of a space-separated list column, e.g. one row per code prefix."""
    out = []
    for row in read_reference(file_name):
        if not CONCEPT.match(row["concept"]):
            raise ConfigError(f"{file_name}: concept {row['concept']!r} must be lowercase words with _.")
        for item in row[list_column].split():
            out.append({**{k: row[k] for k in keep}, item_name: item})
    return out

