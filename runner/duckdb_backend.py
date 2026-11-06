"""The DuckDB backend, for Explorer: the same steps on Komodo's parquet files.

  <extracts_dir>/sharp_<profile>.duckdb   the work schema: patient-level tables, never copied out.
                                          One file per profile, so the three can run at once.
  komodo_<snapshot>.<table>               a view over <komodo_root>/<snapshot>/<table>/<table>_*.parquet
                                          with every column name in lower case (DuckDB keeps the
                                          parquet's upper case, which would reach result headers and
                                          pandas). Only files named after the table are read, so a
                                          stray extract saved into a table folder is ignored.
  komodo_<snapshot>.normalized_dx_events  Redshift has it as a table, the parquet snapshot does not.
                                          Built from the two event tables (dx_query): first as a view
                                          over all patients, then, before the first step that needs
                                          it, materialized ONCE per profile as
                                          <work_schema>.dx_events_<snapshot><suffix> with the
                                          profile's sample filter applied to the raw event rows
                                          before the arrays are unnested; the view then reads that
                                          table. Without this, every step that reads diagnoses would
                                          unnest every patient's arrays again.

The step SQL is translated by runner/dialect.py. Behaviour that differs without any syntax to
rewrite is set on the connection here, so DuckDB answers as Redshift does: integer division,
and NULLs last when sorting ascending but first when descending.

DuckDB allows one writer per file: the runner closes its connection before each Gagne script
(its own process, opening the same file) and reopens it after. Views are stored in the file, so
the Gagne scripts see the same normalized_dx_events.
"""
from __future__ import annotations

import logging
import os
import sys
import tempfile
import time
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Union

import pandas as pd

from runner.config import Config, ConfigError, sql_quote

if TYPE_CHECKING:
    import duckdb

log = logging.getLogger("runner")

KOMODO_TABLES = ("inpatient_events", "non_inpatient_events", "patient_closed", "patient_demographics",
                 "patient_geography", "patient_insurance", "patient_mortality", "patient_race_ethnicity",
                 "pharmacy_events")
DX_VIEW = "normalized_dx_events"

# Every Komodo column a step or the diagnosis view reads. DATE where the SQL does date arithmetic
# or EXTRACT(YEAR ...), or compares with a date: --check stops if the parquet type is anything else.
REQUIRED_COLUMNS: dict[str, dict[str, str | None]] = {
    "patient_demographics": {"patient_id": None, "patient_dob": "DATE", "patient_gender": None},
    "patient_mortality": {"patient_id": None, "patient_death_date": "DATE"},
    "patient_closed": {"patient_id": None, "closed_type": None, "closed_start_date": "DATE",
                       "closed_end_date": "DATE"},
    "patient_insurance": {"patient_id": None, "row_valid_start": "DATE", "row_valid_end": "DATE",
                          "mx_payer_id": None, "rx_payer_id": None},
    "patient_geography": {"patient_id": None, "patient_state": None, "valid_from_date": "DATE",
                          "valid_to_date": "DATE"},
    "patient_race_ethnicity": {"patient_id": None, "patient_race_ethnicity": None},
    "inpatient_events": {"patient_id": None, "utilization_id": None, "admit_date": "DATE", "drg_code": None,
                         "admission_diagnosis_code": None, "primary_diagnosis_code": None,
                         "secondary_diagnosis_codes": None},
    "non_inpatient_events": {"patient_id": None, "utilization_id": None, "service_date": "DATE",
                             "procedure_code": None, "primary_diagnosis_code_array": None,
                             "diagnosis_codes": None},
    "pharmacy_events": {"patient_id": None, "fill_date": "DATE", "generic_name": None, "brand_name": None,
                        "transaction_status": None, "transaction_result": None},
}
DX_VIEW_COLUMNS = {"patient_id": None, "dx_code": "VARCHAR", "event_date": "DATE", "source_table": "VARCHAR"}

Setting = Union[str, bool, int, float, list[str]]
NULL_ORDER = "nulls_last_on_asc_first_on_desc"   # Redshift: NULLS LAST on ASC, NULLS FIRST on DESC
DEFAULT_THREADS = 4
MEMORY_SHARE = 0.85
_INSERT_VIEW = "sharp_insert_rows"


def _slurm_number(environ: Mapping[str, str], name: str) -> int | None:
    value = environ.get(name)
    if value is None or value == "":
        return None
    if not value.isdigit():
        raise ConfigError(f"{name}={value!r} is not a whole number.")
    return int(value)


