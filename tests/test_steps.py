from __future__ import annotations

import re

from runner import sql, steps


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


def test_the_r_script_suffixes_its_tables() -> None:
    script = (steps.PIPELINE_DIR / "4_matching" / "11_ps_matching.R").read_text(encoding="utf-8")
    lines = [line for line in script.splitlines() if 'write_schema, ".' in line]
    assert lines and all("table_suffix" in line for line in lines)


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
