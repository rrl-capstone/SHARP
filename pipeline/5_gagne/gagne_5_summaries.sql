-- Gagne step 5: Rhea's scores (gagne_2_scores.py) saved as result tables, for the website.
-- gagne_score_excl_hiv leaves out group 19 (HIV/AIDS), which controls cannot have: it is the
-- fair comparison. Averages use the match weights (all 1 with 1:1 matching).
-- Levels: config gagne.level_tops.

-- check: mean score per year and HIV status
-- result: gagne_scores_by_year
SELECT g.analysis_year, g.hiv, COUNT(*) AS person_years,
       ROUND((SUM(m.match_weight * g.gagne_score_excl_hiv) / SUM(m.match_weight))::DECIMAL(18, 6), 3)
           AS mean_score_excl_hiv,
       ROUND((SUM(m.match_weight * g.gagne_score) / SUM(m.match_weight))::DECIMAL(18, 6), 3) AS mean_score,
       ROUND((SUM(m.match_weight * g.gagne_group_count) / SUM(m.match_weight))::DECIMAL(18, 6), 3) AS mean_groups
FROM ${work_schema}.gagne_scores${sfx} g
JOIN ${work_schema}.ps_matched${sfx} m ON m.patient_id = g.patient_id AND m.analysis_year = g.analysis_year
GROUP BY 1, 2
ORDER BY 1, 2;

-- check: share of person-years at each Gagne level (score without the HIV/AIDS group)
-- result: gagne_levels
WITH levelled AS (
    SELECT g.hiv, ${gagne_level} AS gagne_level, m.match_weight
    FROM ${work_schema}.gagne_scores${sfx} g
    JOIN ${work_schema}.ps_matched${sfx} m ON m.patient_id = g.patient_id AND m.analysis_year = g.analysis_year
)
SELECT hiv, gagne_level, COUNT(*) AS person_years,
       ROUND((100.0 * SUM(match_weight) / SUM(SUM(match_weight)) OVER (PARTITION BY hiv))::DECIMAL(18, 6), 2)
           AS pct_of_group
FROM levelled
GROUP BY 1, 2
ORDER BY 1, 2;

-- check: share of person-years with each Gagne group (names: reference/gagne_weight_lookup.csv)
-- result: gagne_group_prevalence
WITH totals AS (
    SELECT p.hiv, SUM(m.match_weight) AS weight
    FROM ${work_schema}.gagne_person_years${sfx} p
    JOIN ${work_schema}.ps_matched${sfx} m ON m.patient_id = p.patient_id AND m.analysis_year = p.analysis_year
    GROUP BY 1
)
SELECT p.hiv, e.gagne_group, COUNT(*) AS person_years_with,
       ROUND((100.0 * SUM(m.match_weight) / MAX(t.weight))::DECIMAL(18, 6), 2) AS pct_with_group
FROM ${work_schema}.gagne_group_evidence${sfx} e
JOIN ${work_schema}.gagne_person_years${sfx} p ON p.patient_id = e.patient_id AND p.analysis_year = e.analysis_year
JOIN ${work_schema}.ps_matched${sfx} m ON m.patient_id = e.patient_id AND m.analysis_year = e.analysis_year
JOIN totals t ON t.hiv = p.hiv
GROUP BY 1, 2
ORDER BY 2, 1;

-- check: the comorbidity network (Rhea's plot 7) as data, for the website. Nodes are
-- gagne_group_prevalence above; links are every pair of Gagne groups present together in a
-- matched person-year, by HIV status. lift = P(A and B) / (P(A) x P(B)): 1 = no link, 2 = the
-- pair occurs together twice as often as chance. As in gagne_4_network.py, pairs seen in fewer
-- than 11 person-years are dropped; unlike the plot, every pair is kept (the plot draws the
-- 25 strongest with lift >= 1.2, and leaves out group 19, HIV/AIDS).
-- result: gagne_network_links
WITH py AS (
    SELECT p.patient_id, p.analysis_year, p.hiv, m.match_weight
    FROM ${work_schema}.gagne_person_years${sfx} p
    JOIN ${work_schema}.ps_matched${sfx} m ON m.patient_id = p.patient_id AND m.analysis_year = p.analysis_year
),
totals AS (
    SELECT hiv, SUM(match_weight) AS weight FROM py GROUP BY 1
),
group_weights AS (
    SELECT py.hiv, e.gagne_group, SUM(py.match_weight) AS weight
    FROM ${work_schema}.gagne_group_evidence${sfx} e
    JOIN py ON py.patient_id = e.patient_id AND py.analysis_year = e.analysis_year
    GROUP BY 1, 2
),
pairs AS (
    SELECT py.hiv, a.gagne_group AS group_a, b.gagne_group AS group_b,
           COUNT(*) AS person_years_with_both, SUM(py.match_weight) AS weight
    FROM ${work_schema}.gagne_group_evidence${sfx} a
    JOIN ${work_schema}.gagne_group_evidence${sfx} b
      ON b.patient_id = a.patient_id
     AND b.analysis_year = a.analysis_year
     AND b.gagne_group > a.gagne_group          -- each pair once
    JOIN py ON py.patient_id = a.patient_id AND py.analysis_year = a.analysis_year
    GROUP BY 1, 2, 3
    HAVING COUNT(*) >= 11                        -- small-cell rule
)
SELECT p.hiv, p.group_a, p.group_b, p.person_years_with_both,
       ROUND((100.0 * p.weight / t.weight)::DECIMAL(18, 6), 3) AS pct_with_both,
       ROUND(((p.weight / t.weight) / ((ga.weight / t.weight) * (gb.weight / t.weight)))::DECIMAL(18, 6), 3)
           AS lift
FROM pairs p
JOIN totals t  ON t.hiv = p.hiv
JOIN group_weights ga ON ga.hiv = p.hiv AND ga.gagne_group = p.group_a
JOIN group_weights gb ON gb.hiv = p.hiv AND gb.gagne_group = p.group_b
ORDER BY 1, 2, 3;
