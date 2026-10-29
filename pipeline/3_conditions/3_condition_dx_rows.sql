-- Conditions 3 [HEAVY]: read the diagnosis table once per year for everyone in the study.
-- Keeps only codes whose first 3 characters could belong to a condition (the roots of
-- reference/conditions.csv, as literal values so Spectrum filters inside the scan), counted
-- per person, year, code and setting. Exact prefixes are matched in step 4, on distinct codes.
-- One statement per year: Komodo is a Spectrum table, and one year at a time stays within its
-- time limit (a year that times out is retried).
-- Output: ${work_schema}.condition_dx_rows${sfx}

DROP TABLE IF EXISTS ${work_schema}.condition_dx_rows${sfx};

CREATE TABLE ${work_schema}.condition_dx_rows${sfx} (
    patient_id    VARCHAR(100),
    analysis_year SMALLINT,
    dx_code       VARCHAR(10),
    inpatient     SMALLINT,
    claims        BIGINT,
    first_date    DATE,
    last_date     DATE
) DISTKEY(patient_id) SORTKEY(patient_id, analysis_year);

-- for each year: study
INSERT INTO ${work_schema}.condition_dx_rows${sfx}
SELECT s.patient_id, ${year}, s.dx_code, s.inpatient, s.claims, s.first_date, s.last_date
FROM (
    SELECT patient_id,
           UPPER(REPLACE(dx_code, '.', ''))::VARCHAR(10)                    AS dx_code,
           CASE WHEN source_table = 'INPATIENT_EVENTS' THEN 1 ELSE 0 END  AS inpatient,
           COUNT(*)                                                       AS claims,
           MIN(event_date)::DATE                                          AS first_date,
           MAX(event_date)::DATE                                          AS last_date
    FROM ${komodo_schema}.normalized_dx_events
    WHERE event_date >= '${year}-01-01'
      AND event_date <  '${next_year}-01-01'
      AND source_table IN ('INPATIENT_EVENTS', 'NON_INPATIENT_EVENTS')
      AND LEFT(dx_code, 3) IN (${condition_roots})
      AND ${sample_filter}
    GROUP BY 1, 2, 3
) s
JOIN ${work_schema}.study_person_years${sfx} p
  ON p.patient_id = s.patient_id
 AND p.analysis_year = ${year};

-- check: rows kept per year
-- result: condition_dx_rows_by_year
SELECT analysis_year, COUNT(*) AS code_rows, COUNT(DISTINCT dx_code) AS distinct_codes
FROM ${work_schema}.condition_dx_rows${sfx}
GROUP BY 1
ORDER BY 1;
