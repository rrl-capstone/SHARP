from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from runner.results import HIDDEN, UnsafeResultError, resuppress, suppress


def test_counts_from_1_to_10_are_hidden_and_their_percentages_blanked() -> None:
    df = pd.DataFrame({"analysis_year": [2016, 2017, 2018], "hiv": [1, 1, 0],
                       "person_years": [5, 0, 250], "pct_with_condition": [12.5, 0.0, 40.0]})
    out = suppress(df)
    assert out["person_years"].tolist() == [HIDDEN, 0, 250]
    assert out["pct_with_condition"].tolist() == [None, 0.0, 40.0]


def test_label_columns_are_never_hidden() -> None:
    out = suppress(pd.DataFrame({"hiv": [1, 0], "gagne_group": [3, 19], "step_order": [1, 2],
                                 "people": [500, 600]}))
    assert out["hiv"].tolist() == [1, 0]
    assert out["gagne_group"].tolist() == [3, 19]
    assert out["step_order"].tolist() == [1, 2]


def test_counts_with_a_blank_or_from_numeric_columns_are_still_hidden() -> None:
    df = pd.DataFrame({"hiv": [0, 1, 1], "people": [np.nan, 7.0, 40.0],
                       "met": [Decimal("3"), Decimal("12"), None]})
    out = suppress(df)
    assert out["people"].tolist() == [None, HIDDEN, 40]
    assert out["met"].tolist() == [HIDDEN, 20, None]


def test_other_counts_are_rounded_so_a_hidden_count_cannot_be_worked_out_from_a_total() -> None:
    # 1,004 people in total, 997 in one group and 7 in the other: 1,000 - 1,000 no longer reveals the 7
    out = suppress(pd.DataFrame({"hiv": [0, 1, 1], "people": [1004, 997, 7],
                                 "pct_of_group": [100.0, 99.3027, 0.6972]}))
    assert out["people"].tolist() == [1000, 1000, HIDDEN]
    assert out["pct_of_group"].tolist() == [100.0, 99.3, None]


def test_counts_from_11_to_24_are_shown_as_20_and_others_to_the_nearest_10() -> None:
    out = suppress(pd.DataFrame({"people": [11, 14, 15, 24, 25, 0, 840, 2407, 14123, 116049829]}))
    assert out["people"].tolist() == [20, 20, 20, 20, 30, 0, 840, 2410, 14100, 116000000]


def test_years_and_flags_are_labels_not_counts() -> None:
    out = suppress(pd.DataFrame({"concept_year": [2015, 2016], "higher_is_better": [1, 0], "person_years": [500, 501]}))
    assert out["concept_year"].tolist() == [2015, 2016]
    assert out["higher_is_better"].tolist() == [1, 0]
    assert out["person_years"].tolist() == [500, 500]


def test_applying_the_rule_twice_changes_nothing(tmp_path: Path) -> None:
    path = tmp_path / "r.csv"
    path.write_text("hiv,people,pct_of_group\n0,1004,99.3027\n1,<11,\n", encoding="utf-8")
    resuppress(path)
    once = path.read_text(encoding="utf-8")
    resuppress(path)
    assert path.read_text(encoding="utf-8") == once
    assert once.splitlines()[1:] == ["0,1000,99.3", "1,<11,"]


def test_network_links_keep_their_group_labels_and_lift() -> None:
    out = suppress(pd.DataFrame({"hiv": [1, 1], "group_a": [2, 9], "group_b": [9, 14],
                                 "person_years_with_both": [8, 120], "lift": [3.5, 1.8]}))
    assert out["group_a"].tolist() == [2, 9] and out["group_b"].tolist() == [9, 14]
    assert out["person_years_with_both"].tolist() == [HIDDEN, 120]
    assert out["lift"].tolist() == [None, 1.8]


def test_a_fraction_in_a_column_not_named_as_derived_stops_the_save() -> None:
    with pytest.raises(UnsafeResultError):
        suppress(pd.DataFrame({"hiv": [0, 1], "average": [1.25, 2.5]}))
