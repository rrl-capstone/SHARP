"""The database connection: Redshift (the lab workspace) or DuckDB (Explorer, runner/duckdb_backend.py).

Komodo's Redshift tables are Redshift Spectrum tables (Parquet files in S3), and Spectrum gives
each scan a time limit, so a Redshift statement that times out is retried. On DuckDB every
statement is translated from Redshift SQL first (runner/dialect.py)."""
from __future__ import annotations

import getpass
import logging
import os
import time
from typing import TYPE_CHECKING, Union

import pandas as pd
import redshift_connector

from runner import dialect, duckdb_backend
from runner.config import Config

if TYPE_CHECKING:
    import duckdb

log = logging.getLogger(__name__)

Connection = Union[redshift_connector.Connection, "duckdb.DuckDBPyConnection"]

PASSWORD_ENV = "REDSHIFT_PASSWORD"
RETRYABLE = ("Spectrum Scan Error", "timed out", "Retries exceeded")
ATTEMPTS = 3
WAIT_SECONDS = 60


def password() -> str:
    """From REDSHIFT_PASSWORD if set, otherwise asked for once. Never stored or logged."""
    return os.environ.get(PASSWORD_ENV) or getpass.getpass("Redshift password: ")


def connect(cfg: Config, secret: str) -> Connection:
    if cfg.backend == "duckdb":
        return duckdb_backend.connect(cfg)
    conn = redshift_connector.connect(host=cfg.host, port=cfg.port, database=cfg.database,
                                      user=cfg.redshift_user, password=secret)
    conn.autocommit = True  # each statement is saved when it finishes, as in DBeaver
    return conn


def errors(cfg: Config) -> tuple[type[Exception], ...]:
    """The driver errors a step can raise, for the runner to report and stop on."""
    if cfg.backend == "duckdb":
        import duckdb

        return (redshift_connector.Error, duckdb.Error)
    return (redshift_connector.Error,)


def _with_retry(conn: Connection, sql: str, label: str, fetch: bool) -> pd.DataFrame | None:
    if duckdb_backend.is_duckdb(conn):
        sql = dialect.to_duckdb(sql)
    for attempt in range(1, ATTEMPTS + 1):
        cursor = conn.cursor()
        try:
            cursor.execute(sql)
            if not fetch:
                return None
            assert cursor.description is not None
            columns = [c[0] for c in cursor.description]
            return pd.DataFrame(cursor.fetchall(), columns=pd.Index(columns))
        except redshift_connector.Error as error:
            if attempt == ATTEMPTS or not any(k in str(error) for k in RETRYABLE):
                raise
            wait = WAIT_SECONDS * attempt
            log.warning("%s: Spectrum timed out (attempt %d of %d), retrying in %d s",
                        label, attempt, ATTEMPTS, wait)
            time.sleep(wait)
        finally:
            cursor.close()
    return None


def execute(conn: Connection, sql: str, label: str) -> None:
    _with_retry(conn, sql, label, fetch=False)


def query(conn: Connection, sql: str, label: str) -> pd.DataFrame:
    result = _with_retry(conn, sql, label, fetch=True)
    assert result is not None
    return result
