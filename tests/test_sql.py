from __future__ import annotations

import pytest

from runner.sql import StepError, parse, render

STEP = """-- header; with a semicolon in a comment
DROP TABLE IF EXISTS ${work_schema}.a;

-- for each year: study
INSERT INTO ${work_schema}.a SELECT ${year} WHERE x ~* 'a|b;c';

-- check: rows
-- result: a_check
-- expect: rows_total = person_years
SELECT COUNT(*) AS rows_total, COUNT(*) AS person_years FROM ${work_schema}.a;
"""


def test_statements_and_their_comment_lines_are_read() -> None:
    drop, insert, check = parse(STEP, "t.sql")
    assert not drop.is_query and drop.for_each_year is None
    assert insert.for_each_year == "study" and "'a|b;c'" in insert.text
    assert check.is_query and check.result_name == "a_check"
    assert check.expect == ("rows_total", "person_years")


def test_a_select_without_a_result_name_is_rejected() -> None:
    with pytest.raises(StepError, match="result"):
        parse("SELECT 1 AS n;", "t.sql")


def test_a_per_year_select_is_rejected() -> None:
    with pytest.raises(StepError, match="INSERT"):
        parse("-- for each year: study\n-- result: x\nSELECT ${year} AS n;", "t.sql")


def test_an_unknown_variable_is_reported_by_name() -> None:
    with pytest.raises(StepError, match="nope"):
        render("SELECT ${nope}", {}, "t.sql")
