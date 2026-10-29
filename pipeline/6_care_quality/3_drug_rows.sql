-- Care quality 3 [HEAVY]: final, paid pharmacy fills of the matched people, per year and
-- generic drug, from ${lookback_start}. Only generic names containing a word from
-- reference/drug_patterns.csv are read (a literal filter, so Spectrum applies it inside the
-- scan); drug concepts are then matched on the short list of distinct drug names.
-- One statement per year; a year that times out is retried.
-- Outputs: ${work_schema}.care_generic_fills${sfx}, ${work_schema}.care_drug_map${sfx}, ${work_schema}.care_rx_concepts${sfx}

DROP TABLE IF EXISTS ${work_schema}.care_generic_fills${sfx};

CREATE TABLE ${work_schema}.care_generic_fills${sfx} (
    patient_id   VARCHAR(100),
    concept_year SMALLINT,
    generic_name VARCHAR(200),
    fills        BIGINT
) DISTKEY(patient_id) SORTKEY(patient_id, concept_year);

-- for each year: lookback
INSERT INTO ${work_schema}.care_generic_fills${sfx}
SELECT s.patient_id, ${year}, s.generic_name, s.fills
FROM (
    SELECT patient_id, UPPER(TRIM(generic_name))::VARCHAR(200) AS generic_name, COUNT(*) AS fills
    FROM ${komodo_schema}.pharmacy_events
    WHERE fill_date >= '${year}-01-01'
      AND fill_date <  '${next_year}-01-01'
      AND UPPER(transaction_status) IN (${pharmacy_final_status})
      AND UPPER(transaction_result) = ${pharmacy_paid_result}
      AND generic_name IS NOT NULL
      AND generic_name ~* ${drug_patterns_regex}
      AND ${sample_filter}
    GROUP BY 1, 2
) s
JOIN ${work_schema}.matched_ids${sfx} i ON i.patient_id = s.patient_id;

DROP TABLE IF EXISTS ${work_schema}.care_drug_map${sfx};

CREATE TABLE ${work_schema}.care_drug_map${sfx} DISTSTYLE ALL AS
SELECT DISTINCT n.generic_name, r.concept
FROM (SELECT DISTINCT generic_name FROM ${work_schema}.care_generic_fills${sfx}) n
JOIN ${work_schema}.ref_drug_patterns${sfx} r ON n.generic_name LIKE '%' || r.pattern || '%';

DROP TABLE IF EXISTS ${work_schema}.care_rx_concepts${sfx};

CREATE TABLE ${work_schema}.care_rx_concepts${sfx}
DISTKEY(patient_id) SORTKEY(patient_id, concept_year) AS
SELECT g.patient_id, g.concept_year, m.concept, SUM(g.fills) AS fills
FROM ${work_schema}.care_generic_fills${sfx} g
JOIN ${work_schema}.care_drug_map${sfx} m ON m.generic_name = g.generic_name
GROUP BY 1, 2, 3;

-- check: which generic names each drug concept matched (names only, no counts)
-- result: drug_concept_names
SELECT concept, generic_name FROM ${work_schema}.care_drug_map${sfx} ORDER BY 1, 2;

-- check: person-years with each drug concept, per year
-- result: drug_concepts_by_year
SELECT concept_year, concept, COUNT(*) AS person_years
FROM ${work_schema}.care_rx_concepts${sfx}
GROUP BY 1, 2
ORDER BY 1, 2;
