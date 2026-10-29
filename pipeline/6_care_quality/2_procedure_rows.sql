-- Care quality 2 [HEAVY]: procedure claims (CPT and HCPCS) of the matched people, per year,
-- from ${lookback_start} (config measures.lookback_years before the first study year) so a
-- measure can look back, e.g. a hearing screen in the last 5 years.
-- Only the codes in reference/procedure_codes.csv are read, as literal values so Spectrum
-- filters inside the scan. One statement per year; a year that times out is retried.
-- Outputs: ${work_schema}.matched_ids${sfx}, ${work_schema}.care_px_concepts${sfx}

DROP TABLE IF EXISTS ${work_schema}.matched_ids${sfx};

CREATE TABLE ${work_schema}.matched_ids${sfx} DISTKEY(patient_id) AS
SELECT DISTINCT patient_id FROM ${work_schema}.ps_matched${sfx};

DROP TABLE IF EXISTS ${work_schema}.care_px_concepts${sfx};

CREATE TABLE ${work_schema}.care_px_concepts${sfx} (
    patient_id   VARCHAR(100),
    concept_year SMALLINT,
    concept      VARCHAR(200),
    claims       BIGINT
) DISTKEY(patient_id) SORTKEY(patient_id, concept_year);

-- for each year: lookback
INSERT INTO ${work_schema}.care_px_concepts${sfx}
SELECT s.patient_id, ${year}, r.concept, SUM(s.claims)
FROM (
    SELECT patient_id, procedure_code, COUNT(*) AS claims
    FROM ${komodo_schema}.non_inpatient_events
    WHERE service_date >= '${year}-01-01'
      AND service_date <  '${next_year}-01-01'
      AND procedure_code IN (${procedure_codes})
      AND ${sample_filter}
    GROUP BY 1, 2
) s
JOIN ${work_schema}.matched_ids${sfx} i ON i.patient_id = s.patient_id
JOIN ${work_schema}.ref_procedures${sfx} r ON r.code = s.procedure_code
GROUP BY 1, 2, 3;

-- check: person-years with each procedure concept, per year
-- result: procedure_concepts_by_year
SELECT concept_year, concept, COUNT(*) AS person_years
FROM ${work_schema}.care_px_concepts${sfx}
GROUP BY 1, 2
ORDER BY 1, 2;
