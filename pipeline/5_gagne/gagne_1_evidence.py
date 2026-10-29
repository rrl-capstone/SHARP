"""
Gagne step 1: find Gagne evidence for every matched person-year.

Run:  python gagne_1_evidence.py      (asks for your Redshift password)

Builds, in the work schema:
  gagne_person_years    the matched person-years to score (from ps_matched)
  gagne_rules           Nemo's ICD-10-CM Gagne rules
  gagne_dx_candidates   distinct (patient, year, dx_code) that passed the prefix filter
  gagne_code_map        distinct dx_code -> Gagne group
  gagne_group_evidence  distinct (patient, year, Gagne group)

How it works (same approach as Nemo's script 3):
  1. Read the diagnosis table one calendar year at a time (Komodo is a Redshift
     Spectrum table; one statement for all ten years ran for hours). Keep only
     codes whose first 1-3 characters could belong to a Gagne rule, then only
     matched patients in the year they were matched. Keep each code once per
     patient-year.
  2. Apply the exact/prefix/range rules to the few thousand DISTINCT codes,
     not to the millions of patient rows.
  3. Join back by plain code equality to get each patient-year's groups.

Window: a diagnosis counts toward the person-year of the calendar year it
falls in (Jan 1 - Dec 31), i.e. a 1-year look-back to the Dec 31 index date.
"""

import time

from gagne_config import (SETTINGS, table, komodo, connect, run_sql,
                          query_df, show, sql_str, load_gagne_rules,
                          candidate_prefixes, prefix_filter_sql)

RETRYABLE = ("Spectrum Scan Error", "timed out", "Retries exceeded")


def drop(conn, key):
    run_sql(conn, f"DROP TABLE IF EXISTS {table(key)};")


def build_person_years_sql():
    years = ", ".join(str(y) for y in SETTINGS["study_years"])
    return f"""
CREATE TABLE {table("person_years")}
DISTKEY(patient_id) SORTKEY(patient_id, analysis_year) AS
SELECT patient_id, analysis_year, pair_id, hiv, index_date
FROM {SETTINGS["work_schema"]}.{SETTINGS["matched_table"]}{SETTINGS["table_suffix"]}
WHERE analysis_year IN ({years});"""


def build_rules_sql(rules):
    """CREATE + INSERT for the rule table. DISTSTYLE ALL = a full copy on every
    node, so joining to it never moves data around."""
    create = f"""
CREATE TABLE {table("rules")} (
    gagne_group INTEGER, match_type VARCHAR(8), match_value VARCHAR(16),
    range_start VARCHAR(16), range_end VARCHAR(16), range_end_inclusive VARCHAR(8)
) DISTSTYLE ALL;"""
    values = ",\n".join(
        f"({r.gagne_group}, {sql_str(r.match_type)}, {sql_str(r.match_value)}, "
        f"{sql_str(r.range_start)}, {sql_str(r.range_end)}, {sql_str(r.range_end_inclusive)})"
        for r in rules.itertuples())
    insert = f"INSERT INTO {table('rules')} VALUES\n{values};"
    return create, insert


def build_candidates_table_sql():
    return f"""
CREATE TABLE {table("candidates")} (
    patient_id VARCHAR(100), analysis_year INTEGER, dx_code VARCHAR(40)
) DISTKEY(patient_id) SORTKEY(patient_id, analysis_year);"""


def build_scan_year_sql(prefixes, year):
    """One year of the scan of the big diagnosis table (the slow step).
    - the date range, the prefix filter and the profile's sample filter are literal
      values, so Spectrum applies them while reading
    - codes are made distinct per patient inside the scan, so only a short list
      reaches the cluster
    - the JOIN to person_years keeps only matched patients, in the year they were matched
    - REPLACE strips dots so codes compare the same way as the lookup (no dots)"""
    return f"""
INSERT INTO {table("candidates")}
SELECT s.patient_id, {year} AS analysis_year, s.dx_code
FROM (
    SELECT patient_id, REPLACE(dx_code, '.', '')::VARCHAR(40) AS dx_code
    FROM {komodo("dx_table")}
    WHERE event_date >= DATE '{year}-01-01'
      AND event_date <  DATE '{year + 1}-01-01'
      AND dx_code IS NOT NULL AND dx_code <> ''
      AND {prefix_filter_sql(prefixes, "dx_code")}
      AND {SETTINGS["sample_filter"]}
    GROUP BY 1, 2
) s
JOIN {table("person_years")} py
  ON py.patient_id = s.patient_id
 AND py.analysis_year = {year};"""


