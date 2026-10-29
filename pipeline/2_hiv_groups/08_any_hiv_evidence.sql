-- 08: Find everyone with ANY HIV evidence in the study years. Since the Oct 2026 lab meeting this
-- is only reported, not used to exclude: anyone who is not an HIV case can be a control (File 09).
-- This is wider than the HIV definition (Files 04-06):
--   even a single HIV record is enough here (one outpatient code, only R75, one HIV drug fill).
--   Any HIV diagnosis code (any setting, R75 included), from the Supplement 1 list
--   Any HIV MS-DRG inpatient stay (Supplement 1)
--   Any HIV drug fill (from File 06 Step 1, so the same drug rules apply:
--     lamivudine alone is not HIV evidence; Paxlovid / HCV drugs follow File 06)
--   Anyone already in pwh_all (File 07)
-- Only looks at eligible people (File 03), since the non-HIV group comes from them.
-- Output: ${work_schema}.any_hiv_evidence_ids${sfx} (one row per person)

DROP TABLE IF EXISTS ${work_schema}.any_hiv_evidence_ids${sfx};

CREATE TABLE ${work_schema}.any_hiv_evidence_ids${sfx} AS
-- any HIV diagnosis code, any setting
SELECT DISTINCT patient_id
FROM ${komodo_schema}.normalized_dx_events
WHERE dx_code IN ('B20',
                  'B210', 'B211', 'B212', 'B213', 'B217', 'B218', 'B219',
                  'B220', 'B221', 'B222', 'B227',
                  'B230', 'B231', 'B232', 'B238',
                  'B24', 'B9735', 'B97.35', 'R75', 'Z21')
  AND event_date >= '${study_start}'
  AND event_date <  '${study_end}'
  AND patient_id IN (SELECT patient_id FROM ${work_schema}.eligible_ids${sfx})   -- only eligible people (File 03)
UNION
-- any HIV MS-DRG inpatient stay
SELECT DISTINCT patient_id
FROM ${komodo_schema}.inpatient_events
WHERE drg_code IN ('969', '970', '974', '975', '976', '977')
  AND admit_date >= '${study_start}' AND admit_date < '${study_end}'
  AND patient_id IN (SELECT patient_id FROM ${work_schema}.eligible_ids${sfx})
UNION
-- any HIV drug fill (File 06 Step 1 already found all HIV drug fills)
SELECT DISTINCT patient_id
FROM ${work_schema}.hiv_rx_fills_all${sfx}
WHERE patient_id IN (SELECT patient_id FROM ${work_schema}.eligible_ids${sfx})
UNION
-- everyone who met the HIV definition (File 07)
SELECT patient_id
FROM ${work_schema}.pwh_all${sfx};
-- (UNION, not UNION ALL, removes duplicates, so each person appears once)

-- check: people with any HIV evidence vs people who met the HIV definition
-- result: any_hiv_evidence_people
SELECT (SELECT COUNT(*) FROM ${work_schema}.any_hiv_evidence_ids${sfx}) AS any_evidence,
       (SELECT COUNT(*) FROM ${work_schema}.pwh_all${sfx})              AS met_hiv_definition;
