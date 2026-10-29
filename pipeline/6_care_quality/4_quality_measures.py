"""Care quality 4: every Table 1 measure in reference/quality_measures.csv, for the matched people.

Builds, in the work schema:
  measure_concepts  every concept a matched person has in a year: conditions (stage 3, with the
                    claim-count rule), procedures and drugs (steps 2 and 3)
  measure_flags     one row per person and year, a 0/1 column per concept (c_<concept>) and the
                    latest year up to then with that concept (last_<concept>), for look-backs
  quality_measures  one row per measure and matched person-year in its denominator, met 0/1

In the CSV, `+` means AND and `|` means OR, so `antihypertensive|bp_sys_lt140+bp_dia_lt90` is
"a blood pressure medicine, or both BP result codes". A measure's denominator needs every
denominator_all concept, any one denominator_any group, and no denominator_none group, plus the
age range; its numerator is any numerator_any group within lookback_years (counting the
measurement year). missing_as_met names a concept whose ABSENCE meets the numerator (the
diabetes measure counts "not tested" as poor control). To add or change a measure, edit the CSV.
"""
from __future__ import annotations

from runner.config import ConfigError, read_reference
from runner.reference import CONCEPT

GROUP_FIELDS = ("denominator_all", "denominator_any", "denominator_none", "numerator_any", "missing_as_met")


def groups(text: str) -> list[list[str]]:
    """'a|b+c' -> [['a'], ['b', 'c']]: any one group, every concept inside a group."""
    out = []
    for part in (text or "").split("|"):
        concepts = [c.strip().lower() for c in part.split("+") if c.strip()]
        if concepts:
            out.append(concepts)
    return out


def load_measures() -> list[dict[str, str]]:
    measures = read_reference("quality_measures.csv")
    for m in measures:
        if not CONCEPT.match(m["measure_id"]):
            raise ConfigError(f"quality_measures.csv: bad measure_id {m['measure_id']!r}.")
        for field in ("min_age", "max_age", "lookback_years"):
            if not m[field].isdigit():
                raise ConfigError(f"quality_measures.csv: {m['measure_id']} {field} must be a whole number.")
        if not groups(m["numerator_any"]):
            raise ConfigError(f"quality_measures.csv: {m['measure_id']} has no numerator.")
    return measures


def concepts_used(measures: list[dict[str, str]]) -> list[str]:
    names = {c for m in measures for field in GROUP_FIELDS for g in groups(m[field]) for c in g}
    bad = sorted(n for n in names if not CONCEPT.match(n))
    if bad:
        raise ConfigError(f"quality_measures.csv: concept names must be lowercase words: {bad}.")
    return sorted(names)


def _has(concept: str, lookback: int) -> str:
    if lookback <= 1:
        return f"f.c_{concept} = 1"
    return f"COALESCE(f.last_{concept}, 0) >= m.analysis_year - {lookback - 1}"


def _any(group_list: list[list[str]], lookback: int = 1) -> str:
    return "(" + " OR ".join("(" + " AND ".join(_has(c, lookback) for c in g) + ")" for g in group_list) + ")"


def measure_sql(m: dict[str, str]) -> str:
    """One measure: its denominator person-years and whether each met the numerator."""
    where = [f"s.age BETWEEN {int(m['min_age'])} AND {int(m['max_age'])}"]
    den_all = [c for g in groups(m["denominator_all"]) for c in g]
    if den_all:
        where.append(_any([den_all]))
    if groups(m["denominator_any"]):
        where.append(_any(groups(m["denominator_any"])))
    if groups(m["denominator_none"]):
        where.append("NOT " + _any(groups(m["denominator_none"])))
    met = _any(groups(m["numerator_any"]), max(1, int(m["lookback_years"])))
    if groups(m["missing_as_met"]):
        met = f"({met} OR NOT {_any(groups(m['missing_as_met']))})"
    return (f"SELECT m.patient_id, m.analysis_year, '{m['measure_id']}'::VARCHAR(40) AS measure_id,\n"
            f"       CASE WHEN {met} THEN 1 ELSE 0 END AS met\n"
            f"FROM ${{work_schema}}.ps_matched${{sfx}} m\n"
            f"JOIN ${{work_schema}}.study_person_years${{sfx}} s ON s.patient_id = m.patient_id AND s.analysis_year = m.analysis_year\n"
            f"JOIN ${{work_schema}}.measure_flags${{sfx}} f ON f.patient_id = m.patient_id AND f.analysis_year = m.analysis_year\n"
            f"WHERE {' AND '.join(where)}")


