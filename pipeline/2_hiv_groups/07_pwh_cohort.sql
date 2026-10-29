-- 07: Build the final HIV group.
-- Part 1: everyone with HIV, by any of the 3 rules (Files 04, 05, 06).
-- Part 2: keep their eligible person-years (File 03) from the year they are first
--         known to have HIV, as long as they stayed closed from the HIV date onward.
-- Outputs:
--   ${work_schema}.pwh_all${sfx}    (one row per person with HIV)
--   ${work_schema}.pwh_cohort${sfx} (final HIV group, one row per person-year)


-- Part 1: Everyone with HIV, by any of the 3 rules:
--   File 04: found through inpatient records
--   File 05: found through outpatient records
--   File 06: found through HIV drug fills
-- Keeps the first and most recent date we know they have HIV,
-- plus which rule(s) found them.
DROP TABLE IF EXISTS ${work_schema}.pwh_all${sfx};

CREATE TABLE ${work_schema}.pwh_all${sfx} AS
SELECT patient_id,
       MIN(first_date) AS first_hiv_date,
       MAX(last_date)  AS last_hiv_date,
       MAX(by_inpatient)  AS by_inpatient,
       MAX(by_outpatient) AS by_outpatient,
       MAX(by_rx)         AS by_rx
FROM (
    SELECT patient_id, first_date, last_date, 1 AS by_inpatient, 0 AS by_outpatient, 0 AS by_rx
    FROM ${work_schema}.hiv_dx_inpatient${sfx}
    UNION ALL
    SELECT patient_id, first_date, last_date, 0, 1, 0
    FROM ${work_schema}.hiv_dx_outpatient${sfx}
    UNION ALL
    SELECT patient_id, first_date, last_date, 0, 0, 1
    FROM ${work_schema}.hiv_rx${sfx}
) x
GROUP BY patient_id;

-- check: total, and how many found by each rule
-- result: hiv_people_by_rule
SELECT COUNT(*) AS people,
       SUM(by_inpatient)  AS by_inpatient,
       SUM(by_outpatient) AS by_outpatient,
       SUM(by_rx)         AS by_rx
FROM ${work_schema}.pwh_all${sfx};

-- check: overlap between the 3 rules (each person is counted in exactly one row)
--   e.g. "inpatient only" = found by File 04 but not by 05 or 06
-- result: hiv_rule_overlap
SELECT CASE
         WHEN by_inpatient = 1 AND by_outpatient = 0 AND by_rx = 0 THEN '1 inpatient only'
         WHEN by_inpatient = 0 AND by_outpatient = 1 AND by_rx = 0 THEN '2 outpatient only'
         WHEN by_inpatient = 0 AND by_outpatient = 0 AND by_rx = 1 THEN '3 medication only'
         WHEN by_inpatient = 1 AND by_outpatient = 1 AND by_rx = 0 THEN '4 inpatient + outpatient'
         WHEN by_inpatient = 1 AND by_outpatient = 0 AND by_rx = 1 THEN '5 inpatient + medication'
         WHEN by_inpatient = 0 AND by_outpatient = 1 AND by_rx = 1 THEN '6 outpatient + medication'
         WHEN by_inpatient = 1 AND by_outpatient = 1 AND by_rx = 1 THEN '7 all three'
       END AS found_by,
       COUNT(*) AS people
FROM ${work_schema}.pwh_all${sfx}
GROUP BY 1
UNION ALL
SELECT '8 overall (anyone found by any rule)', COUNT(*)
FROM ${work_schema}.pwh_all${sfx}
ORDER BY 1;


-- Part 2: Final HIV group.
-- Confirmed by the professor: HIV cannot be cured, so once someone is an HIV case
-- they count as HIV in every later year, even with no HIV claims that year,
-- as long as they stayed closed from the HIV date onward.
-- Closed check: one MX CLOSED row and one RX CLOSED row covering the first HIV date
-- (or Jan 1, if that is earlier) through Dec 31 of the year.
-- (Closed periods are never split into back-to-back rows, so one row must cover it.)

DROP TABLE IF EXISTS ${work_schema}.pwh_cohort${sfx};

CREATE TABLE ${work_schema}.pwh_cohort${sfx} AS
SELECT e.patient_id,
       e.analysis_year,
       e.index_date,
       e.age,
       p.first_hiv_date, p.last_hiv_date,
       p.by_inpatient, p.by_outpatient, p.by_rx,
       e.birth_year,
       e.patient_gender,
       e.patient_state,
       e.patient_race_ethnicity
FROM ${work_schema}.eligible_person_years${sfx} e
JOIN ${work_schema}.pwh_all${sfx} p ON p.patient_id = e.patient_id
WHERE e.analysis_year >= EXTRACT(YEAR FROM p.first_hiv_date)
  AND EXISTS (SELECT 1 FROM ${komodo_schema}.patient_closed c
              WHERE c.patient_id = e.patient_id
                AND c.closed_type = 'MX CLOSED'
                AND c.closed_start_date <= LEAST(e.year_start, p.first_hiv_date)
                AND c.closed_end_date   >= e.index_date)
  AND EXISTS (SELECT 1 FROM ${komodo_schema}.patient_closed c
              WHERE c.patient_id = e.patient_id
                AND c.closed_type = 'RX CLOSED'
                AND c.closed_start_date <= LEAST(e.year_start, p.first_hiv_date)
                AND c.closed_end_date   >= e.index_date);

-- check: people per year
-- result: hiv_group_by_year
SELECT analysis_year, COUNT(*) AS people FROM ${work_schema}.pwh_cohort${sfx} GROUP BY 1 ORDER BY 1;

-- check: should be one row per person-year (the two numbers should match)
-- result: hiv_group_one_row_per_person_year
-- expect: rows_total = person_years
SELECT COUNT(*) AS rows_total,
       COUNT(DISTINCT patient_id || '-' || analysis_year) AS person_years
FROM ${work_schema}.pwh_cohort${sfx};