def run_with_retry(conn, sql, label, attempts=3, wait_seconds=60):
    """Spectrum gives each scan a time limit; a year that times out is tried again."""
    import redshift_connector
    for attempt in range(1, attempts + 1):
        try:
            run_sql(conn, sql, label)
            return
        except redshift_connector.Error as error:
            if attempt == attempts or not any(k in str(error) for k in RETRYABLE):
                raise
            print(f"{label}: Spectrum timed out (attempt {attempt} of {attempts}), retrying", flush=True)
            time.sleep(wait_seconds * attempt)


def build_code_map_sql():
    """Apply Nemo's rules to DISTINCT codes (a few thousand rows, so the OR
    join is cheap here). Range logic is copied from his script 3: ranges
    flagged range_end_inclusive = FALSE use '<', otherwise '<='."""
    return f"""
CREATE TABLE {table("code_map")} DISTSTYLE ALL AS
SELECT DISTINCT d.dx_code, r.gagne_group
FROM (SELECT DISTINCT dx_code FROM {table("candidates")}) d
JOIN {table("rules")} r
  ON (r.match_type = 'exact'  AND d.dx_code = r.match_value)
  OR (r.match_type = 'prefix' AND LEFT(d.dx_code, LENGTH(r.match_value)) = r.match_value)
  OR (r.match_type = 'range'  AND d.dx_code >= r.range_start AND (
         (COALESCE(UPPER(r.range_end_inclusive), 'TRUE') =  'FALSE' AND d.dx_code <  r.range_end)
      OR (COALESCE(UPPER(r.range_end_inclusive), 'TRUE') <> 'FALSE' AND d.dx_code <= r.range_end)));"""


def build_evidence_sql():
    """Back to patient level by plain code equality: one row per
    (patient, year, Gagne group) that had at least one matching code."""
    return f"""
CREATE TABLE {table("evidence")}
DISTKEY(patient_id) SORTKEY(patient_id, analysis_year, gagne_group) AS
SELECT DISTINCT c.patient_id, c.analysis_year, m.gagne_group
FROM {table("candidates")} c
JOIN {table("code_map")} m ON m.dx_code = c.dx_code;"""


def main():
    rules, groups = load_gagne_rules()
    prefixes = candidate_prefixes(rules)
    print(f"Study years: {SETTINGS['study_years']}")
    print(f"{len(rules)} ICD-10-CM rules, {sum(len(p) for p in prefixes.values())} filter prefixes")

    conn = connect()
    try:
        for key in ["evidence", "code_map", "candidates", "rules", "person_years"]:
            drop(conn, key)

        # 1. Matched person-years to score
        run_sql(conn, build_person_years_sql(), "person-years from ps_matched")
        qa = query_df(conn, f"""
            SELECT COUNT(*) AS n_rows,
                   COUNT(DISTINCT patient_id || '-' || analysis_year) AS n_person_years
            FROM {table("person_years")}""")
        print(qa.to_string(index=False))
        if qa.n_rows[0] == 0 or qa.n_rows[0] != qa.n_person_years[0]:
            raise RuntimeError("gagne_person_years must have exactly one row per person-year.")

        # 2. Rule table
        create, insert = build_rules_sql(rules)
        run_sql(conn, create)
        run_sql(conn, insert)

        # 3. The diagnosis scan (the slow step), one year at a time
        run_sql(conn, build_candidates_table_sql())
        for year in SETTINGS["study_years"]:
            run_with_retry(conn, build_scan_year_sql(prefixes, year), f"scan {year} diagnoses for Gagne candidates")
        show(conn, "Candidate rows:",
             f"SELECT COUNT(*) AS n_rows FROM {table('candidates')}")

        # 4. Distinct codes -> groups
        run_sql(conn, build_code_map_sql(), "map distinct codes to Gagne groups")
        show(conn, "Distinct codes per Gagne group (all 20 groups should appear):",
             f"""SELECT gagne_group, COUNT(*) AS n_codes FROM {table('code_map')}
                 GROUP BY 1 ORDER BY 1""")

        # 5. Patient-level evidence
        run_sql(conn, build_evidence_sql(), "patient-year Gagne evidence")
        show(conn, "Person-years with each Gagne group:",
             f"""SELECT gagne_group, COUNT(*) AS n_person_years FROM {table('evidence')}
                 GROUP BY 1 ORDER BY 1""")
    finally:
        conn.close()


if __name__ == "__main__":
    main()