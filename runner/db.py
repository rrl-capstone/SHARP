"""The Redshift connection. Komodo's tables are Redshift Spectrum tables (Parquet files in S3),
and Spectrum gives each scan a time limit, so a statement that times out is retried."""
from __future__ import annotations

import getpass
import logging
import os
import time

import pandas as pd
import redshift_connector

from runner.config import Config

log = logging.getLogger(__name__)

PASSWORD_ENV = "REDSHIFT_PASSWORD"
RETRYABLE = ("Spectrum Scan Error", "timed out", "Retries exceeded")
ATTEMPTS = 3
WAIT_SECONDS = 60


def password() -> str:
    """From REDSHIFT_PASSWORD if set, otherwise asked for once. Never stored or logged."""
    return os.environ.get(PASSWORD_ENV) or getpass.getpass("Redshift password: ")


def connect(cfg: Config, secret: str) -> redshift_connector.Connection:
    conn = redshift_connector.connect(host=cfg.host, port=cfg.port, database=cfg.database,
                                      user=cfg.redshift_user, password=secret)
    conn.autocommit = True  # each statement is saved when it finishes, as in DBeaver
    return conn


def _with_retry(conn: redshift_connector.Connection, sql: str, label: str,
                fetch: bool) -> pd.DataFrame | None:
    for attempt in range(1, ATTEMPTS + 1):
        cursor = conn.cursor()
        try:
            cursor.execute(sql)
            if not fetch:
                return None
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


def execute(conn: redshift_connector.Connection, sql: str, label: str) -> None:
    _with_retry(conn, sql, label, fetch=False)


def query(conn: redshift_connector.Connection, sql: str, label: str) -> pd.DataFrame:
    result = _with_retry(conn, sql, label, fetch=True)
    assert result is not None
    return result
