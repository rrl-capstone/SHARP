from __future__ import annotations

import re
from pathlib import Path

import pytest

from runner import config


def test_the_shared_settings_load_and_the_work_schema_defaults_to_the_user(local_file: Path) -> None:
    cfg = config.load()
    assert cfg.work_schema == "work_test_user"
    assert cfg.study_years == list(range(2016, 2026))
    assert cfg.run_name in ("sample_1pct", "full")


def test_a_schema_name_that_could_change_the_sql_is_rejected(local_file: Path) -> None:
    local_file.write_text("redshift_user: x; DROP TABLE y\n", encoding="utf-8")
    with pytest.raises(config.ConfigError, match="redshift_user"):
        config.load()


def test_each_profile_has_its_own_people_tables_and_results(local_file: Path) -> None:
    one, thirty, full = (config.load(profile=p) for p in ("sample_1pct", "sample_30pct", "full"))
    assert one.sample_filter.endswith("< '03'") and one.table_suffix == "_s1"
    assert thirty.sample_filter.endswith("< '4d'") and thirty.table_suffix == "_s30"
    assert full.sample_filter == "TRUE" and full.table_suffix == ""
    assert len({one.run_name, thirty.run_name, full.run_name}) == 3


def test_an_unknown_profile_is_rejected(local_file: Path) -> None:
    with pytest.raises(config.ConfigError, match="profile"):
        config.load(profile="sample_50pct")


def test_the_drug_scan_filter_lets_through_every_drug_pattern() -> None:
    regex = config.drug_patterns_regex()
    for row in config.read_reference("drug_patterns.csv"):
        for word in row["patterns"].split():
            assert re.search(regex, f"x {word.lower()} y", re.IGNORECASE), word


def test_gagne_levels_are_named_from_their_tops() -> None:
    sql = config.gagne_level_sql((0, 2, 4), "s")
    assert sql == ("CASE WHEN s <= 0 THEN '0 or less' WHEN s <= 2 THEN '1-2' "
                   "WHEN s <= 4 THEN '3-4' ELSE '5+' END")
