-- 12: The matched groups (File 11's ps_matched), and the comparison AFTER matching.
-- Averages use match_weight (all 1 with 1:1 matching), so they stay right for 1:k matching.
-- Counts are of people, unweighted.

-- check: one row per matched person-year (Rhea's Gagne code needs this)
-- result: matched_one_row_per_person_year
-- expect: rows_total = person_years
SELECT COUNT(*) AS rows_total,
       COUNT(DISTINCT patient_id || '-' || analysis_year) AS person_years
FROM ${work_schema}.ps_matched${sfx};

-- check: people with HIV matched, and dropped (no control within the caliper), per year
-- result: matched_by_year
WITH hiv_group AS (
    SELECT analysis_year, COUNT(*) AS hiv_people FROM ${work_schema}.pwh_cohort${sfx} GROUP BY 1
),
matched AS (
    SELECT analysis_year,
           SUM(hiv)     AS hiv_matched,
           SUM(1 - hiv) AS controls_matched,
           COUNT(DISTINCT pair_id) AS matched_sets
    FROM ${work_schema}.ps_matched${sfx}
    GROUP BY 1
)
SELECT h.analysis_year, h.hiv_people, m.hiv_matched, h.hiv_people - m.hiv_matched AS hiv_not_matched,
       m.controls_matched, m.matched_sets,
       ROUND(100.0 * m.hiv_matched / h.hiv_people, 2) AS pct_hiv_matched
FROM hiv_group h
JOIN matched m ON m.analysis_year = h.analysis_year
ORDER BY 1;

-- check: the base populations before matching (HIV group vs control pool) and the matched groups
-- after, on the matching variables (the PI's "Table 1"). After matching the shares should be
-- close; File 11 saves the standardized mean differences before and after (balance_smd.csv).
-- result: characteristics_before_and_after_matching
WITH before_after AS (
    SELECT 'before'::VARCHAR(10) AS stage, hiv, 1.0::FLOAT8 AS weight, age, patient_gender,
           patient_race_ethnicity, census_region
    FROM ${work_schema}.study_person_years${sfx}
    UNION ALL
    SELECT 'after', m.hiv, m.match_weight, s.age, s.patient_gender,
           s.patient_race_ethnicity, s.census_region
    FROM ${work_schema}.ps_matched${sfx} m
    JOIN ${work_schema}.study_person_years${sfx} s
      ON s.patient_id = m.patient_id AND s.analysis_year = m.analysis_year
),
by_variable AS (
    SELECT stage, hiv, weight, 'sex'::VARCHAR(30) AS variable, patient_gender::VARCHAR(200) AS category
    FROM before_after
    UNION ALL
    SELECT stage, hiv, weight, 'age group',
           CASE WHEN age < 65 THEN '50-64' WHEN age < 75 THEN '65-74' ELSE '75+' END FROM before_after
    UNION ALL
    SELECT stage, hiv, weight, 'race and ethnicity', patient_race_ethnicity FROM before_after
    UNION ALL
    SELECT stage, hiv, weight, 'census region', census_region FROM before_after
)
SELECT stage, variable, category, hiv, COUNT(*) AS person_years,
       ROUND((100.0 * SUM(weight) / SUM(SUM(weight)) OVER (PARTITION BY stage, variable, hiv))::DECIMAL(18, 6), 2)
           AS pct_of_group
FROM by_variable
GROUP BY 1, 2, 3, 4
ORDER BY 1 DESC, 2, 3, 4;

-- check: mean age before and after matching
-- result: age_before_and_after_matching
SELECT 'before'::VARCHAR(10) AS stage, hiv, COUNT(*) AS person_years,
       ROUND(AVG(age::FLOAT8)::DECIMAL(18, 6), 2) AS mean_age
FROM ${work_schema}.study_person_years${sfx}
GROUP BY 1, 2
UNION ALL
SELECT 'after', m.hiv, COUNT(*),
       ROUND((SUM(m.match_weight * s.age) / SUM(m.match_weight))::DECIMAL(18, 6), 2)
FROM ${work_schema}.ps_matched${sfx} m
JOIN ${work_schema}.study_person_years${sfx} s
  ON s.patient_id = m.patient_id AND s.analysis_year = m.analysis_year
GROUP BY 1, 2
ORDER BY 1 DESC, 2;

-- check: CONSORT diagram for the first study year (PI, Oct 2026): how many people each
-- inclusion or exclusion step leaves, from everyone in Komodo to the matched groups
-- result: consort_first_year
SELECT 1 AS step_order, 'Everyone in Komodo'::VARCHAR(120) AS step, COUNT(*) AS people
FROM ${komodo_schema}.patient_demographics
UNION ALL
SELECT 2, 'In this run (the 1% sample, or everyone)', COUNT(*) FROM ${work_schema}.study_ids${sfx}
UNION ALL
SELECT 3, 'Aged 50 or older on Dec 31 and alive all year', COUNT(*)
FROM ${work_schema}.age50_alive${sfx} WHERE yr = ${first_year}
UNION ALL
SELECT 4, 'Medical and pharmacy closed all year, one medical and one pharmacy payer', COUNT(*)
FROM ${work_schema}.same_insurance${sfx} WHERE yr = ${first_year}
UNION ALL
SELECT 5, 'No missing birth date, sex, state or race (eligible)', COUNT(*)
FROM ${work_schema}.eligible_person_years${sfx} WHERE analysis_year = ${first_year}
UNION ALL
SELECT 6, 'People with HIV', COUNT(*) FROM ${work_schema}.pwh_cohort${sfx} WHERE analysis_year = ${first_year}
UNION ALL
SELECT 7, 'People without HIV (control pool)', COUNT(*) FROM ${work_schema}.nonhiv_pool${sfx} WHERE analysis_year = ${first_year}
UNION ALL
SELECT 8, 'Eligible but in neither group (HIV found in a later year, or not closed since the HIV date)',
       (SELECT COUNT(*) FROM ${work_schema}.eligible_person_years${sfx} WHERE analysis_year = ${first_year})
     - (SELECT COUNT(*) FROM ${work_schema}.pwh_cohort${sfx} WHERE analysis_year = ${first_year})
     - (SELECT COUNT(*) FROM ${work_schema}.nonhiv_pool${sfx} WHERE analysis_year = ${first_year})
UNION ALL
SELECT 9, 'People with HIV matched', SUM(hiv) FROM ${work_schema}.ps_matched${sfx} WHERE analysis_year = ${first_year}
UNION ALL
SELECT 10, 'Matched controls', SUM(1 - hiv) FROM ${work_schema}.ps_matched${sfx} WHERE analysis_year = ${first_year}
ORDER BY 1;

-- check: share of matched person-years with each study condition, per year and HIV status
-- result: conditions_after_matching_by_year
WITH totals AS (
    SELECT analysis_year, hiv, COUNT(*) AS person_years, SUM(match_weight) AS weight
    FROM ${work_schema}.ps_matched${sfx}
    GROUP BY 1, 2
),
with_condition AS (
    SELECT m.analysis_year, m.hiv, c.concept, c.label,
           COUNT(*) AS person_years_with, SUM(m.match_weight) AS weight
    FROM ${work_schema}.ps_matched${sfx} m
    JOIN ${work_schema}.person_year_conditions${sfx} c
      ON c.patient_id = m.patient_id AND c.analysis_year = m.analysis_year
    WHERE c.study_condition = 'yes'
    GROUP BY 1, 2, 3, 4
)
SELECT t.analysis_year, t.hiv, w.concept AS condition, w.label,
       t.person_years, w.person_years_with,
       ROUND((100.0 * w.weight / t.weight)::DECIMAL(18, 6), 2) AS pct_with_condition
FROM totals t
JOIN with_condition w ON w.analysis_year = t.analysis_year AND w.hiv = t.hiv
ORDER BY 1, 3, 2;

-- check: the same over all study years, by age group
-- result: conditions_after_matching_by_age
WITH banded AS (
    SELECT m.patient_id, m.analysis_year, m.hiv, m.match_weight,
           CASE WHEN s.age < 65 THEN '50-64' WHEN s.age < 75 THEN '65-74' ELSE '75+' END AS age_group
    FROM ${work_schema}.ps_matched${sfx} m
    JOIN ${work_schema}.study_person_years${sfx} s
      ON s.patient_id = m.patient_id AND s.analysis_year = m.analysis_year
),
totals AS (
    SELECT age_group, hiv, COUNT(*) AS person_years, SUM(match_weight) AS weight FROM banded GROUP BY 1, 2
),
with_condition AS (
    SELECT b.age_group, b.hiv, c.concept, c.label,
           COUNT(*) AS person_years_with, SUM(b.match_weight) AS weight
    FROM banded b
    JOIN ${work_schema}.person_year_conditions${sfx} c
      ON c.patient_id = b.patient_id AND c.analysis_year = b.analysis_year
    WHERE c.study_condition = 'yes'
    GROUP BY 1, 2, 3, 4
)
SELECT t.age_group, t.hiv, w.concept AS condition, w.label,
       t.person_years, w.person_years_with,
       ROUND((100.0 * w.weight / t.weight)::DECIMAL(18, 6), 2) AS pct_with_condition
FROM totals t
JOIN with_condition w ON w.age_group = t.age_group AND w.hiv = t.hiv
ORDER BY 1, 3, 2;

-- check: how many study conditions each matched person-year has
-- result: condition_count_after_matching
WITH per_person_year AS (
    SELECT m.patient_id, m.analysis_year, m.hiv, m.match_weight,
           COUNT(c.concept) AS conditions
    FROM ${work_schema}.ps_matched${sfx} m
    LEFT JOIN ${work_schema}.person_year_conditions${sfx} c
      ON c.patient_id = m.patient_id AND c.analysis_year = m.analysis_year
     AND c.study_condition = 'yes'
    GROUP BY 1, 2, 3, 4
)
SELECT hiv,
       LEAST(conditions, 4) AS n_conditions,   -- 4 means 4 or more
       COUNT(*) AS person_years,
       ROUND((100.0 * SUM(match_weight) / SUM(SUM(match_weight)) OVER (PARTITION BY hiv))::DECIMAL(18, 6), 2)
           AS pct_of_group
FROM per_person_year
GROUP BY 1, 2
ORDER BY 1, 2;
