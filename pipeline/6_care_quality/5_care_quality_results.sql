-- Care quality 5: for each measure, the share of matched person-years in its denominator that
-- met it, people with HIV against their matched controls. pct_met uses the match weights (all
-- 1 with 1:1 matching); counts are people, unweighted. higher_is_better = 0 marks a measure
-- where a higher share is worse care (HbA1c above 9% or not tested).
-- These are descriptive rates: no confidence intervals and no adjustment for repeated years
-- per person (methods are still to be agreed with the PI).

-- check: each measure over all study years
-- result: care_quality_overall
SELECT q.measure_id, r.condition, r.label, r.higher_is_better, m.hiv,
       COUNT(*)   AS person_years,
       SUM(q.met) AS person_years_met,
       ROUND((100.0 * SUM(m.match_weight * q.met) / SUM(m.match_weight))::DECIMAL(18, 6), 2) AS pct_met
FROM ${work_schema}.quality_measures${sfx} q
JOIN ${work_schema}.ps_matched${sfx} m ON m.patient_id = q.patient_id AND m.analysis_year = q.analysis_year
JOIN ${work_schema}.ref_measures${sfx} r ON r.measure_id = q.measure_id
GROUP BY 1, 2, 3, 4, 5
ORDER BY 1, 5;

-- check: each measure per year (how care changes over time)
-- result: care_quality_by_year
SELECT q.measure_id, q.analysis_year, m.hiv,
       COUNT(*)   AS person_years,
       SUM(q.met) AS person_years_met,
       ROUND((100.0 * SUM(m.match_weight * q.met) / SUM(m.match_weight))::DECIMAL(18, 6), 2) AS pct_met
FROM ${work_schema}.quality_measures${sfx} q
JOIN ${work_schema}.ps_matched${sfx} m ON m.patient_id = q.patient_id AND m.analysis_year = q.analysis_year
GROUP BY 1, 2, 3
ORDER BY 1, 2, 3;

-- check: each measure by Gagne level: people with HIV and controls who are about as sick
-- (Gagne score without the HIV/AIDS group; levels from config gagne.level_tops)
-- result: care_quality_by_gagne_level
SELECT q.measure_id, ${gagne_level} AS gagne_level, m.hiv,
       COUNT(*)   AS person_years,
       SUM(q.met) AS person_years_met,
       ROUND((100.0 * SUM(m.match_weight * q.met) / SUM(m.match_weight))::DECIMAL(18, 6), 2) AS pct_met
FROM ${work_schema}.quality_measures${sfx} q
JOIN ${work_schema}.ps_matched${sfx} m ON m.patient_id = q.patient_id AND m.analysis_year = q.analysis_year
JOIN ${work_schema}.gagne_scores${sfx} g ON g.patient_id = q.patient_id AND g.analysis_year = q.analysis_year
GROUP BY 1, 2, 3
ORDER BY 1, 2, 3;

-- check: each measure by age group (protocol: care quality by age)
-- result: care_quality_by_age
SELECT q.measure_id,
       CASE WHEN s.age < 65 THEN '50-64' WHEN s.age < 75 THEN '65-74' ELSE '75+' END AS age_group,
       m.hiv,
       COUNT(*)   AS person_years,
       SUM(q.met) AS person_years_met,
       ROUND((100.0 * SUM(m.match_weight * q.met) / SUM(m.match_weight))::DECIMAL(18, 6), 2) AS pct_met
FROM ${work_schema}.quality_measures${sfx} q
JOIN ${work_schema}.ps_matched${sfx} m ON m.patient_id = q.patient_id AND m.analysis_year = q.analysis_year
JOIN ${work_schema}.study_person_years${sfx} s ON s.patient_id = q.patient_id AND s.analysis_year = q.analysis_year
GROUP BY 1, 2, 3
ORDER BY 1, 2, 3;
