"""Care quality 1: loads the code lists the measures use.

  reference/procedure_codes.csv  -> ref_procedures (concept, code): CPT and HCPCS codes
  reference/drug_patterns.csv    -> ref_drug_patterns (concept, pattern): words in generic names
  reference/quality_measures.csv -> ref_measures (measure_id, condition, label, higher_is_better)
"""
from __future__ import annotations

import re

from runner.config import read_reference
from runner.reference import CONCEPT, explode, table_statements

PROCEDURE_CODE = re.compile(r"^[0-9A-Z]{5}$")
DRUG_PATTERN = re.compile(r"^[A-Z][A-Z0-9 -]*$")
TEXT = re.compile(r"^[A-Za-z0-9 ()%/+,.'-]+$")


def statements(variables: dict[str, str]) -> list[str]:
    procedures = explode("procedure_codes.csv", "codes", "code", ("concept",))
    drugs = explode("drug_patterns.csv", "patterns", "pattern", ("concept",))
    measures = read_reference("quality_measures.csv")
    return (table_statements("ref_procedures", {"concept": CONCEPT, "code": PROCEDURE_CODE},
                             procedures, "reference/procedure_codes.csv")
            + table_statements("ref_drug_patterns", {"concept": CONCEPT, "pattern": DRUG_PATTERN},
                               drugs, "reference/drug_patterns.csv")
            + table_statements("ref_measures",
                               {"measure_id": CONCEPT, "condition": TEXT, "label": TEXT,
                                "higher_is_better": re.compile(r"^[01]$")},
                               measures, "reference/quality_measures.csv"))
