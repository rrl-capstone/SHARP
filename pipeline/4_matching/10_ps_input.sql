-- 10: Build the table for propensity score matching (read into R next).
-- Part 1: narrow down the control pool. For each year and sex, randomly keep
--         20 controls for every person with HIV in that year and sex.
--         (e.g. 2020 men: 500 with HIV -> keep 10,000 men without HIV from 2020)
--         Only year and sex are used here; birth year, census region, and race are left
--         for the propensity score to compare.
--         Census region (Northeast, Midwest, South, West; PI, Oct 2026) replaces state as the
--         geography for matching; it comes from patient_state via reference/census_regions.csv.
--         "Random" uses MD5 of the ID and year, so the same people are picked every run.
-- Part 2: stack the HIV group (hiv = 1) and the kept controls (hiv = 0) into one table.
-- Output: ${work_schema}.ps_input${sfx} (one row per person-year)

DROP TABLE IF EXISTS ${work_schema}.ps_input${sfx};

CREATE TABLE ${work_schema}.ps_input${sfx} AS
WITH hiv_counts AS (
    -- how many people with HIV in each year and sex
    SELECT analysis_year, patient_gender, COUNT(*) AS n_hiv
    FROM ${work_schema}.pwh_cohort${sfx}
    GROUP BY analysis_year, patient_gender
),
pool_ranked AS (
    -- give each control a random-looking order within its year and sex
    SELECT n.patient_id, n.analysis_year, n.birth_year, n.patient_gender,
           n.patient_state, n.patient_race_ethnicity,
           ROW_NUMBER() OVER (PARTITION BY n.analysis_year, n.patient_gender
                              ORDER BY MD5(n.patient_id || '-' || n.analysis_year)) AS rn
    FROM ${work_schema}.nonhiv_pool${sfx} n
),
controls AS (
    -- Part 1: keep the first 20 x n_hiv controls in each year and sex
    SELECT r.patient_id, r.analysis_year, r.birth_year, r.patient_gender,
           r.patient_state, r.patient_race_ethnicity
    FROM pool_ranked r
    JOIN hiv_counts h ON h.analysis_year  = r.analysis_year
                     AND h.patient_gender = r.patient_gender
    WHERE r.rn <= 20 * h.n_hiv   -- change the 20 here
)
-- Part 2: stack the two groups
SELECT analysis_year, patient_id, birth_year, patient_gender,
       patient_state, ${census_region} AS census_region, patient_race_ethnicity, 1 AS hiv
FROM ${work_schema}.pwh_cohort${sfx}
UNION ALL
SELECT analysis_year, patient_id, birth_year, patient_gender,
       patient_state, ${census_region} AS census_region, patient_race_ethnicity, 0 AS hiv
FROM controls;

-- check: people with and without HIV per year and sex (controls should be about 20x)
-- result: ps_input_by_year_sex
SELECT analysis_year, patient_gender,
       SUM(hiv)     AS with_hiv,
       SUM(1 - hiv) AS without_hiv
FROM ${work_schema}.ps_input${sfx}
GROUP BY 1, 2
ORDER BY 1, 2;

-- check: should be one row per person-year (the two numbers should match)
-- result: ps_input_one_row_per_person_year
-- expect: rows_total = person_years
SELECT COUNT(*) AS rows_total,
       COUNT(DISTINCT patient_id || '-' || analysis_year) AS person_years
FROM ${work_schema}.ps_input${sfx};
