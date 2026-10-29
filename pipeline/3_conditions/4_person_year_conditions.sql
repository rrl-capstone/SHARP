-- Conditions 4: which conditions each person has each year, and the comparison BEFORE matching.
-- Prefixes are matched to the few thousand distinct codes (cheap), then joined back by plain
-- code equality. A concept counts once per person-year however many codes or prefixes match.
-- rule = claims:    at least ${min_inpatient_claims} inpatient claim(s), or at least
--                   ${min_outpatient_claims} outpatient claims on different days, in the year
-- rule = any_claim: any one claim in the year
-- Outputs: ${work_schema}.condition_code_map${sfx}, ${work_schema}.person_year_conditions${sfx}

DROP TABLE IF EXISTS ${work_schema}.condition_code_map${sfx};

CREATE TABLE ${work_schema}.condition_code_map${sfx} DISTSTYLE ALL AS
SELECT DISTINCT d.dx_code, r.concept, r.label, r.study_condition, r.rule
FROM (SELECT DISTINCT dx_code FROM ${work_schema}.condition_dx_rows${sfx}) d
JOIN ${work_schema}.ref_conditions${sfx} r
  ON LEFT(d.dx_code, LENGTH(r.prefix)) = r.prefix;

DROP TABLE IF EXISTS ${work_schema}.person_year_conditions${sfx};

CREATE TABLE ${work_schema}.person_year_conditions${sfx}
DISTKEY(patient_id) SORTKEY(patient_id, analysis_year) AS
WITH per_concept AS (
    SELECT x.patient_id, x.analysis_year, m.concept, m.label, m.study_condition, m.rule,
           SUM(CASE WHEN x.inpatient = 1 THEN x.claims ELSE 0 END) AS ip_claims,
           SUM(CASE WHEN x.inpatient = 0 THEN x.claims ELSE 0 END) AS op_claims,
           MIN(CASE WHEN x.inpatient = 0 THEN x.first_date END)    AS op_first,
           MAX(CASE WHEN x.inpatient = 0 THEN x.last_date END)     AS op_last
    FROM ${work_schema}.condition_dx_rows${sfx} x   -- already one row per person, year, code and setting
    JOIN ${work_schema}.condition_code_map${sfx} m ON m.dx_code = x.dx_code
    GROUP BY 1, 2, 3, 4, 5, 6
)
SELECT patient_id, analysis_year, concept, label, study_condition
FROM per_concept
WHERE rule = 'any_claim'
   OR ip_claims >= ${min_inpatient_claims}
   OR (op_claims >= ${min_outpatient_claims}
       AND (${min_outpatient_claims} < 2 OR op_first < op_last));   -- 2+ claims on different days

-- check: one row per person, year and condition
-- result: person_year_conditions_check
-- expect: rows_total = distinct_rows
SELECT COUNT(*) AS rows_total,
       COUNT(DISTINCT patient_id || '-' || analysis_year || '-' || concept) AS distinct_rows
FROM ${work_schema}.person_year_conditions${sfx};


-- BEFORE MATCHING: everyone in the HIV group against everyone in the control pool.
-- These groups also differ by age, sex, state and race, so differences here mix HIV with
-- those; stage 4 repeats the comparison on the matched groups.

-- check: share of person-years with each study condition, per year and HIV status
-- result: conditions_before_matching_by_year
WITH totals AS (
    SELECT analysis_year, hiv, COUNT(*) AS person_years
    FROM ${work_schema}.study_person_years${sfx}
    GROUP BY 1, 2
),
with_condition AS (
    SELECT p.analysis_year, p.hiv, c.concept, c.label, COUNT(*) AS person_years_with
    FROM ${work_schema}.study_person_years${sfx} p
    JOIN ${work_schema}.person_year_conditions${sfx} c
      ON c.patient_id = p.patient_id AND c.analysis_year = p.analysis_year
    WHERE c.study_condition = 'yes'
    GROUP BY 1, 2, 3, 4
)
SELECT t.analysis_year, t.hiv, w.concept AS condition, w.label,
       t.person_years, w.person_years_with,
       ROUND(100.0 * w.person_years_with / t.person_years, 2) AS pct_with_condition
FROM totals t
JOIN with_condition w ON w.analysis_year = t.analysis_year AND w.hiv = t.hiv
ORDER BY 1, 3, 2;

-- check: the same over all study years, by age group (protocol: how it varies by age)
-- result: conditions_before_matching_by_age
WITH banded AS (
    SELECT patient_id, analysis_year, hiv,
           CASE WHEN age < 65 THEN '50-64' WHEN age < 75 THEN '65-74' ELSE '75+' END AS age_group
    FROM ${work_schema}.study_person_years${sfx}
),
totals AS (
    SELECT age_group, hiv, COUNT(*) AS person_years FROM banded GROUP BY 1, 2
),
with_condition AS (
    SELECT b.age_group, b.hiv, c.concept, c.label, COUNT(*) AS person_years_with
    FROM banded b
    JOIN ${work_schema}.person_year_conditions${sfx} c
      ON c.patient_id = b.patient_id AND c.analysis_year = b.analysis_year
    WHERE c.study_condition = 'yes'
    GROUP BY 1, 2, 3, 4
)
SELECT t.age_group, t.hiv, w.concept AS condition, w.label,
       t.person_years, w.person_years_with,
       ROUND(100.0 * w.person_years_with / t.person_years, 2) AS pct_with_condition
FROM totals t
JOIN with_condition w ON w.age_group = t.age_group AND w.hiv = t.hiv
ORDER BY 1, 3, 2;

-- check: how many study conditions each person-year has (multimorbidity = 2 or more)
-- result: condition_count_before_matching
WITH per_person_year AS (
    SELECT p.patient_id, p.analysis_year, p.hiv,
           COUNT(c.concept) AS conditions
    FROM ${work_schema}.study_person_years${sfx} p
    LEFT JOIN ${work_schema}.person_year_conditions${sfx} c
      ON c.patient_id = p.patient_id AND c.analysis_year = p.analysis_year
     AND c.study_condition = 'yes'
    GROUP BY 1, 2, 3
)
SELECT hiv,
       LEAST(conditions, 4) AS n_conditions,   -- 4 means 4 or more
       COUNT(*) AS person_years,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (PARTITION BY hiv), 2) AS pct_of_group
FROM per_person_year
GROUP BY 1, 2
ORDER BY 1, 2;
