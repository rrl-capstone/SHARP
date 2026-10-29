"""Conditions 2: loads reference/conditions.csv into ref_conditions, one row per code prefix.

  concept          short name used in every table, e.g. diabetes
  label            the name shown in results
  study_condition  yes = one of the study's conditions (reported); no = only used by a measure
  rule             claims = 1 inpatient claim, or 2 outpatient claims on different days, in the
                   year (config conditions); any_claim = any one claim in the year
  prefixes         ICD-10-CM prefixes without dots; a code matches if it starts with one
"""
from __future__ import annotations

import re

from runner.reference import CONCEPT, explode, table_statements

COLUMNS = {
    "concept": CONCEPT,
    "label": re.compile(r"^[A-Za-z0-9 ()'-]+$"),
    "study_condition": re.compile(r"^(yes|no)$"),
    "rule": re.compile(r"^(claims|any_claim)$"),
    "prefix": re.compile(r"^[A-Z][0-9A-Z]{1,6}$"),
}


def statements(variables: dict[str, str]) -> list[str]:
    rows = explode("conditions.csv", "prefixes", "prefix", ("concept", "label", "study_condition", "rule"))
    return table_statements("ref_conditions", COLUMNS, rows, "reference/conditions.csv")
