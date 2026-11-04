"""The whole pipeline on DuckDB (the Explorer backend), on the made-up snapshot in conftest.py:
every step, File 11's matching and Rhea's Gagne scripts in their own processes. Proves the
translated SQL runs and the one-writer handoff works; says nothing about Komodo's real data."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from runner import __main__ as run
from runner import config, results

pytest.importorskip("duckdb")


def test_check_run_and_dry_run_work_end_to_end_on_duckdb(
        synthetic_explorer: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(run, "BUILD_DIR", tmp_path / "build")
    monkeypatch.setattr(results, "RESULTS_DIR", tmp_path / "results")
    monkeypatch.delenv("SLURM_CPUS_PER_TASK", raising=False)

    assert run.main(["--check", "--profile", "full"]) == 0
    assert run.main(["--profile", "full"]) == 0

    info = json.loads((tmp_path / "results" / "full" / "run_info.json").read_text(encoding="utf-8"))
    assert info["status"] == "complete" and info["backend"] == "duckdb" and info["komodo_schema"] == "komodo_202606"
    counts = json.loads((tmp_path / "build" / "parity" / "full.json").read_text(encoding="utf-8"))["row_counts"]
    assert counts["1_cohort/00_sample.sql"] == {"study_ids": 150}
    assert counts["2_hiv_groups/07_pwh_cohort.sql"] == {"pwh_all": 30, "pwh_cohort": 300}   # 30 people x 10 years
    matched = counts["4_matching/11_ps_matching.py"]["ps_matched"]
    assert matched > 0 and matched % 2 == 0
    assert counts["5_gagne/gagne_2_scores.py"] == {"gagne_scores": matched}

    by_rule = pd.read_csv(tmp_path / "results" / "full" / "2_hiv_groups" / "hiv_people_by_rule.csv")
    assert by_rule.to_dict("records") == [{"people": 30, "by_inpatient": "<11", "by_outpatient": 30, "by_rx": 30}]
    assert len(list((tmp_path / "results" / "full" / "5_gagne" / "plots").glob("*.png"))) == 7
    assert (tmp_path / "results" / "full" / "6_care_quality" / "care_quality_overall.csv").exists()

    assert run.main(["--dry-run", "--profile", "full"]) == 0
    rendered = (tmp_path / "build" / "rendered" / "2_hiv_groups" / "06_hiv_rx.sql.txt").read_text(encoding="utf-8")
    assert "regexp_matches(generic_name" in rendered and "~*" not in rendered
    assert config.load(profile="full").duckdb_file == f"{(tmp_path / 'extracts').as_posix()}/sharp_full.duckdb"
