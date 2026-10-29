-- 01: One row per person per study year (2016-2025, config study_years), kept only if on that year's
-- index date (Dec 31) the person is aged 50+ and was alive the whole year.
--   Age = year - birth year. People with no birth date are dropped (age unknown).
--   Alive the whole year = no death date, or death date after Dec 31 of that year.
-- Input: study_ids (File 00)
-- Output: ${work_schema}.age50_alive${sfx} (one row per person-year)

-- Death data: ${komodo_schema}.patient_mortality.patient_death_date

DROP TABLE IF EXISTS ${work_schema}.age50_alive${sfx};

CREATE TABLE ${work_schema}.age50_alive${sfx} AS
WITH years AS (
    ${study_years_select}
),
deaths AS (
    SELECT patient_id, MIN(patient_death_date) AS death_date
    FROM ${komodo_schema}.patient_mortality
    GROUP BY patient_id
)
SELECT s.patient_id,
       y.yr,
       TO_DATE(y.yr || '-01-01', 'YYYY-MM-DD') AS year_start,
       TO_DATE(y.yr || '-12-31', 'YYYY-MM-DD') AS year_end,
       y.yr - EXTRACT(YEAR FROM d.patient_dob) AS age
FROM ${work_schema}.study_ids${sfx} s
JOIN ${komodo_schema}.patient_demographics d ON d.patient_id = s.patient_id
JOIN years y ON y.yr - EXTRACT(YEAR FROM d.patient_dob) >= 50
LEFT JOIN deaths dt ON dt.patient_id = s.patient_id
WHERE d.patient_dob IS NOT NULL
  AND (dt.death_date IS NULL OR dt.death_date > TO_DATE(y.yr || '-12-31', 'YYYY-MM-DD'));

-- check: people per year
-- result: age50_alive_by_year
SELECT yr, COUNT(*) AS people FROM ${work_schema}.age50_alive${sfx} GROUP BY yr ORDER BY yr;
