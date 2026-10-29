-- 03: Exclude participants with missing demographics (protocol).
-- Demographics = birth date, gender, state, and race. All 4 must be known (not missing).

-- Some values are filled in but still mean "unknown", so they count as missing too:
--   Field       Value                            Missing?
--   birth date  any date                         No
--   birth date  NULL                             Yes (already dropped in File 01)
--   gender      M, F                             No
--   gender      U (unknown)                      Yes
--   gender      NULL                             Yes
--   race        WHITE, BLACK, HISPANIC, ASIAN    No
--   race        OTHER                            No (a real category)
--   race        NULL                             Yes
--   race        UNKNOWN                          Yes
--   state       any state                        No
--   state       NULL                             Yes

-- State = where they lived on Dec 31 (index date); if more than one address
-- is valid that day, keep the newest one.

-- Input: same_insurance (File 02) + age50_alive (File 01)
-- Outputs:
--   ${work_schema}.eligible_person_years${sfx} (everyone eligible, with or without HIV;
--                                            one row per person-year; also the pool for controls)
--   ${work_schema}.eligible_ids${sfx}          (one row per eligible person; used by Files 04-06)

DROP TABLE IF EXISTS ${work_schema}.eligible_person_years${sfx};

CREATE TABLE ${work_schema}.eligible_person_years${sfx} AS
SELECT a.patient_id,
       a.yr       AS analysis_year,
       a.year_start,
       a.year_end AS index_date,
       a.age,
       EXTRACT(YEAR FROM d.patient_dob) AS birth_year,
       d.patient_gender,
       s.patient_state,
       r.patient_race_ethnicity
FROM ${work_schema}.same_insurance${sfx} ins
JOIN ${work_schema}.age50_alive${sfx} a        ON a.patient_id = ins.patient_id AND a.yr = ins.yr
JOIN ${komodo_schema}.patient_demographics d   ON d.patient_id = a.patient_id
JOIN ${komodo_schema}.patient_race_ethnicity r ON r.patient_id = a.patient_id
JOIN (
    -- state on Dec 31, newest address first
    SELECT a2.patient_id, a2.yr, g.patient_state,
           ROW_NUMBER() OVER (PARTITION BY a2.patient_id, a2.yr
                              ORDER BY g.valid_from_date DESC) AS rn
    FROM ${work_schema}.same_insurance${sfx} ins2
    JOIN ${work_schema}.age50_alive${sfx} a2  ON a2.patient_id = ins2.patient_id AND a2.yr = ins2.yr
    JOIN ${komodo_schema}.patient_geography g ON g.patient_id = a2.patient_id
    WHERE g.valid_from_date <= a2.year_end
      AND (g.valid_to_date >= a2.year_end OR g.valid_to_date IS NULL)
) s ON s.patient_id = a.patient_id AND s.yr = a.yr AND s.rn = 1
WHERE d.patient_gender <> 'U'
  AND s.patient_state IS NOT NULL
  AND r.patient_race_ethnicity <> 'UNKNOWN';

DROP TABLE IF EXISTS ${work_schema}.eligible_ids${sfx};

CREATE TABLE ${work_schema}.eligible_ids${sfx} AS
SELECT DISTINCT patient_id FROM ${work_schema}.eligible_person_years${sfx};

-- check: people per year
-- result: eligible_by_year
SELECT analysis_year, COUNT(*) AS people
FROM ${work_schema}.eligible_person_years${sfx} GROUP BY 1 ORDER BY 1;

-- check: should be one row per person-year (the two numbers should match)
-- result: eligible_one_row_per_person_year
-- expect: rows_total = person_years
SELECT COUNT(*) AS rows_total,
       COUNT(DISTINCT patient_id || '-' || analysis_year) AS person_years
FROM ${work_schema}.eligible_person_years${sfx};
