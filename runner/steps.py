"""The pipeline, in run order. This list is the only place the order is defined.

Kinds:
  sql              a .sql file: statements run in order (see runner/sql.py for its comment lines)
  sql_from_python  a .py file whose statements(variables) returns SQL built from reference/ CSVs
  python           a .py file whose run(conn, cfg, variables, results_dir) does work SQL cannot
                   (the propensity score model and the matching), on the runner's connection
  python_script    a standalone Python script, run as its own process (Rhea's Gagne scripts)
"""
from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

from runner import sql
from runner.config import REPO_ROOT

PIPELINE_DIR = REPO_ROOT / "pipeline"
SUPPORT_FILES = frozenset({"5_gagne/gagne_config.py", "README.md"})  # used by steps, not steps


@dataclass(frozen=True)
class Step:
    path: str   # relative to pipeline/
    kind: str

    @property
    def stage(self) -> str:
        return self.path.split("/")[0]

    @property
    def file(self) -> Path:
        return PIPELINE_DIR / self.path

    @property
    def name(self) -> str:
        return self.path.split("/")[-1]


STEPS: tuple[Step, ...] = (
    # 1. Eligible people (Lifei)
    Step("1_cohort/00_sample.sql", "sql"),
    Step("1_cohort/01_age50_alive.sql", "sql"),
    Step("1_cohort/02_same_insurance_all_year.sql", "sql"),
    Step("1_cohort/03_demographics.sql", "sql"),
    # 2. HIV group and control pool (Lifei, with the PI's drug decisions)
    Step("2_hiv_groups/04_hiv_dx_inpatient.sql", "sql"),
    Step("2_hiv_groups/05_hiv_dx_outpatient.sql", "sql"),
    Step("2_hiv_groups/06_hiv_rx.sql", "sql"),
    Step("2_hiv_groups/07_pwh_cohort.sql", "sql"),
    Step("2_hiv_groups/08_any_hiv_evidence.sql", "sql"),
    Step("2_hiv_groups/09_nonhiv_pool.sql", "sql"),
    # 3. Conditions for everyone, and the comparison before matching
    Step("3_conditions/1_study_person_years.sql", "sql"),
    Step("3_conditions/2_condition_codes.py", "sql_from_python"),
    Step("3_conditions/3_condition_dx_rows.sql", "sql"),
    Step("3_conditions/4_person_year_conditions.sql", "sql"),
    # 4. Propensity score matching (Lifei), and the comparison after matching
    Step("4_matching/10_ps_input.sql", "sql"),
    Step("4_matching/11_ps_matching.py", "python"),
    Step("4_matching/12_matched_summaries.sql", "sql"),
    # 5. Gagne comorbidity score of the matched people (Rhea)
    Step("5_gagne/gagne_1_evidence.py", "python_script"),
    Step("5_gagne/gagne_2_scores.py", "python_script"),
    Step("5_gagne/gagne_3_plots.py", "python_script"),
    Step("5_gagne/gagne_4_network.py", "python_script"),
    Step("5_gagne/gagne_5_summaries.sql", "sql"),
    # 6. Care quality of the matched people, overall and by Gagne level
    Step("6_care_quality/1_measure_codes.py", "sql_from_python"),
    Step("6_care_quality/2_procedure_rows.sql", "sql"),
    Step("6_care_quality/3_drug_rows.sql", "sql"),
    Step("6_care_quality/4_quality_measures.py", "sql_from_python"),
    Step("6_care_quality/5_care_quality_results.sql", "sql"),
)


def select(start: str | None = None, only: str | None = None) -> list[Step]:
    """All steps; or one stage or step (--only); or everything from a stage or step on (--from).
    A stage is its folder name (3_conditions), a step its path or file name (07_pwh_cohort.sql)."""
    def matches(step: Step, wanted: str) -> bool:
        return wanted in (step.stage, step.path, step.name)

    for wanted in (start, only):
        if wanted is not None and not any(matches(s, wanted) for s in STEPS):
            raise sql.StepError(f"No stage or step called {wanted!r}. Stages: "
                                + ", ".join(dict.fromkeys(s.stage for s in STEPS)))
    if only is not None:
        return [s for s in STEPS if matches(s, only)]
    if start is not None:
        first = next(i for i, s in enumerate(STEPS) if matches(s, start))
        return list(STEPS[first:])
    return list(STEPS)


def load_module(step: Step) -> ModuleType:
    """Import a sql_from_python or python step from its file."""
    spec = importlib.util.spec_from_file_location(step.file.stem, step.file)
    if spec is None or spec.loader is None:
        raise sql.StepError(f"Cannot load {step.path}.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def statements(step: Step, variables: dict[str, str]) -> list[sql.Statement]:
    """The statements of a sql or sql_from_python step, not yet rendered."""
    if step.kind == "sql":
        return sql.parse(step.file.read_text(encoding="utf-8"), step.path)
    if step.kind != "sql_from_python":
        raise sql.StepError(f"{step.path} is a {step.kind}, not SQL.")
    chunks: list[str] = load_module(step).statements(variables)
    return [s for chunk in chunks for s in sql.parse(chunk + ";", step.path)]