"""The DuckDB backend (runner/duckdb_backend.py) on made-up values only: no Komodo data."""
from __future__ import annotations

import datetime
from typing import Any
from pathlib import Path

import pandas as pd
import pytest

from runner import config, duckdb_backend

duckdb = pytest.importorskip("duckdb")


def _cfg() -> config.Config:
    return config.load(profile="sample_1pct")


def test_threads_and_memory_follow_slurm_unless_explorer_yml_sets_them(explorer_file: Path) -> None:
    cfg = config.load()
    slurm = duckdb_backend.resource_settings(cfg, {"SLURM_CPUS_PER_TASK": "8", "SLURM_MEM_PER_NODE": "65536"})
    assert slurm["threads"] == 8 and slurm["memory_limit"] == "55705MiB"   # 85% of 64 GiB
    outside = duckdb_backend.resource_settings(cfg, {})
    assert outside["threads"] == 4 and "memory_limit" not in outside
    assert outside["temp_directory"] == "/projects/OHDSI_Lab/extracts/your_project_dir/duckdb_tmp/sample_1pct"
    assert outside["preserve_insertion_order"] is False
    explorer_file.write_text(explorer_file.read_text(encoding="utf-8")
                             .replace("# threads: 8", "threads: 2").replace("# memory_limit: 48GB", "memory_limit: 48GB"),
                             encoding="utf-8")
    fixed = duckdb_backend.resource_settings(config.load(), {"SLURM_CPUS_PER_TASK": "8", "SLURM_MEM_PER_NODE": "65536"})
    assert fixed["threads"] == 2 and fixed["memory_limit"] == "48GB"
    with pytest.raises(config.ConfigError, match="SLURM_MEM_PER_NODE"):
        duckdb_backend.resource_settings(cfg, {"SLURM_MEM_PER_NODE": "64G"})


def _connection(tmp_path: Path) -> Any:
    settings = {"threads": 1, "temp_directory": (tmp_path / "tmp").as_posix(), "default_null_order": duckdb_backend.NULL_ORDER,
                "integer_division": True, "preserve_insertion_order": False, "autoinstall_known_extensions": False,
                "allowed_directories": [tmp_path.as_posix() + "/"]}
    return duckdb_backend.open_file(":memory:", settings)


def test_nulls_sort_last_ascending_and_first_descending_as_in_redshift(tmp_path: Path) -> None:
    conn = _connection(tmp_path)
    values = "(VALUES (1), (NULL), (2)) t(x)"
    assert conn.execute(f"SELECT x FROM {values} ORDER BY x").fetchall() == [(1,), (2,), (None,)]
    assert conn.execute(f"SELECT x FROM {values} ORDER BY x DESC").fetchall() == [(None,), (2,), (1,)]
    ranked = conn.execute(f"SELECT x, ROW_NUMBER() OVER (ORDER BY x DESC) FROM {values} ORDER BY 2").fetchall()
    assert ranked == [(None, 1), (2, 2), (1, 3)]


def test_integers_divide_as_in_redshift_and_files_outside_the_allowed_folders_are_refused(tmp_path: Path) -> None:
    conn = _connection(tmp_path)
    assert conn.execute("SELECT 7 / 2, 100.0 * 7 / 8").fetchall() == [(3, 87.5)]
    outside = tmp_path.parent / "outside.csv"
    with pytest.raises(duckdb.PermissionException):
        conn.execute(f"SELECT * FROM read_csv('{outside.as_posix()}')")


def _dx_view(tmp_path: Path, inpatient: list[tuple], non_inpatient: list[tuple]) -> list[tuple]:
    conn = _connection(tmp_path)
    conn.execute("CREATE SCHEMA k")
    conn.execute("CREATE TABLE k.inpatient_events (patient_id VARCHAR, utilization_id VARCHAR, admit_date DATE, "
                 "admission_diagnosis_code VARCHAR, primary_diagnosis_code VARCHAR, secondary_diagnosis_codes VARCHAR)")
    conn.execute("CREATE TABLE k.non_inpatient_events (patient_id VARCHAR, utilization_id VARCHAR, line_number INT, "
                 "service_date DATE, primary_diagnosis_code_array VARCHAR, diagnosis_codes VARCHAR)")
    if inpatient:
        conn.executemany("INSERT INTO k.inpatient_events VALUES (?, ?, ?, ?, ?, ?)", inpatient)
    if non_inpatient:
        conn.executemany("INSERT INTO k.non_inpatient_events VALUES (?, ?, ?, ?, ?, ?)", non_inpatient)
    conn.execute(duckdb_backend.normalized_dx_view_sql("k"))
    types = {row[0]: row[1] for row in conn.execute("DESCRIBE k.normalized_dx_events").fetchall()}
    assert types == {"patient_id": "VARCHAR", "utilization_id": "VARCHAR", "dx_code": "VARCHAR",
                     "event_date": "DATE", "source_table": "VARCHAR", "dx_position": "VARCHAR"}
    return conn.execute("SELECT patient_id, utilization_id, dx_code, event_date, source_table, dx_position "
                        "FROM k.normalized_dx_events ORDER BY ALL").fetchall()


MARCH = datetime.date(2020, 3, 1)


