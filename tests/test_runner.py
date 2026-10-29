"""The runner's orchestration, with the database replaced by a recorder."""
from __future__ import annotations

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


def test_the_password_reaches_r_in_its_environment_not_its_command_line(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path, local_file: Path) -> None:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(run.subprocess, "run", lambda command, **kw: calls.append({"command": command, **kw}))
    run._run_script(config.load(), _step("4_matching/11_ps_matching.R"), "s3cret", tmp_path)
    assert "s3cret" not in " ".join(calls[0]["command"])
    assert calls[0]["env"]["REDSHIFT_PASSWORD"] == "s3cret"
    assert calls[0]["env"]["SHARP_MATCH_RATIO"] == "1"
