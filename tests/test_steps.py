from __future__ import annotations

import re
import sys

from runner import duckdb_backend, sql, steps


def test_every_file_in_pipeline_is_a_listed_step_or_a_support_file() -> None:
    on_disk = {p.relative_to(steps.PIPELINE_DIR).as_posix()
               for p in steps.PIPELINE_DIR.rglob("*") if p.is_file() and "__pycache__" not in p.parts}
    listed = {s.path for s in steps.STEPS}
    assert on_disk - listed - steps.SUPPORT_FILES == set()
    assert listed - on_disk == set()


def test_every_sql_step_renders_with_no_unknown_variables(variables: dict[str, str]) -> None:
    for step in steps.STEPS:
        if step.kind not in ("sql", "sql_from_python"):
            continue
        for statement in steps.statements(step, variables):
            rendered = sql.render(statement.text, {**variables, "year": "2016", "next_year": "2017"}, step.path)
            assert "${" not in rendered, step.path


def test_every_work_schema_table_carries_the_profile_suffix(variables: dict[str, str]) -> None:
    """Without the suffix, two profiles running at once would overwrite each other's tables."""
    assert variables["sfx"] == "_s1"
    table = re.compile(re.escape(variables["work_schema"]) + r"\.([a-z0-9_]+)")
    for step in steps.STEPS:
        if step.kind not in ("sql", "sql_from_python"):
            continue
        for statement in steps.statements(step, variables):
            rendered = sql.render(statement.text, {**variables, "year": "2016", "next_year": "2017"}, step.path)
            unsuffixed = [t for t in table.findall(rendered) if not t.endswith("_s1")]
            assert not unsuffixed, f"{step.path}: {unsuffixed}"


def test_file_11_suffixes_its_tables() -> None:
    script = (steps.PIPELINE_DIR / "4_matching" / "11_ps_matching.py").read_text(encoding="utf-8")
    tables = re.findall(r"\$\{work_schema\}\.([a-z_]+)(\$\{sfx\})?", script)
    assert {name for name, _ in tables} == {"ps_input", "ps_matched"}
    assert all(suffix for _, suffix in tables)


def test_python_steps_declare_the_tables_they_build(variables: dict[str, str]) -> None:
    sys.path.insert(0, str(steps.PIPELINE_DIR / "5_gagne"))
    import gagne_config

    gagne = [s for s in steps.STEPS if s.kind == "python_script"]
    assert {t for s in gagne for t in s.outputs} == set(gagne_config.TABLES.values())
    assert steps.created_tables(next(s for s in steps.STEPS if s.kind == "python"), variables) == ["ps_matched_s1"]
    assert steps.created_tables(next(s for s in steps.STEPS if s.name == "03_demographics.sql"), variables) == \
        ["eligible_person_years_s1", "eligible_ids_s1"]


def test_every_komodo_table_a_step_reads_has_a_duckdb_view(variables: dict[str, str]) -> None:
    """On Explorer each one is a view over its parquet folder, or built (normalized_dx_events)."""
    sys.path.insert(0, str(steps.PIPELINE_DIR / "5_gagne"))
    import gagne_config

    read = {gagne_config.SETTINGS["dx_table"]}
    for path in steps.PIPELINE_DIR.rglob("*.sql"):
        read |= set(re.findall(r"\$\{komodo_schema\}\.([a-z_]+)", path.read_text(encoding="utf-8")))
    assert read <= set(duckdb_backend.KOMODO_TABLES) | {duckdb_backend.DX_VIEW}
    assert set(duckdb_backend.REQUIRED_COLUMNS) == set(duckdb_backend.KOMODO_TABLES)


def test_result_names_are_unique_within_each_stage(variables: dict[str, str]) -> None:
    seen: dict[tuple[str, str], str] = {}
    for step in steps.STEPS:
        if step.kind not in ("sql", "sql_from_python"):
            continue
        for statement in steps.statements(step, variables):
            if statement.result_name:
                key = (step.stage, statement.result_name)
                assert key not in seen, f"{key} in {step.path} and {seen.get(key)}"
                seen[key] = step.path


def test_from_and_only_pick_steps_by_stage_or_file_name() -> None:
    assert [s.stage for s in steps.select(only="5_gagne")] == ["5_gagne"] * 5
    assert steps.select(start="07_pwh_cohort.sql")[0].path == "2_hiv_groups/07_pwh_cohort.sql"
    assert len(steps.select()) == len(steps.STEPS)