def test_diagnosis_arrays_are_parsed_as_json_and_empty_or_null_arrays_give_no_rows(tmp_path: Path) -> None:
    rows = _dx_view(tmp_path, [], [
        ("p1", "c1", 1, MARCH, '["E119"]', '["I10","E785"]'),
        ("p2", "c2", 1, MARCH, None, "[]"),
        ("p3", "c3", 1, MARCH, '["E119","I10"]', "[]"),          # more than one primary code
        ("p4", "c4", 1, MARCH, '[" e119 ", ""]', "[]"),           # trimmed, upper-cased, empty dropped
    ])
    assert rows == [
        ("p1", "c1", "E119", MARCH, "NON_INPATIENT_EVENTS", "primary"),
        ("p1", "c1", "E785", MARCH, "NON_INPATIENT_EVENTS", "other"),
        ("p1", "c1", "I10", MARCH, "NON_INPATIENT_EVENTS", "other"),
        ("p3", "c3", "E119", MARCH, "NON_INPATIENT_EVENTS", "primary"),
        ("p3", "c3", "I10", MARCH, "NON_INPATIENT_EVENTS", "primary"),
        ("p4", "c4", "E119", MARCH, "NON_INPATIENT_EVENTS", "primary"),
    ]


def test_a_code_repeated_across_lines_or_in_both_arrays_is_one_row_flagged_primary(tmp_path: Path) -> None:
    september = datetime.date(2020, 9, 1)
    rows = _dx_view(tmp_path, [], [
        ("p1", "c1", 1, MARCH, None, '["I10"]'),
        ("p1", "c1", 2, MARCH, '["I10"]', '["I10"]'),
        ("p1", "c1", 3, MARCH, None, '["I10"]'),
        ("p1", "c1", 4, september, None, '["I10"]'),   # another date on the same claim: its own row
    ])
    assert rows == [("p1", "c1", "I10", MARCH, "NON_INPATIENT_EVENTS", "primary"),
                    ("p1", "c1", "I10", september, "NON_INPATIENT_EVENTS", "other")]


def test_inpatient_codes_are_dated_on_admission_with_their_position(tmp_path: Path) -> None:
    rows = _dx_view(tmp_path, [
        ("p1", "s1", MARCH, "R509", "B20", '["I10","B20"]'),
        ("p2", "s2", MARCH, None, None, None),
    ], [])
    assert rows == [("p1", "s1", "B20", MARCH, "INPATIENT_EVENTS", "primary"),
                    ("p1", "s1", "I10", MARCH, "INPATIENT_EVENTS", "secondary"),
                    ("p1", "s1", "R509", MARCH, "INPATIENT_EVENTS", "admission")]


def test_komodo_views_have_lower_case_columns(synthetic_explorer: Path, komodo_root: Path) -> None:
    conn = duckdb_backend.connect(_cfg())
    names = [c[0] for c in conn.execute("SELECT * FROM komodo_202606.patient_demographics LIMIT 0").description]
    assert names == ["patient_id", "patient_dob", "patient_gender"]
    conn.close()


def test_check_passes_on_a_complete_snapshot(synthetic_explorer: Path, komodo_root: Path) -> None:
    assert duckdb_backend.check(_cfg()) == []


def test_check_reports_a_missing_table_folder(synthetic_explorer: Path, komodo_root: Path) -> None:
    for parquet in (komodo_root / "202606" / "patient_insurance").iterdir():
        parquet.unlink()
    problems = duckdb_backend.check(_cfg())
    assert len(problems) == 1 and "patient_insurance: no .parquet files" in problems[0]


def test_check_reports_a_missing_column_and_a_date_that_is_not_a_date(
        synthetic_explorer: Path, komodo_root: Path) -> None:
    folder = komodo_root / "202606" / "patient_demographics"
    with duckdb.connect() as conn:
        conn.execute(f"COPY (SELECT 'P000' AS PATIENT_ID, 'M' AS PATIENT_GENDER) TO '{(folder / 'part0.parquet').as_posix()}'")
        folder = komodo_root / "202606" / "pharmacy_events"
        conn.execute(f"COPY (SELECT 'P000' AS PATIENT_ID, TIMESTAMP '2020-01-01' AS FILL_DATE, 'A' AS GENERIC_NAME, "
                     f"'B' AS BRAND_NAME, 'FINAL' AS TRANSACTION_STATUS, 'PAID' AS TRANSACTION_RESULT) "
                     f"TO '{(folder / 'part0.parquet').as_posix()}'")
    problems = duckdb_backend.check(_cfg())
    assert problems == ["patient_demographics.patient_dob: not in the parquet files (the steps read it)",
                        "pharmacy_events.fill_date: is TIMESTAMP, the steps need DATE"]


def test_a_dataframe_is_inserted_by_column_name(tmp_path: Path) -> None:
    conn = _connection(tmp_path)
    conn.execute("CREATE TABLE m (analysis_year INT, index_date DATE, patient_id VARCHAR, match_weight FLOAT8)")
    duckdb_backend.insert_frame(conn, "m", pd.DataFrame({
        "patient_id": ["p1"], "match_weight": [1.0], "index_date": [datetime.date(2016, 12, 31)], "analysis_year": [2016]}))
    duckdb_backend.insert_frame(conn, "m", pd.DataFrame())   # a year with no pairs
    assert conn.execute("SELECT * FROM m").fetchall() == [(2016, datetime.date(2016, 12, 31), "p1", 1.0)]