def flags_sql(concepts: list[str]) -> str:
    listed = ", ".join(f"'{c}'" for c in concepts)
    pivot = ",\n           ".join(f"MAX(CASE WHEN concept = '{c}' THEN 1 ELSE 0 END) AS c_{c}" for c in concepts)
    filled = ", ".join(f"COALESCE(f.c_{c}, 0) AS c_{c}" for c in concepts)
    last = ",\n       ".join(f"MAX(CASE WHEN c_{c} = 1 THEN analysis_year END) OVER "
                            f"(PARTITION BY patient_id ORDER BY analysis_year ROWS UNBOUNDED PRECEDING) AS last_{c}"
                            for c in concepts)
    return f"""CREATE TABLE ${{work_schema}}.measure_flags${{sfx}} DISTKEY(patient_id) SORTKEY(patient_id, analysis_year) AS
WITH f AS (
    SELECT patient_id, concept_year AS analysis_year,
           {pivot}
    FROM ${{work_schema}}.measure_concepts${{sfx}}
    WHERE concept IN ({listed})
    GROUP BY 1, 2
),
grid AS (   -- every year with a concept, plus every matched person-year (which may have none)
    SELECT patient_id, analysis_year FROM f
    UNION
    SELECT patient_id, analysis_year FROM ${{work_schema}}.ps_matched${{sfx}}
),
wide AS (
    SELECT g.patient_id, g.analysis_year, {filled}
    FROM grid g
    LEFT JOIN f ON f.patient_id = g.patient_id AND f.analysis_year = g.analysis_year
)
SELECT patient_id, analysis_year, {', '.join(f'c_{c}' for c in concepts)},
       {last}
FROM wide"""


CONCEPTS_SQL = """CREATE TABLE ${work_schema}.measure_concepts${sfx} DISTKEY(patient_id) SORTKEY(patient_id, concept_year) AS
SELECT c.patient_id, c.analysis_year AS concept_year, c.concept::VARCHAR(200) AS concept
FROM ${work_schema}.person_year_conditions${sfx} c
JOIN ${work_schema}.matched_ids${sfx} i ON i.patient_id = c.patient_id
UNION
SELECT patient_id, concept_year, concept FROM ${work_schema}.care_px_concepts${sfx}
UNION
SELECT patient_id, concept_year, concept FROM ${work_schema}.care_rx_concepts${sfx}"""


def statements(variables: dict[str, str]) -> list[str]:
    measures = load_measures()
    union = "\nUNION ALL\n".join(measure_sql(m) for m in measures)
    return [
        "DROP TABLE IF EXISTS ${work_schema}.measure_concepts${sfx}",
        CONCEPTS_SQL,
        "DROP TABLE IF EXISTS ${work_schema}.measure_flags${sfx}",
        flags_sql(concepts_used(measures)),
        "DROP TABLE IF EXISTS ${work_schema}.quality_measures${sfx}",
        "CREATE TABLE ${work_schema}.quality_measures${sfx} DISTKEY(patient_id) SORTKEY(measure_id, analysis_year) AS\n"
        + union,
        "-- check: one row per measure and matched person-year in its denominator\n"
        "-- result: quality_measures_check\n"
        "-- expect: rows_total = distinct_rows\n"
        "SELECT COUNT(*) AS rows_total,\n"
        "       COUNT(DISTINCT measure_id || '-' || patient_id || '-' || analysis_year) AS distinct_rows\n"
        "FROM ${work_schema}.quality_measures${sfx}",
    ]