def resource_settings(cfg: Config, environ: Mapping[str, str] = os.environ) -> dict[str, Setting]:
    """DuckDB settings for every connection to the profile's file (runner and Gagne scripts).
    Threads and memory follow the Slurm allocation unless config/explorer.yml sets them."""
    settings: dict[str, Setting] = {
        "threads": cfg.duckdb_threads or _slurm_number(environ, "SLURM_CPUS_PER_TASK") or DEFAULT_THREADS,
        "temp_directory": cfg.duckdb_temp_directory,
        "preserve_insertion_order": False,
        "default_null_order": NULL_ORDER,
        "integer_division": True,
        "autoinstall_known_extensions": False,
        # Least privilege: once open_file() turns external access off, queries may read and write
        # files only under these folders.
        "allowed_directories": [f"{d}/" for d in dict.fromkeys((cfg.komodo_root, cfg.extracts_dir, cfg.duckdb_temp_root))],
    }
    memory_mb = _slurm_number(environ, "SLURM_MEM_PER_NODE")   # Slurm reports MB (2**20 bytes)
    if cfg.duckdb_memory_limit:
        settings["memory_limit"] = cfg.duckdb_memory_limit
    elif memory_mb:
        settings["memory_limit"] = f"{int(memory_mb * MEMORY_SHARE)}MiB"
    return settings


def _identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _table_folder(cfg: Config, table: str) -> Path:
    return Path(cfg.komodo_root, cfg.snapshot, table)


def _table_pattern(table: str) -> str:
    """Komodo's own files are named <table>_<n>_<n>_<n>.snappy.parquet. Anything else in the folder
    (someone's saved extract, for example) has a different schema and must not be read."""
    return f"{table}_*.parquet"


def _parquet(cfg: Config, table: str) -> str:
    return f"read_parquet({sql_quote(f'{cfg.komodo_root}/{cfg.snapshot}/{table}/{_table_pattern(table)}')})"


def stray_files(cfg: Config, table: str) -> list[str]:
    """Parquet files in a table's folder that the view does not read (names only, never opened)."""
    folder = _table_folder(cfg, table)
    if not folder.is_dir():
        return []
    every = {f.name for f in folder.glob("*.parquet")}
    ours = {f.name for f in folder.glob(_table_pattern(table))}
    return sorted(every - ours)


def table_view_sql(conn: duckdb.DuckDBPyConnection, cfg: Config, table: str) -> str:
    """The view of one Komodo table, every column renamed to lower case. Reads only the parquet
    schema (DESCRIBE), never rows."""
    columns = [str(row[0]) for row in conn.execute(f"DESCRIBE SELECT * FROM {_parquet(cfg, table)}").fetchall()]
    lowered = [c.lower() for c in columns]
    if len(set(lowered)) != len(lowered):
        raise ConfigError(f"{table}: two parquet columns differ only by case.")
    select = ", ".join(f"{_identifier(c)} AS {_identifier(c.lower())}" for c in columns)
    return f"CREATE OR REPLACE VIEW {cfg.komodo_schema}.{table} AS SELECT {select} FROM {_parquet(cfg, table)}"


def dx_query(komodo_schema: str, patient_filter: str = "TRUE") -> str:
    """normalized_dx_events from the parquet event tables: one row per patient, claim
    (utilization_id), diagnosis code and date, with the columns the steps read (patient_id,
    dx_code, event_date, source_table) plus utilization_id and dx_position.

      inpatient_events      one row per stay, dated ADMIT_DATE: ADMISSION_DIAGNOSIS_CODE,
                            PRIMARY_DIAGNOSIS_CODE and the JSON array SECONDARY_DIAGNOSIS_CODES
      non_inpatient_events  one row per claim line, dated SERVICE_DATE: the JSON arrays
                            PRIMARY_DIAGNOSIS_CODE_ARRAY and DIAGNOSIS_CODES. Lines of one claim on
                            the same date collapse to one row per code.

    patient_filter is applied to the raw event rows, before any array is unnested (the profile's
    MD5 sample filter when materializing; TRUE for the all-patients view).
    Arrays are parsed as JSON; NULL and [] give no rows. Codes are trimmed and upper-cased, and
    empty codes dropped. A code found in more than one place on the same claim and date is one
    row, with the most important position: primary, then admission, then secondary or other.
    UNNEST sits in the select list (not FROM t, UNNEST(...)) so DuckDB unnests in place instead of
    joining on the JSON text."""
    k = komodo_schema
    w = f"WHERE {patient_filter}"
    return f"""WITH coded AS (
    SELECT patient_id, utilization_id, admit_date AS event_date, 'INPATIENT_EVENTS' AS source_table,
           'primary' AS dx_position, 1 AS position_rank, primary_diagnosis_code AS code
    FROM {k}.inpatient_events {w}
    UNION ALL
    SELECT patient_id, utilization_id, admit_date, 'INPATIENT_EVENTS', 'admission', 2, admission_diagnosis_code
    FROM {k}.inpatient_events {w}
    UNION ALL
    SELECT patient_id, utilization_id, admit_date, 'INPATIENT_EVENTS', 'secondary', 3,
           UNNEST(from_json(secondary_diagnosis_codes, '["VARCHAR"]'))
    FROM {k}.inpatient_events {w}
    UNION ALL
    SELECT patient_id, utilization_id, service_date, 'NON_INPATIENT_EVENTS', 'primary', 1,
           UNNEST(from_json(primary_diagnosis_code_array, '["VARCHAR"]'))
    FROM {k}.non_inpatient_events {w}
    UNION ALL
    SELECT patient_id, utilization_id, service_date, 'NON_INPATIENT_EVENTS', 'other', 4,
           UNNEST(from_json(diagnosis_codes, '["VARCHAR"]'))
    FROM {k}.non_inpatient_events {w}
),
cleaned AS (
    SELECT patient_id, utilization_id, UPPER(TRIM(code)) AS dx_code, event_date, source_table,
           dx_position, position_rank
    FROM coded
)
SELECT patient_id, utilization_id, dx_code, event_date, source_table,
       arg_min(dx_position, position_rank) AS dx_position
FROM cleaned
WHERE dx_code <> ''
GROUP BY patient_id, utilization_id, dx_code, event_date, source_table"""


