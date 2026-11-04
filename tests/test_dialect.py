"""Redshift-to-DuckDB rewrites (runner/dialect.py), on SQL text only: no database."""
from __future__ import annotations

import re
import sys

import pytest

from runner import dialect, sql, steps
from runner.dialect import DialectError, to_duckdb

sys.path.insert(0, str(steps.PIPELINE_DIR / "5_gagne"))
import gagne_1_evidence  # noqa: E402
import gagne_2_scores  # noqa: E402
import gagne_config  # noqa: E402

REDSHIFT_ONLY = re.compile(r"\bDISTKEY\b|\bSORTKEY\b|\bDISTSTYLE\b|~\*|\bTO_DATE\b|::\s*FLOAT\b", re.IGNORECASE)
LITERAL_IN_LIST = re.compile(r"\bIN\s*\(\s*('|-?\d)", re.IGNORECASE)


def test_redshift_physical_layout_is_removed() -> None:
    assert to_duckdb("CREATE TABLE w.a DISTKEY(patient_id) SORTKEY(patient_id, yr) AS SELECT 1") == \
        "CREATE TABLE w.a AS SELECT 1"
    assert to_duckdb("CREATE TABLE w.r (code VARCHAR(200)) DISTSTYLE ALL") == "CREATE TABLE w.r (code VARCHAR(200))"
    assert to_duckdb("CREATE TABLE w.m DISTSTYLE ALL AS\nSELECT 1") == "CREATE TABLE w.m AS\nSELECT 1"


def test_case_insensitive_regex_becomes_a_partial_regexp_match() -> None:
    assert to_duckdb("WHERE generic_name ~* 'abacavir|dolutegravir'") == \
        "WHERE regexp_matches(generic_name, 'abacavir|dolutegravir', 'i')"


def test_to_date_becomes_a_cast_and_other_formats_are_refused() -> None:
    assert to_duckdb("TO_DATE(y.yr || '-12-31', 'YYYY-MM-DD') AS year_end") == \
        "CAST(y.yr || '-12-31' AS DATE) AS year_end"
    with pytest.raises(DialectError, match="DD/MM/YYYY"):
        to_duckdb("TO_DATE(x, 'DD/MM/YYYY')")


def test_float_means_double_and_float8_is_left_alone() -> None:
    assert to_duckdb("AVG(score::FLOAT), 1.0::FLOAT8") == "AVG(score::DOUBLE), 1.0::FLOAT8"
    with pytest.raises(DialectError, match="FLOAT"):
        to_duckdb("CAST(score AS FLOAT)")


def test_value_lists_become_or_chains() -> None:
    assert to_duckdb("WHERE dx_code IN ('B20', 'B24')") == "WHERE (dx_code = 'B20' OR dx_code = 'B24')"
    assert to_duckdb("AND LEFT(dx_code, 3) IN ('E11')") == "AND (LEFT(dx_code, 3) = 'E11')"
    assert to_duckdb("UPPER(transaction_status) IN ('FINAL', 'STANDALONE')") == \
        "(UPPER(transaction_status) = 'FINAL' OR UPPER(transaction_status) = 'STANDALONE')"
    assert to_duckdb("WHERE p.analysis_year IN (2016,\n 2017)") == \
        "WHERE (p.analysis_year = 2016 OR p.analysis_year = 2017)"
    assert to_duckdb("CASE WHEN s IN ('CT') THEN 'Northeast' END") == "CASE WHEN (s = 'CT') THEN 'Northeast' END"


def test_subqueries_strings_and_comments_are_not_rewritten() -> None:
    text = ("-- Lifei's list: x IN ('a')\nSELECT 'y IN (''b'')' FROM t\n"
            "WHERE patient_id IN (SELECT patient_id FROM w.ids) /* z IN ('c') */")
    assert to_duckdb(text) == text


def test_an_in_list_whose_left_side_is_unclear_is_refused() -> None:
    for text in ("a || b IN ('x')", "x::VARCHAR IN ('x')", "CASE WHEN a THEN b END IN ('x')",
                 "x NOT IN ('a', 'b')"):
        with pytest.raises(DialectError):
            to_duckdb(text)


def test_code_without_redshift_constructs_comes_out_unchanged() -> None:
    text = ("SELECT patient_id || '-' || analysis_year, MD5(CAST(patient_id AS VARCHAR)) < '03', "
            "LEAST(a, 4), ROUND((100.0 * x / y)::DECIMAL(18, 6), 2) FROM w.t GROUP BY 1, 2 ORDER BY 1 DESC")
    assert to_duckdb(text) == text


def _gagne_sql(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    monkeypatch.setitem(gagne_config.SETTINGS, "work_schema", "work_x")
    monkeypatch.setitem(gagne_config.SETTINGS, "komodo_schema", "komodo_202606")
    rules, groups = gagne_config.load_gagne_rules()
    return [gagne_1_evidence.build_person_years_sql(), *gagne_1_evidence.build_rules_sql(rules),
            gagne_1_evidence.build_candidates_table_sql(),
            gagne_1_evidence.build_scan_year_sql(gagne_config.candidate_prefixes(rules), 2016),
            gagne_1_evidence.build_code_map_sql(), gagne_1_evidence.build_evidence_sql(),
            gagne_2_scores.build_scores_sql(groups)]


def test_every_pipeline_statement_translates_with_no_redshift_construct_or_value_list_left(
        variables: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> None:
    rendered = []
    for step in steps.STEPS:
        if step.kind in ("sql", "sql_from_python"):
            for statement in steps.statements(step, variables):
                rendered.append(sql.render(statement.text, {**variables, "year": "2016", "next_year": "2017"},
                                           step.path))
    for text in rendered + _gagne_sql(monkeypatch):
        code = dialect._HIDDEN.sub("''", to_duckdb(text))
        assert not REDSHIFT_ONLY.search(code), code[:300]
        assert not LITERAL_IN_LIST.search(code), code[:300]
