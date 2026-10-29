-- Figure 3: What percent of patients aged 50+ have hypertension, HIV group vs. non-HIV group?

-- Instead of checking all 59 million people aged 50+, we compare the HIV group with a random 1% sample of people without HIV.
-- Uses the hiv_50plus table made by file 02.

-- Hypertension: at least 1 diagnosis code from I10 to I16, in 2016-2025.
-- Rough numbers only: the two groups are not matched yet.

-- Step 1: pick a random 1% sample of people aged 50+ without HIV (about 590k people)

CREATE TABLE work_wang_life297.nonhiv_sample AS
SELECT DISTINCT d.patient_id
FROM komodo_202606.patient_demographics d
LEFT JOIN work_wang_life297.hiv_50plus h ON h.patient_id = d.patient_id
WHERE EXTRACT(YEAR FROM d.patient_dob) <= 1975
  AND h.patient_id IS NULL
  AND MOD(STRTOL(LEFT(MD5(d.patient_id::VARCHAR), 8), 16), 100) = 0;

-- Step 2: compare hypertension in the two groups
WITH people AS (
    SELECT patient_id, 'HIV+' AS hiv_status
    FROM work_wang_life297.hiv_50plus
    UNION ALL
    SELECT patient_id, 'HIV- (1% sample)'
    FROM work_wang_life297.nonhiv_sample
),
htn AS (
    SELECT DISTINCT dx.patient_id
    FROM komodo_202606.normalized_dx_events dx
    JOIN people p ON p.patient_id = dx.patient_id
    WHERE dx.dx_code >= 'I10' AND dx.dx_code < 'I17'
      AND dx.event_date >= '2016-01-01'
      AND dx.event_date <  '2026-01-01'
)
SELECT p.hiv_status,
       COUNT(*) AS total_patients,
       COUNT(h.patient_id) AS patients_with_hypertension,
       ROUND(100.0 * COUNT(h.patient_id) / COUNT(*), 1) AS percent_with_hypertension
FROM people p
LEFT JOIN htn h ON h.patient_id = p.patient_id
GROUP BY p.hiv_status
ORDER BY p.hiv_status;
