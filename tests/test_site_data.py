"""The website's data export, on a small results folder made here."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from runner import site_data


def _results(root: Path, status: str = "complete") -> Path:
    run = root / "full"
    (run / "3_conditions").mkdir(parents=True)
    (run / "run_info.json").write_text(json.dumps({
        "run": "full", "status": status, "git_commit": "abc123",
        "config_study_yml": "redshift:\n  host: cluster.example.com\n"}), encoding="utf-8")
    (run / "3_conditions" / "conditions_by_age.csv").write_text(
        "age_group,hiv,person_years,pct_with_condition\n50-64,1,<11,\n75+,0,250,12.5\n", encoding="utf-8")
    return root


def _payload(target: Path) -> dict[str, Any]:
    """The JSON inside docs/data/<profile>.js: window.SHARP_RESULTS["full"] = {...};"""
    line = target.read_text(encoding="utf-8").splitlines()[-1]
    assert line.startswith('window.SHARP_RESULTS["full"] = ') and line.endswith(";")
    return json.loads(line.split(" = ", 1)[1][:-1])


def test_hidden_counts_stay_text_and_numbers_become_numbers(tmp_path: Path) -> None:
    target = site_data.build("full", _results(tmp_path), tmp_path / "out")
    table = _payload(target)["tables"]["3_conditions/conditions_by_age"]
    assert table["columns"] == ["age_group", "hiv", "person_years", "pct_with_condition"]
    assert table["rows"] == [["50-64", 1, "<11", None], ["75+", 0, 250, 12.5]]


def test_only_the_runs_name_status_times_and_commit_are_published(tmp_path: Path) -> None:
    target = site_data.build("full", _results(tmp_path), tmp_path / "out")
    text = target.read_text(encoding="utf-8")
    assert "cluster.example.com" not in text
    assert _payload(target)["run"]["git_commit"] == "abc123"


def test_an_unfinished_run_is_not_published(tmp_path: Path) -> None:
    with pytest.raises(site_data.SiteDataError, match="did not finish"):
        site_data.build("full", _results(tmp_path, status="failed at 4_matching"), tmp_path / "out")
    assert not (tmp_path / "out" / "full.js").exists()


def test_only_the_full_cohorts_figures_are_published(tmp_path: Path) -> None:
    for profile, name in [("full", "1_score.png"), ("sample_1pct", "2_small.png")]:
        plots = tmp_path / profile / "5_gagne" / "plots"
        plots.mkdir(parents=True)
        image = Image.new("RGB", (2, 1), (255, 255, 255))
        image.putpixel((1, 0), (30, 60, 120))
        image.save(plots / name)
    assert site_data.copy_figures(tmp_path, tmp_path / "figures") == 1
    assert [p.name for p in (tmp_path / "figures").iterdir()] == ["1_score.png"]
    with Image.open(tmp_path / "figures" / "1_score.png") as out:
        background, mark = out.getpixel((0, 0)), out.getpixel((1, 0))
    assert isinstance(background, tuple) and background[3] == 0
    assert mark == (30, 60, 120, 255)
