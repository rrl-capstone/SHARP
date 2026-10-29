-- 04 finds people with HIV based on inpatient records
-- (people with at least 1 inpatient claim with an HIV diagnosis).
-- Codes from protocol Supplement 1: B20, B21.x, B22.x, B23.x, B24, B97.35, R75, Z21
-- An inpatient R75 only counts if the person also has an HIV claim that is not R75.
-- Only looks at eligible people (File 03), and at their claims from any year 2016-2025.
-- Output: ${work_schema}.hiv_dx_inpatient${sfx} (one row per person)

DROP TABLE IF EXISTS ${work_schema}.hiv_dx_inpatient${sfx};

CREATE TABLE ${work_schema}.hiv_dx_inpatient${sfx} AS
SELECT patient_id,
       MIN(CASE WHEN source_table = 'INPATIENT_EVENTS' THEN event_date END) AS first_date,
       MAX(CASE WHEN source_table = 'INPATIENT_EVENTS' THEN event_date END) AS last_date
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
    -- inpatient HIV code that is not R75
    SUM(CASE WHEN source_table = 'INPATIENT_EVENTS'
              AND dx_code <> 'R75' THEN 1 ELSE 0 END) >= 1
    -- or inpatient R75, plus some other HIV code that is not R75 (any setting)
    OR (SUM(CASE WHEN source_table = 'INPATIENT_EVENTS'
                  AND dx_code = 'R75' THEN 1 ELSE 0 END) >= 1
        AND SUM(CASE WHEN dx_code <> 'R75' THEN 1 ELSE 0 END) >= 1);

-- add people who have an HIV MS-DRG (Supplement 1) but were not found above
INSERT INTO ${work_schema}.hiv_dx_inpatient${sfx}
SELECT patient_id, MIN(admit_date), MAX(admit_date)
FROM ${komodo_schema}.inpatient_events
WHERE drg_code IN ('969', '970', '974', '975', '976', '977')
  AND admit_date >= '${study_start}' AND admit_date < '${study_end}'
  AND patient_id IN (SELECT patient_id FROM ${work_schema}.eligible_ids${sfx})   -- only eligible people (File 03)
  AND patient_id NOT IN (SELECT patient_id FROM ${work_schema}.hiv_dx_inpatient${sfx}
                         WHERE patient_id IS NOT NULL)
GROUP BY patient_id;

-- check
-- result: hiv_inpatient_people
SELECT COUNT(*) AS people FROM ${work_schema}.hiv_dx_inpatient${sfx};
