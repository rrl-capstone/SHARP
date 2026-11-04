"""The runner's orchestration, with the database replaced by a recorder."""
from __future__ import annotations

import dataclasses
import json
import os
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from runner import __main__ as run
from runner import config, steps


class FakeDb:
    def __init__(self, rows: dict[str, list[Any]]) -> None:
        self.rows = rows
        self.executed: list[str] = []

    def execute(self, conn: object, sql: str, label: str) -> None:
        self.executed.append(sql)

    def query(self, conn: object, sql: str, label: str) -> pd.DataFrame:
        return pd.DataFrame(self.rows)


def _step(path: str) -> steps.Step:
    return next(s for s in steps.STEPS if s.path == path)


def _run(monkeypatch: pytest.MonkeyPatch, fake: FakeDb, path: str, results_dir: Path,
         variables: dict[str, str]) -> None:
    monkeypatch.setattr(run.db, "execute", fake.execute)
    monkeypatch.setattr(run.db, "query", fake.query)
    conn: Any = object()
    run._run_sql_step(conn, config.load(), _step(path), variables, results_dir)


def test_a_per_year_statement_runs_once_for_each_study_year(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path, variables: dict[str, str]) -> None:
    fake = FakeDb({"analysis_year": [2016], "code_rows": [500], "distinct_codes": [40]})
    _run(monkeypatch, fake, "3_conditions/3_condition_dx_rows.sql", tmp_path, variables)
    inserts = [s for s in fake.executed if "INSERT INTO" in s]
    assert len(inserts) == 10
    assert "'2016-01-01'" in inserts[0] and "'2026-01-01'" in inserts[-1]


def test_results_are_saved_with_small_counts_hidden(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path, variables: dict[str, str]) -> None:
    fake = FakeDb({"analysis_year": [2016, 2017], "people": [4, 900],
                   "rows_total": [900, 900], "person_years": [900, 900]})
    _run(monkeypatch, fake, "1_cohort/03_demographics.sql", tmp_path, variables)
    saved = pd.read_csv(tmp_path / "1_cohort" / "eligible_by_year.csv", dtype=str)
    assert saved["people"].tolist() == ["<11", "900"]


def test_a_failed_expect_line_stops_the_run(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path, variables: dict[str, str]) -> None:
    fake = FakeDb({"analysis_year": [2016], "people": [900], "rows_total": [901], "person_years": [900]})
    with pytest.raises(run.CheckFailed, match="rows_total = person_years"):
        _run(monkeypatch, fake, "1_cohort/03_demographics.sql", tmp_path, variables)


def test_the_password_reaches_gagne_in_its_environment_not_its_command_line(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path, local_file: Path) -> None:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(run.subprocess, "run", lambda command, **kw: calls.append({"command": command, **kw}))
    run._run_script(config.load(), _step("5_gagne/gagne_1_evidence.py"), "s3cret", tmp_path)
    assert "s3cret" not in " ".join(calls[0]["command"])
    assert calls[0]["env"]["REDSHIFT_PASSWORD"] == "s3cret"
    assert calls[0]["env"]["SHARP_MATCH_RATIO"] == "1"
    assert "SHARP_BACKEND" not in calls[0]["env"]


def test_on_duckdb_gagne_gets_the_profile_file_and_the_runners_settings(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path, explorer_file: Path) -> None:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(run.subprocess, "run", lambda command, **kw: calls.append({"command": command, **kw}))
    monkeypatch.setenv("SLURM_CPUS_PER_TASK", "8")
    cfg = config.load(profile="sample_1pct")
    run._run_script(cfg, _step("5_gagne/gagne_1_evidence.py"), "", tmp_path)
    env = calls[0]["env"]
    assert env["SHARP_BACKEND"] == "duckdb" and env["SHARP_DUCKDB_FILE"] == cfg.duckdb_file
    assert json.loads(env["SHARP_DUCKDB_SETTINGS"])["threads"] == 8
    assert str(config.REPO_ROOT) in env["PYTHONPATH"].split(os.pathsep)


def test_file_11_inserts_values_on_redshift_and_a_dataframe_on_duckdb(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path, variables: dict[str, str]) -> None:
    ps_input = pd.DataFrame({"patient_id": ["a", "b", "c", "d"], "birth_year": [1950, 1950, 1951, 1951],
                             "patient_gender": ["M"] * 4, "census_region": ["South"] * 4,
                             "patient_race_ethnicity": ["WHITE"] * 4, "hiv": [1, 0, 1, 0]})
    executed: list[str] = []
    frames: list[pd.DataFrame] = []

    def query(conn: object, sql: str, label: str) -> pd.DataFrame:
        return pd.DataFrame({"analysis_year": [2016]}) if "DISTINCT" in sql else ps_input

    monkeypatch.setattr(run.db, "query", query)
    monkeypatch.setattr(run.db, "execute", lambda conn, sql, label: executed.append(sql))
    file_11 = steps.load_module(_step("4_matching/11_ps_matching.py"))
    monkeypatch.setattr(file_11.duckdb_backend, "insert_frame", lambda conn, table, frame: frames.append(frame))
    cfg = config.load()
    file_11.run(object(), cfg, variables, tmp_path)
    inserts = [s for s in executed if s.startswith("INSERT")]
    assert inserts == ["INSERT INTO work_test_user.ps_matched_s1 VALUES (2016, '2016-12-31', '2016-1', 'a', 1, 1.0),"
                       "(2016, '2016-12-31', '2016-1', 'b', 0, 1.0),(2016, '2016-12-31', '2016-2', 'c', 1, 1.0),"
                       "(2016, '2016-12-31', '2016-2', 'd', 0, 1.0)"]
    assert not frames
    executed.clear()
    file_11.run(object(), dataclasses.replace(cfg, backend="duckdb"), variables, tmp_path)
    assert not [s for s in executed if s.startswith("INSERT")]
    assert frames[0][["pair_id", "patient_id", "hiv"]].values.tolist() == [
        ["2016-1", "a", 1], ["2016-1", "b", 0], ["2016-2", "c", 1], ["2016-2", "d", 0]]


def test_each_steps_table_row_counts_go_to_the_parity_file(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path, variables: dict[str, str]) -> None:
    monkeypatch.setattr(run, "BUILD_DIR", tmp_path)
    fake = FakeDb({"n": [1234]})
    monkeypatch.setattr(run.db, "query", fake.query)
    conn: Any = object()
    cfg = config.load()
    run._record_parity(conn, cfg, _step("2_hiv_groups/06_hiv_rx.sql"), variables)
    run._record_parity(conn, cfg, _step("4_matching/12_matched_summaries.sql"), variables)   # builds nothing
    saved = json.loads((tmp_path / "parity" / "sample_1pct.json").read_text(encoding="utf-8"))
    assert saved["backend"] == "redshift"
    assert saved["row_counts"] == {"2_hiv_groups/06_hiv_rx.sql": {
        "hiv_rx_fills_all_s1": 1234, "hiv_rx_drug_names_s1": 1234, "hiv_rx_s1": 1234}}
