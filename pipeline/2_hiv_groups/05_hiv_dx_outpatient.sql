-- 05 finds people with HIV based on outpatient records
-- (people with HIV diagnoses on 2 outpatient dates at least 7 days apart).
-- Codes from protocol Supplement 1: B20, B21.x, B22.x, B23.x, B24, B97.35, R75, Z21
-- R75 alone is not enough: the person must also have an HIV claim that is not R75.
-- Only looks at eligible people (File 03), and at their claims from any year 2016-2025.
-- Output: ${work_schema}.hiv_dx_outpatient${sfx} (one row per person)

DROP TABLE IF EXISTS ${work_schema}.hiv_dx_outpatient${sfx};

CREATE TABLE ${work_schema}.hiv_dx_outpatient${sfx} AS
SELECT patient_id,
       MIN(CASE WHEN source_table = 'NON_INPATIENT_EVENTS' THEN event_date END) AS first_date,
       MAX(CASE WHEN source_table = 'NON_INPATIENT_EVENTS' THEN event_date END) AS last_date
FROM ${komodo_schema}.normalized_dx_events
WHERE dx_code IN ('B20',
                  'B210', 'B211', 'B212', 'B213', 'B217', 'B218', 'B219',
                  'B220', 'B221', 'B222', 'B227',
                  'B230', 'B231', 'B232', 'B238',
                  'B24', 'B9735', 'B97.35', 'R75', 'Z21')
  AND event_date >= '${study_start}'
  AND event_date <  '${study_end}'
  AND patient_id IN (SELECT patient_id FROM ${work_schema}.eligible_ids${sfx})   -- only eligible people (File 03)
GROUP BY patient_id
HAVING
    -- Rule 1: 2 outpatient HIV dates at least 7 days apart
    -- (if the earliest and latest outpatient dates are 7+ days apart, such a pair exists)
    MAX(CASE WHEN source_table = 'NON_INPATIENT_EVENTS' THEN event_date END)
  - MIN(CASE WHEN source_table = 'NON_INPATIENT_EVENTS' THEN event_date END) >= 7
    -- Rule 2: the R75 exception (same structure as File 04)
    AND (
        -- outpatient HIV code that is not R75
        SUM(CASE WHEN source_table = 'NON_INPATIENT_EVENTS'
                  AND dx_code <> 'R75' THEN 1 ELSE 0 END) >= 1
        -- or outpatient R75, plus some other HIV code that is not R75 (any setting)
     OR (SUM(CASE WHEN source_table = 'NON_INPATIENT_EVENTS'
                   AND dx_code = 'R75' THEN 1 ELSE 0 END) >= 1
         AND SUM(CASE WHEN dx_code <> 'R75' THEN 1 ELSE 0 END) >= 1)
    );

-- check
-- result: hiv_outpatient_people
SELECT COUNT(*) AS people FROM ${work_schema}.hiv_dx_outpatient${sfx};