def normalized_dx_view_sql(komodo_schema: str) -> str:
    """The all-patients diagnosis view (used by --check, and until the profile's table exists)."""
    return f"CREATE OR REPLACE VIEW {komodo_schema}.{DX_VIEW} AS\n{dx_query(komodo_schema)}"


def dx_table_name(cfg: Config) -> str:
    """The profile's materialized diagnosis table, e.g. dx_events_202610_s1 (no schema)."""
    return f"dx_events_{cfg.snapshot}{cfg.table_suffix}"


def _dx_table_exists(conn: duckdb.DuckDBPyConnection, cfg: Config) -> bool:
    row = conn.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = ? AND table_name = ?",
                       [cfg.work_schema, dx_table_name(cfg)]).fetchone()
    return bool(row and row[0])


def _point_view_at_table(conn: duckdb.DuckDBPyConnection, cfg: Config) -> None:
    conn.execute(f"CREATE OR REPLACE VIEW {cfg.komodo_schema}.{DX_VIEW} AS "
                 f"SELECT * FROM {cfg.work_schema}.{dx_table_name(cfg)}")


def ensure_dx_table(conn: object, cfg: Config, rebuild: bool = False) -> None:
    """Build the profile's diagnosis table once (or again with rebuild) and point
    normalized_dx_events at it. The sample filter runs on the raw event rows, so a 1% profile
    unnests about 1% of the arrays. Logs counts and time only, never rows."""
    import duckdb

    assert isinstance(conn, duckdb.DuckDBPyConnection)
    table = f"{cfg.work_schema}.{dx_table_name(cfg)}"
    if rebuild or not _dx_table_exists(conn, cfg):
        log.info("BUILD %s (diagnoses of the %s people, once; later steps read it)", table, cfg.profile)
        began = time.monotonic()
        conn.execute(f"DROP TABLE IF EXISTS {table}")
        conn.execute(f"CREATE TABLE {table} AS\n{dx_query(cfg.komodo_schema, cfg.sample_filter)}")
        row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
        log.info("BUILT %s: %s rows in %s", table, f"{row[0]:,}" if row else "?", elapsed(time.monotonic() - began))
    _point_view_at_table(conn, cfg)


def elapsed(seconds: float) -> str:
    minutes, secs = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h{minutes:02d}m{secs:02d}s" if hours else f"{minutes}m{secs:02d}s"


def open_file(path: str, settings: Mapping[str, Setting]) -> duckdb.DuckDBPyConnection:
    """A connection with resource_settings(), for the runner and the Gagne scripts alike. DuckDB
    takes allowed_directories only once the database has started, and with external access off
    no folder setting can change, so both are applied here, in that order, after connecting.
    External access cannot be turned back on for this connection."""
    import duckdb

    startup = dict(settings)
    folders = startup.pop("allowed_directories")
    assert isinstance(folders, list)
    conn = duckdb.connect(path, config=startup)
    conn.execute(f"SET allowed_directories = [{', '.join(sql_quote(str(f)) for f in folders)}]")
    conn.execute("SET enable_external_access = false")
    return conn


def open_database(cfg: Config) -> duckdb.DuckDBPyConnection:
    """The profile's file with its two schemas, before any Komodo view exists."""
    Path(cfg.duckdb_temp_directory).mkdir(parents=True, exist_ok=True)
    conn = open_file(cfg.duckdb_file, resource_settings(cfg))
    conn.execute(f"CREATE SCHEMA IF NOT EXISTS {cfg.work_schema}")   # identifiers validated in config.load
    conn.execute(f"CREATE SCHEMA IF NOT EXISTS {cfg.komodo_schema}")
    return conn


