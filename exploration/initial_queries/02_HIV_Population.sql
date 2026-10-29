-- Figure 2: How many patients aged 50+ have HIV
-- HIV rule (from the protocol): at least 1 inpatient HIV diagnosis, or HIV diagnoses on 2+ different outpatient dates.
-- HIV codes: B20 and Z21. Years: 2016-2025.
-- The result is saved as a table in my own work schema, so file 03 can reuse it.


-- Step 1: build the HIV 50+ list
CREATE TABLE work_wang_life297.hiv_50plus AS
WITH hiv_dx AS (
    SELECT patient_id, event_date, source_table
    FROM komodo_202606.normalized_dx_events
    WHERE ((dx_code >= 'B20' AND dx_code < 'B21')
        OR (dx_code >= 'Z21' AND dx_code < 'Z22'))
      AND event_date >= '2016-01-01'
      AND event_date <  '2026-01-01'
),
hiv AS (
    SELECT patient_id
    FROM hiv_dx
    GROUP BY patient_id
    HAVING SUM(CASE WHEN source_table = 'INPATIENT_EVENTS' THEN 1 ELSE 0 END) >= 1
        OR COUNT(DISTINCT CASE WHEN source_table = 'NON_INPATIENT_EVENTS'
                               THEN event_date END) >= 2
)
SELECT DISTINCT h.patient_id
FROM hiv h
JOIN komodo_202606.patient_demographics d ON d.patient_id = h.patient_id
WHERE EXTRACT(YEAR FROM d.patient_dob) <= 1975;

-- Step 2: count them
SELECT COUNT(*) AS hiv_patients_50_plus
FROM work_wang_life297.hiv_50plus;
