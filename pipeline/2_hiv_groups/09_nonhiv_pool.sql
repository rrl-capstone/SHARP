-- 09: Build the pool of people without HIV (the control pool).
-- Start from all eligible person-years (File 03: aged 50+, alive all year,
-- closed and same insurance all year, no missing demographics),
-- then drop every person who is an HIV case (File 07, pwh_all), in ALL years,
-- including years before their HIV was first found.
-- PI (Oct 2026 lab meeting): "anybody who is not a case of HIV can be a control", even someone
-- with a single HIV drug fill or code, so the control pool is not limited; propensity matching
-- handles the confounding. (Lifei's first version also dropped anyone with any HIV evidence,
-- File 08; the check below reports how many such people are now controls.)
-- Output: ${work_schema}.nonhiv_pool${sfx} (one row per person-year)

DROP TABLE IF EXISTS ${work_schema}.nonhiv_pool${sfx};

CREATE TABLE ${work_schema}.nonhiv_pool${sfx} AS
SELECT e.patient_id,
       e.analysis_year,
       e.index_date,
       e.age,
       e.birth_year,
       e.patient_gender,
       e.patient_state,
       e.patient_race_ethnicity
FROM ${work_schema}.eligible_person_years${sfx} e
LEFT JOIN ${work_schema}.pwh_all${sfx} p ON p.patient_id = e.patient_id
WHERE p.patient_id IS NULL;   -- keep only people who are not HIV cases

-- check: people in the pool with some HIV record (File 08) who are not HIV cases
-- result: controls_with_some_hiv_record
SELECT COUNT(DISTINCT n.patient_id) AS people
FROM ${work_schema}.nonhiv_pool${sfx} n
JOIN ${work_schema}.any_hiv_evidence_ids${sfx} h ON h.patient_id = n.patient_id;

-- check: people per year
-- result: control_pool_by_year
SELECT analysis_year, COUNT(*) AS people FROM ${work_schema}.nonhiv_pool${sfx} GROUP BY 1 ORDER BY 1;

-- check: no one with HIV should be in the pool (should be 0)
-- result: control_pool_hiv_check
-- expect: hiv_people_in_pool = 0
SELECT COUNT(*) AS hiv_people_in_pool
FROM ${work_schema}.nonhiv_pool${sfx} n
JOIN ${work_schema}.pwh_all${sfx} p ON p.patient_id = n.patient_id;
