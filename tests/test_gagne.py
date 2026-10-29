"""Rhea's Gagne code, checked without a database."""
from __future__ import annotations

import sys

import pytest

from runner.steps import PIPELINE_DIR

sys.path.insert(0, str(PIPELINE_DIR / "5_gagne"))
import gagne_2_scores  # noqa: E402
import gagne_config  # noqa: E402


def test_nemos_lookups_give_20_groups_with_hiv_aids_weighted_minus_1() -> None:
    rules, groups = gagne_config.load_gagne_rules()
    assert sorted(groups["gagne_group"]) == list(range(1, 21))
    assert len(rules) == 166
    hiv = groups.loc[groups["gagne_group"] == gagne_config.SETTINGS["hiv_group"]]
    assert hiv["group_name"].iloc[0] == "hiv_aids" and hiv["weight"].iloc[0] == -1


def test_gagne_tables_carry_the_profile_suffix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(gagne_config.SETTINGS, "work_schema", "work_x")
    monkeypatch.setitem(gagne_config.SETTINGS, "table_suffix", "_s30")
    assert gagne_config.table("scores") == "work_x.gagne_scores_s30"


def test_the_score_without_hiv_leaves_out_only_the_hiv_aids_group() -> None:
    _, groups = gagne_config.load_gagne_rules()
    sql = gagne_2_scores.build_scores_sql(groups)
    with_hiv = sql.split("AS gagne_score,")[0].rsplit("AS gagne_group_count,", 1)[1]
    without_hiv = sql.split("AS gagne_score,")[1].split("AS gagne_score_excl_hiv")[0]
    assert "gagne_group_19_hiv_aids" in with_hiv
    assert "gagne_group_19_hiv_aids" not in without_hiv
    assert "f.*" not in sql
