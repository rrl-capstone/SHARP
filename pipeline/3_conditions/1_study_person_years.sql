-- Conditions 1: everyone the comparisons are about, with HIV status and the characteristics
-- used to describe the groups before and after matching (stage 4).
-- The HIV group (File 07) and the control pool (File 09), one row per person-year. Conditions
-- are found once for all of them, so the comparison before matching (this stage) and after
-- matching (stage 4) use exactly the same flags.
-- An HIV case's years before HIV was first found are in neither group (File 09).
-- Output: ${work_schema}.study_person_years${sfx}

DROP TABLE IF EXISTS ${work_schema}.study_person_years${sfx};

CREATE TABLE ${work_schema}.study_person_years${sfx}
DISTKEY(patient_id) SORTKEY(patient_id, analysis_year) AS
SELECT patient_id, analysis_year, 1 AS hiv, age, patient_gender, patient_race_ethnicity,
       ${census_region} AS census_region
FROM ${work_schema}.pwh_cohort${sfx}
UNION ALL
SELECT patient_id, analysis_year, 0 AS hiv, age, patient_gender, patient_race_ethnicity,
       ${census_region} AS census_region
FROM ${work_schema}.nonhiv_pool${sfx};

-- check: person-years in each group per year
-- result: study_person_years_by_year
SELECT analysis_year, hiv, COUNT(*) AS person_years
FROM ${work_schema}.study_person_years${sfx}
GROUP BY 1, 2
ORDER BY 1, 2;

-- check: nobody is in both groups in the same year
-- result: study_one_row_per_person_year
-- expect: rows_total = person_years
SELECT COUNT(*) AS rows_total,
       COUNT(DISTINCT patient_id || '-' || analysis_year) AS person_years
FROM ${work_schema}.study_person_years${sfx};
