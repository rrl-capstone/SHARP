from __future__ import annotations

import importlib.util

from runner.steps import PIPELINE_DIR

_spec = importlib.util.spec_from_file_location("quality_measures", PIPELINE_DIR / "6_care_quality" / "4_quality_measures.py")
assert _spec and _spec.loader
qm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(qm)


def _measure(**fields: str) -> dict[str, str]:
    base = {"measure_id": "m", "min_age": "50", "max_age": "120", "lookback_years": "1",
            "denominator_all": "", "denominator_any": "", "denominator_none": "",
            "numerator_any": "x", "missing_as_met": ""}
    return {**base, **fields}


def test_or_and_groups_become_sql() -> None:
    sql = qm.measure_sql(_measure(denominator_all="hypertension", numerator_any="drug|bp_a+bp_b"))
    assert "((f.c_drug = 1) OR (f.c_bp_a = 1 AND f.c_bp_b = 1))" in sql
    assert "AND ((f.c_hypertension = 1))" in sql


def test_a_look_back_uses_the_latest_year_with_the_concept() -> None:
    sql = qm.measure_sql(_measure(numerator_any="screen", lookback_years="5", denominator_none="hearing_loss"))
    assert "COALESCE(f.last_screen, 0) >= m.analysis_year - 4" in sql
    assert "NOT ((f.c_hearing_loss = 1))" in sql


def test_missing_as_met_counts_an_untested_person_as_met() -> None:
    sql = qm.measure_sql(_measure(numerator_any="hba1c_gt9", missing_as_met="hba1c_test"))
    assert "(((f.c_hba1c_gt9 = 1)) OR NOT ((f.c_hba1c_test = 1)))" in sql


def test_every_measure_in_the_csv_loads() -> None:
    measures = qm.load_measures()
    assert len(measures) == len({m["measure_id"] for m in measures}) > 0
    assert "hearing_screen" in qm.concepts_used(measures)