def connect(cfg: Config) -> duckdb.DuckDBPyConnection:
    """Open the profile's file and (re)create the Komodo views, so a changed snapshot or folder
    in config/explorer.yml takes effect. normalized_dx_events reads the profile's materialized
    table when it exists, otherwise all patients (until ensure_dx_table builds the table)."""
    conn = open_database(cfg)
    for table in KOMODO_TABLES:
        conn.execute(table_view_sql(conn, cfg, table))
    if _dx_table_exists(conn, cfg):
        _point_view_at_table(conn, cfg)
    else:
        conn.execute(normalized_dx_view_sql(cfg.komodo_schema))
    return conn


def is_duckdb(conn: object) -> bool:
    module = sys.modules.get("duckdb")   # not imported means not a DuckDB connection
    return module is not None and isinstance(conn, module.DuckDBPyConnection)


def insert_frame(conn: object, table: str, frame: pd.DataFrame) -> None:
    """INSERT a DataFrame by column name, without writing its values into SQL text."""
    if frame.empty:
        return
    import duckdb

    assert isinstance(conn, duckdb.DuckDBPyConnection)
    conn.register(_INSERT_VIEW, frame)
    try:
        conn.execute(f"INSERT INTO {table} BY NAME SELECT * FROM {_INSERT_VIEW}")
    finally:
        conn.unregister(_INSERT_VIEW)


def column_problems(conn: duckdb.DuckDBPyConnection, schema: str, table: str,
                    required: dict[str, str | None]) -> list[str]:
    """Missing columns, and date columns of another type, from the view's schema (no rows)."""
    found = {str(row[0]): str(row[1]) for row in conn.execute(f"DESCRIBE {schema}.{table}").fetchall()}
    problems = []
    for column, wanted in required.items():
        if column not in found:
            problems.append(f"{table}.{column}: not in the parquet files (the steps read it)")
        elif wanted and found[column] != wanted:
            problems.append(f"{table}.{column}: is {found[column]}, the steps need {wanted}")
    return problems


def _writable(folder: str) -> str | None:
    try:
        Path(folder).mkdir(parents=True, exist_ok=True)
        handle, probe = tempfile.mkstemp(dir=folder)
        os.close(handle)
        os.unlink(probe)
    except OSError as error:
        return f"{folder}: not writable ({error.strerror})"
    return None


def check(cfg: Config) -> list[str]:
    """--check: the parquet folders, the writable folders, the profile's file, and every column
    the steps read with its type. Reads file permissions and parquet schemas only, never rows.
    Returns the problems found (none: ready to run). Stray files in a table folder are printed
    as warnings, not problems: the views do not read them."""
    import duckdb

    problems = []
    for table in KOMODO_TABLES:
        folder = _table_folder(cfg, table)
        files = sorted(folder.glob(_table_pattern(table))) if folder.is_dir() else []
        if not files:
            problems.append(f"{folder.as_posix()}: no {_table_pattern(table)} files")
        elif unreadable := sum(not os.access(f, os.R_OK) for f in files):
            problems.append(f"{folder.as_posix()}: {unreadable} of {len(files)} .parquet files are not readable")
        if stray := stray_files(cfg, table):
            print(f"check: warning: {folder.as_posix()}: ignoring {len(stray)} file(s) not named "
                  f"{_table_pattern(table)}: {', '.join(stray)}", file=sys.stderr)
    problems += [p for p in (_writable(cfg.extracts_dir), _writable(cfg.duckdb_temp_directory)) if p]
    if problems:
        return problems
    try:
        conn = open_database(cfg)
    except duckdb.Error as error:
        return [f"{cfg.duckdb_file}: cannot open it ({error}). Is another run of {cfg.profile} using it?"]
    try:
        for table in KOMODO_TABLES:
            try:
                conn.execute(table_view_sql(conn, cfg, table))
            except duckdb.Error as error:
                problems.append(f"{table}: cannot read the parquet schema ({error})")
                continue
            problems += column_problems(conn, cfg.komodo_schema, table, REQUIRED_COLUMNS[table])
        if not problems:
            if _dx_table_exists(conn, cfg):
                _point_view_at_table(conn, cfg)
            else:
                conn.execute(normalized_dx_view_sql(cfg.komodo_schema))
            problems += column_problems(conn, cfg.komodo_schema, DX_VIEW, DX_VIEW_COLUMNS)
    except duckdb.Error as error:
        problems.append(f"{DX_VIEW}: {error}")
    finally:
        conn.close()
    return problems